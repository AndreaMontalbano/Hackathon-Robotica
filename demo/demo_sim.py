"""
Quick demo — runs the full pipeline in DRY RUN mode with a synthetic sine wave
to verify the joint mapper and controller work without any hardware or camera.

Run: python demo/demo_sim.py
"""

import sys
import os
import math
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from joint_mapper import JointMapper
from robot_controller import RobotController
import numpy as np
from pose_tracker import ArmLandmarks


def synthetic_landmarks(t: float) -> ArmLandmarks:
    """Simulate a slow arm-raise motion using a sine wave."""
    shoulder = np.array([0.5, 0.4, 0.0], dtype=np.float32)
    elbow = np.array([
        0.5 + 0.15 * math.sin(t),
        0.55 + 0.1 * math.cos(t),
        0.0
    ], dtype=np.float32)
    wrist = np.array([
        elbow[0] + 0.1 * math.sin(t * 1.5),
        elbow[1] + 0.12,
        0.0
    ], dtype=np.float32)
    return ArmLandmarks(shoulder=shoulder, elbow=elbow, wrist=wrist)


def main():
    print("=" * 50)
    print("  SO-101 Mirror Arm — DRY RUN DEMO")
    print("  (no hardware required)")
    print("=" * 50)

    mapper     = JointMapper(smoothing=0.3)
    controller = RobotController(robot_name="so-101-twin", mode="dry_run")

    controller.connect()
    controller.home()

    # Calibrate with a reference neutral pose
    neutral = synthetic_landmarks(0.0)
    mapper.calibrate(neutral)
    print("\nCalibration done. Running 10-second sine wave demo...\n")

    start = time.time()
    while time.time() - start < 10.0:
        t = time.time() - start
        lm = synthetic_landmarks(t)
        angles = mapper.map(lm)
        controller.send_joints(angles)
        time.sleep(0.1)

    controller.disconnect()
    print("\nDemo complete.")


if __name__ == "__main__":
    main()
