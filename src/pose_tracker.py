"""
Pose tracker — wraps MediaPipe to extract right-arm joint landmarks from a camera frame.
Returns normalized 3D coordinates for shoulder, elbow, and wrist.
"""

import cv2
import mediapipe as mp
import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class ArmLandmarks:
    shoulder: np.ndarray  # [x, y, z]
    elbow: np.ndarray
    wrist: np.ndarray
    # Optional: hand landmarks for gripper control
    index_tip: Optional[np.ndarray] = None
    thumb_tip: Optional[np.ndarray] = None


class PoseTracker:
    def __init__(self, use_hands: bool = True, confidence: float = 0.7):
        self._pose = mp.solutions.pose.Pose(
            min_detection_confidence=confidence,
            min_tracking_confidence=confidence,
            model_complexity=1,
        )
        self._hands = None
        if use_hands:
            self._hands = mp.solutions.hands.Hands(
                max_num_hands=1,
                min_detection_confidence=confidence,
                min_tracking_confidence=confidence,
            )

    def process(self, frame_bgr: np.ndarray) -> Optional[ArmLandmarks]:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pose_result = self._pose.process(rgb)

        if not pose_result.pose_landmarks:
            return None

        lm = pose_result.pose_landmarks.landmark
        PL = mp.solutions.pose.PoseLandmark

        def to_arr(p) -> np.ndarray:
            return np.array([p.x, p.y, p.z], dtype=np.float32)

        arm = ArmLandmarks(
            shoulder=to_arr(lm[PL.RIGHT_SHOULDER]),
            elbow=to_arr(lm[PL.RIGHT_ELBOW]),
            wrist=to_arr(lm[PL.RIGHT_WRIST]),
        )

        if self._hands:
            hand_result = self._hands.process(rgb)
            if hand_result.multi_hand_landmarks:
                hl = hand_result.multi_hand_landmarks[0].landmark
                arm.index_tip = to_arr(hl[mp.solutions.hands.HandLandmark.INDEX_FINGER_TIP])
                arm.thumb_tip = to_arr(hl[mp.solutions.hands.HandLandmark.THUMB_TIP])

        return arm

    def draw_debug(self, frame_bgr: np.ndarray, landmarks: ArmLandmarks) -> np.ndarray:
        """Draw arm skeleton on frame for visual debugging."""
        h, w = frame_bgr.shape[:2]
        out = frame_bgr.copy()

        def px(p: np.ndarray):
            return (int(p[0] * w), int(p[1] * h))

        pts = [landmarks.shoulder, landmarks.elbow, landmarks.wrist]
        for i in range(len(pts) - 1):
            cv2.line(out, px(pts[i]), px(pts[i + 1]), (0, 255, 0), 3)
        for p in pts:
            cv2.circle(out, px(p), 8, (0, 0, 255), -1)

        return out

    def release(self):
        self._pose.close()
        if self._hands:
            self._hands.close()
