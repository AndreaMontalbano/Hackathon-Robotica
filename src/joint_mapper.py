"""
Joint mapper — converts human arm landmarks to SO-101 joint angles.

SO-101 has 6 joints (string IDs "1"–"6"):
  "1" → Shoulder Pan   (left/right rotation)   range: -90 to 90 deg
  "2" → Shoulder Tilt  (up/down)                range: -90 to 90 deg
  "3" → Elbow Flex     (bend)                   range:   0 to 135 deg
  "4" → Wrist Flex     (up/down)                range: -90 to 90 deg
  "5" → Wrist Roll     (rotation)               range: -90 to 90 deg
  "6" → Gripper        (open/close)             range:   0 to 100 (%)

Human arm MediaPipe coordinates are normalized [0,1] image space (x,y) + depth (z).
Angles are extracted geometrically and then linearly remapped to the robot's range.
"""

import numpy as np
from dataclasses import dataclass
from typing import Dict, Optional
from pose_tracker import ArmLandmarks


@dataclass
class JointLimits:
    min_deg: float
    max_deg: float


# SO-101 joint limits — adjust after physical calibration
JOINT_LIMITS: Dict[str, JointLimits] = {
    "1": JointLimits(-90, 90),
    "2": JointLimits(-90, 90),
    "3": JointLimits(0,  135),
    "4": JointLimits(-90, 90),
    "5": JointLimits(-90, 90),
    "6": JointLimits(0,  100),
}


def _angle_between(a: np.ndarray, vertex: np.ndarray, b: np.ndarray) -> float:
    """Angle at `vertex` formed by vectors vertex→a and vertex→b, in degrees."""
    v1 = a - vertex
    v2 = b - vertex
    norm = np.linalg.norm(v1) * np.linalg.norm(v2)
    if norm < 1e-6:
        return 0.0
    cos_a = np.clip(np.dot(v1, v2) / norm, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_a)))


def _clamp(value: float, limits: JointLimits) -> float:
    return max(limits.min_deg, min(limits.max_deg, value))


def _remap(value: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
    """Linear remap from [in_min, in_max] to [out_min, out_max]."""
    if in_max == in_min:
        return (out_min + out_max) / 2
    ratio = (value - in_min) / (in_max - in_min)
    return out_min + ratio * (out_max - out_min)


class JointMapper:
    """
    Maps human arm pose to SO-101 joint angles.

    Calibration: call `calibrate(ref_landmarks)` while the human holds a
    neutral T-pose to set the zero-angle reference for each joint.
    """

    def __init__(self, smoothing: float = 0.4):
        # smoothing ∈ [0,1]: 0 = no smoothing, 1 = frozen
        self._alpha = smoothing
        self._prev: Optional[Dict[str, float]] = None
        self._ref_shoulder_y: Optional[float] = None

    def calibrate(self, landmarks: ArmLandmarks):
        """Record neutral reference pose for shoulder height normalization."""
        self._ref_shoulder_y = float(landmarks.shoulder[1])

    def map(self, landmarks: ArmLandmarks) -> Dict[str, float]:
        angles = self._compute(landmarks)
        angles = self._smooth(angles)
        return angles

    def _compute(self, lm: ArmLandmarks) -> Dict[str, float]:
        s, e, w = lm.shoulder, lm.elbow, lm.wrist

        # Joint 1 — Shoulder Pan: horizontal angle of upper arm in image plane
        # Positive = arm moves right, negative = left
        dx = e[0] - s[0]
        dy = e[1] - s[1]
        pan_raw = float(np.degrees(np.arctan2(dx, -dy)))  # 0 = straight down
        j1 = _clamp(_remap(pan_raw, -60, 60, -90, 90), JOINT_LIMITS["1"])

        # Joint 2 — Shoulder Tilt: vertical raise of upper arm
        ref_y = self._ref_shoulder_y if self._ref_shoulder_y is not None else 0.5
        shoulder_raise = ref_y - s[1]  # positive = shoulder raised in image
        upper_arm_angle = float(np.degrees(np.arctan2(-dy, abs(dx) + 1e-6)))
        j2 = _clamp(_remap(upper_arm_angle, -90, 90, -90, 90), JOINT_LIMITS["2"])

        # Joint 3 — Elbow Flex: angle at elbow
        elbow_angle = _angle_between(s, e, w)
        j3 = _clamp(_remap(elbow_angle, 180, 20, 0, 135), JOINT_LIMITS["3"])

        # Joint 4 — Wrist Flex: vertical direction of forearm
        fw_dx = w[0] - e[0]
        fw_dy = w[1] - e[1]
        wrist_angle = float(np.degrees(np.arctan2(fw_dy, fw_dx)))
        j4 = _clamp(_remap(wrist_angle, -90, 90, -90, 90), JOINT_LIMITS["4"])

        # Joint 5 — Wrist Roll: estimated from wrist z-depth vs elbow (rough proxy)
        # Better data needs a depth camera or IMU; this is a placeholder
        z_diff = float(w[2] - e[2])
        j5 = _clamp(_remap(z_diff, -0.2, 0.2, -45, 45), JOINT_LIMITS["5"])

        # Joint 6 — Gripper: distance between index tip and thumb tip (if available)
        j6 = 50.0  # default half-open
        if lm.index_tip is not None and lm.thumb_tip is not None:
            pinch_dist = float(np.linalg.norm(lm.index_tip - lm.thumb_tip))
            # pinch_dist ≈ 0.02 (closed) to 0.15 (open)
            j6 = _clamp(_remap(pinch_dist, 0.02, 0.15, 0, 100), JOINT_LIMITS["6"])

        return {"1": j1, "2": j2, "3": j3, "4": j4, "5": j5, "6": j6}

    def _smooth(self, angles: Dict[str, float]) -> Dict[str, float]:
        if self._prev is None:
            self._prev = angles
            return angles
        smoothed = {
            k: self._alpha * self._prev[k] + (1 - self._alpha) * v
            for k, v in angles.items()
        }
        self._prev = smoothed
        return smoothed
