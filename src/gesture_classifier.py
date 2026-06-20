"""
Gesture classifier — maps MediaPipe hand landmarks to discrete gestures.

Each gesture has a UNIQUE finger configuration (no directional ambiguity
for compound gestures). Direction detection is used ONLY for the single
index finger, which is robust due to the finger's length and MediaPipe
landmark quality.

Supported gestures:
  POINT_RIGHT    only index extended, pointing right
  POINT_LEFT     only index extended, pointing left
  POINT_UP       only index extended, pointing up
  POINT_DOWN     only index extended, pointing down
  DEPTH_FORWARD  index + pinky   (rock horns)  → elbow extend J3
  DEPTH_BACK     index+middle+ring (3 fingers)  → elbow retract J3
  PEACE          index + middle  (V sign, any direction) → grip open J6
  FIST           all 4 curled, thumb not clearly up  → grip close J6
  OPEN_PALM      all 4 extended  → stop
  THUMBS_UP      all 4 curled, thumb pointing straight up → home
  UNKNOWN        nothing recognized
"""

import math
import numpy as np
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional
import mediapipe as mp


class Gesture(Enum):
    POINT_RIGHT    = auto()
    POINT_LEFT     = auto()
    POINT_UP       = auto()
    POINT_DOWN     = auto()
    DEPTH_FORWARD  = auto()   # rock horns (index + pinky)
    DEPTH_BACK     = auto()   # 3 fingers  (index + middle + ring)
    FIST           = auto()
    OPEN_PALM      = auto()
    PEACE          = auto()   # V sign (index + middle), direction-agnostic
    THUMBS_UP      = auto()
    UNKNOWN        = auto()


@dataclass
class GestureResult:
    gesture: Gesture
    confidence: float
    hold_count: int
    confirmed: bool
    pointing_angle: Optional[float] = None


_HL = mp.solutions.hands.HandLandmark

TIPS = [_HL.INDEX_FINGER_TIP, _HL.MIDDLE_FINGER_TIP, _HL.RING_FINGER_TIP, _HL.PINKY_TIP]
PIPS = [_HL.INDEX_FINGER_PIP, _HL.MIDDLE_FINGER_PIP, _HL.RING_FINGER_PIP, _HL.PINKY_PIP]


def _lm(landmarks, idx) -> np.ndarray:
    p = landmarks[idx]
    return np.array([p.x, p.y], dtype=np.float32)


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def _finger_extended(landmarks, tip_idx, pip_idx) -> bool:
    """Tip is farther from wrist than PIP — works for all pointing directions."""
    wrist = _lm(landmarks, _HL.WRIST)
    tip   = _lm(landmarks, tip_idx)
    pip   = _lm(landmarks, pip_idx)
    return _dist(tip, wrist) > _dist(pip, wrist)


def _finger_clearly_extended(landmarks, tip_idx, pip_idx) -> bool:
    """Stricter: tip must be at least 15% further from wrist than PIP."""
    wrist = _lm(landmarks, _HL.WRIST)
    tip   = _lm(landmarks, tip_idx)
    pip   = _lm(landmarks, pip_idx)
    return _dist(tip, wrist) > _dist(pip, wrist) * 1.15


def _thumb_pointing_up(landmarks) -> bool:
    """
    Thumb pointing straight up:
    - All 3 thumb joints form a vertical chain (tip above IP above MCP)
    - Tip is well above the wrist in image space (Y smaller = higher)
    This rejects fists where the thumb is tucked sideways.
    """
    tip   = _lm(landmarks, _HL.THUMB_TIP)
    ip    = _lm(landmarks, _HL.THUMB_IP)
    mcp   = _lm(landmarks, _HL.THUMB_MCP)
    wrist = _lm(landmarks, _HL.WRIST)

    chain_up    = tip[1] < ip[1] < mcp[1]   # joints go upward through the chain
    well_above  = tip[1] < wrist[1] - 0.12  # tip is well above wrist baseline
    above_knuck = tip[1] < _lm(landmarks, _HL.INDEX_FINGER_MCP)[1]  # above index knuckle
    return chain_up and well_above and above_knuck


