"""
Camera + pose tracker test — standalone, no robot or Cyberwave needed.

Run: python demo/test_camera.py
     python demo/test_camera.py --cam 1   (se hai più camere)

Mostra la finestra della webcam con lo scheletro del braccio destro in tempo reale.
Stampa le coordinate grezze dei landmark per aiutare il debug del mapper.
Premi Q per uscire.
"""

import sys
import os
import cv2
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pose_tracker import PoseTracker
import argparse


def parse_args():
    p = argparse.ArgumentParser(description="Test camera and pose tracker")
    p.add_argument("--cam", default=0, type=int, help="Camera index")
    p.add_argument("--no-hands", action="store_true", help="Disable hand tracking")
    return p.parse_args()


def main():
    args = parse_args()

    print(f"Opening camera {args.cam}...")
    cap = cv2.VideoCapture(args.cam)

    if not cap.isOpened():
        print(f"ERROR: Cannot open camera {args.cam}")
        print("Try --cam 1 or --cam 2 if you have multiple cameras")
        sys.exit(1)

    tracker = PoseTracker(use_hands=not args.no_hands)

    print("Camera OK. Press Q to quit.")
    print("Move your RIGHT arm in front of the camera.")
    print()

    fps_counter = 0
    fps_start = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Camera read failed")
            break

        frame = cv2.flip(frame, 1)
        landmarks = tracker.process(frame)

        if landmarks is None:
            cv2.putText(frame, "No pose detected — show your full right arm",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        else:
            frame = tracker.draw_debug(frame, landmarks)

            # Print landmark coords to terminal
            s, e, w = landmarks.shoulder, landmarks.elbow, landmarks.wrist
            coords = (
                f"  Shoulder: ({s[0]:.2f}, {s[1]:.2f}, {s[2]:.2f})  "
                f"Elbow: ({e[0]:.2f}, {e[1]:.2f}, {e[2]:.2f})  "
                f"Wrist: ({w[0]:.2f}, {w[1]:.2f}, {w[2]:.2f})"
            )
            # Overwrite same line
            print(f"\r{coords}", end="", flush=True)

            if landmarks.index_tip is not None:
                it = landmarks.index_tip
                tt = landmarks.thumb_tip
                cv2.putText(frame, f"Pinch: ({it[0]:.2f},{it[1]:.2f})",
                            (20, frame.shape[0] - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 0), 1)

            cv2.putText(frame, "Pose OK", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        # FPS counter
        fps_counter += 1
        if time.time() - fps_start >= 1.0:
            fps = fps_counter / (time.time() - fps_start)
            fps_counter = 0
            fps_start = time.time()
            cv2.putText(frame, f"FPS: {fps:.0f}", (frame.shape[1] - 100, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 1)

        cv2.imshow("Camera Test — SO101 Mirror Arm", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    print()  # newline after the overwritten line
    tracker.release()
    cap.release()
    cv2.destroyAllWindows()
    print("Done.")


if __name__ == "__main__":
    main()
