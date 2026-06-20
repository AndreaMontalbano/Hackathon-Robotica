"""
Unit tests for the joint mapper — no hardware or camera required.
Run: python -m pytest tests/
"""

import sys
import os
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pose_tracker import ArmLandmarks
from joint_mapper import JointMapper, JOINT_LIMITS


def make_landmarks(shoulder=(0.5, 0.4, 0.0), elbow=(0.5, 0.6, 0.0), wrist=(0.5, 0.8, 0.0)):
    return ArmLandmarks(
        shoulder=np.array(shoulder, dtype=np.float32),
        elbow=np.array(elbow, dtype=np.float32),
        wrist=np.array(wrist, dtype=np.float32),
    )


def test_output_has_all_joints():
    mapper = JointMapper()
    lm = make_landmarks()
    angles = mapper.map(lm)
    assert set(angles.keys()) == {"1", "2", "3", "4", "5", "6"}


def test_angles_within_limits():
    mapper = JointMapper()
    # Test several different arm positions
    positions = [
        make_landmarks(shoulder=(0.5, 0.4, 0.0), elbow=(0.6, 0.55, 0.0), wrist=(0.7, 0.7, 0.0)),
        make_landmarks(shoulder=(0.5, 0.4, 0.0), elbow=(0.4, 0.55, 0.0), wrist=(0.3, 0.7, 0.0)),
        make_landmarks(shoulder=(0.5, 0.4, 0.0), elbow=(0.5, 0.65, 0.05), wrist=(0.5, 0.85, 0.0)),
    ]
    for lm in positions:
        angles = mapper.map(lm)
        for joint_id, value in angles.items():
            limits = JOINT_LIMITS[joint_id]
            assert limits.min_deg <= value <= limits.max_deg, (
                f"Joint {joint_id} value {value:.1f} out of range "
                f"[{limits.min_deg}, {limits.max_deg}]"
            )


def test_smoothing_reduces_noise():
    mapper = JointMapper(smoothing=0.8)
    base = make_landmarks()
    noisy = make_landmarks(elbow=(0.55, 0.62, 0.0))

    mapper.map(base)     # first frame sets prev
    angles1 = mapper.map(base)
    angles2 = mapper.map(noisy)  # should be smoothed toward base, not jump

    # With smoothing=0.8, the change should be small
    diff = abs(angles2["3"] - angles1["3"])
    assert diff < 30, f"Smoothing too weak: joint 3 jumped {diff:.1f}°"


def test_calibration_sets_reference():
    mapper = JointMapper()
    neutral = make_landmarks()
    mapper.calibrate(neutral)
    assert mapper._ref_shoulder_y is not None
    assert abs(mapper._ref_shoulder_y - 0.4) < 1e-5