def _pointing_angle(landmarks) -> float:
    """Angle of the index finger vector. 0=right, 90=down, ±180=left, -90=up."""
    mcp = _lm(landmarks, _HL.INDEX_FINGER_MCP)
    tip = _lm(landmarks, _HL.INDEX_FINGER_TIP)
    return math.degrees(math.atan2(tip[1] - mcp[1], tip[0] - mcp[0]))


def _classify_raw(landmarks) -> tuple[Gesture, float, Optional[float]]:
    # Soft check for single-finger gestures (pointing)
    extended = [_finger_extended(landmarks, TIPS[i], PIPS[i]) for i in range(4)]
    # Strict check for compound gestures (peace, rock, 3-fingers)
    clearly  = [_finger_clearly_extended(landmarks, TIPS[i], PIPS[i]) for i in range(4)]

    index, middle, ring, pinky = extended
    ci, cm, cr, cp             = clearly

    # ── OPEN PALM — all 4 clearly extended ──────────────────────────────────
    if all(clearly):
        return Gesture.OPEN_PALM, 0.95, None

    # ── NO FINGERS EXTENDED — THUMBS_UP or FIST ─────────────────────────────
    if not any(extended):
        if _thumb_pointing_up(landmarks):
            return Gesture.THUMBS_UP, 0.9, None
        return Gesture.FIST, 0.9, None

    # ── ROCK HORNS (index + pinky clearly extended, middle + ring curled) ───
    # → DEPTH_FORWARD (elbow extend J3+)
    if ci and cp and not cm and not cr:
        return Gesture.DEPTH_FORWARD, 0.9, None

    # ── 3 FINGERS (index + middle + ring clearly extended, pinky curled) ────
    # → DEPTH_BACK (elbow retract J3-)
    if ci and cm and cr and not cp:
        return Gesture.DEPTH_BACK, 0.9, None

    # ── PEACE / V SIGN (index + middle clearly extended, ring + pinky curled)
    # → PEACE (grip open J6-) — direction-agnostic, no angle detection
    if ci and cm and not cr and not cp:
        return Gesture.PEACE, 0.9, None

    # ── POINTING — only index extended ──────────────────────────────────────
    # Use soft check here so normal pointing isn't blocked by strict threshold
    if index and not middle and not ring and not pinky:
        angle = _pointing_angle(landmarks)
        if   -50  <= angle <=  50:             return Gesture.POINT_RIGHT, 0.9, angle
        elif  50  <  angle <= 130:             return Gesture.POINT_DOWN,  0.9, angle
        elif  angle > 130 or angle < -130:     return Gesture.POINT_LEFT,  0.9, angle
        elif -130 <= angle <  -50:             return Gesture.POINT_UP,    0.9, angle

    return Gesture.UNKNOWN, 0.0, None


class GestureClassifier:
    def __init__(self, hold_frames: int = 5):
        self._hold_frames = hold_frames
        self._current: Gesture = Gesture.UNKNOWN
        self._count:   int     = 0

    def classify(self, hand_landmarks) -> GestureResult:
        if hand_landmarks is None:
            self._current = Gesture.UNKNOWN
            self._count   = 0
            return GestureResult(Gesture.UNKNOWN, 0.0, 0, False)

        gesture, confidence, angle = _classify_raw(hand_landmarks)

        if gesture == self._current:
            self._count += 1
        else:
            self._current = gesture
            self._count   = 1

        return GestureResult(
            gesture=gesture,
            confidence=confidence,
            hold_count=self._count,
            confirmed=self._count >= self._hold_frames,
            pointing_angle=angle,
        )

    def reset(self):
        self._current = Gesture.UNKNOWN
        self._count   = 0
