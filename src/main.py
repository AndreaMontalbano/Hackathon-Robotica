"""
SO-101 Gesture Control — main loop.

Perceive → Reason → Act

Usage:
  python src/main.py --mode dry_run --debug
  python src/main.py --mode simulation --debug
  python src/main.py --mode real
"""

import sys
import os
import argparse
import logging
import time
import cv2
import mediapipe as mp
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from gesture_classifier import GestureClassifier, Gesture, GestureResult
from command_dispatcher import CommandDispatcher, HOME_POSITION
from robot_controller import RobotController

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

WINDOW = "SO-101 Gesture Control"

LEGEND = [
    "Index RIGHT    -> pan right  (J1)",
    "Index LEFT     -> pan left   (J1)",
    "Index UP       -> arm up     (J2)",
    "Index DOWN     -> arm down   (J2)",
    "Rock horns I+P -> depth fwd  (J3)",
    "3 fingers I+M+R-> depth back (J3)",
    "Peace V  I+M   -> grip open  (J6)",
    "FIST           -> grip close (J6)",
    "THUMB UP       -> home (zeros)",
    "OPEN PALM      -> stop",
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--mode",  default="dry_run", choices=["simulation", "real", "dry_run"])
    p.add_argument("--robot", default=os.getenv("CYBERWAVE_ROBOT_NAME", "so101-mirror"))
    p.add_argument("--cam",   default=0,   type=int)
    p.add_argument("--fps",   default=30,  type=int)
    p.add_argument("--hold",  default=5,   type=int,   help="Frames to confirm gesture")
    p.add_argument("--step",  default=3.0, type=float, help="Degrees per cycle")
    p.add_argument("--debug", action="store_true")
    return p.parse_args()


def draw_ui(frame, result: GestureResult, position: dict, mode: str, hold_frames: int):
    h, w = frame.shape[:2]

    # Gesture label
    label = result.gesture.name.replace("_", " ")
    color = (0, 255, 0) if result.confirmed else (0, 200, 255)
    cv2.putText(frame, label, (w // 2 - 140, 42),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, color, 3)

    if result.pointing_angle is not None:
        cv2.putText(frame, f"{result.pointing_angle:+.0f}d", (w // 2 + 90, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 100), 1)

    # Hold progress bar
    bar_w = int(min(result.hold_count / max(hold_frames, 1), 1.0) * 220)
    bx    = w // 2 - 110
    cv2.rectangle(frame, (bx, 52), (bx + 220, 65), (50, 50, 50), -1)
    cv2.rectangle(frame, (bx, 52), (bx + bar_w, 65), color, -1)
    cv2.putText(frame, f"{result.hold_count}/{hold_frames}", (bx + 225, 64),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 150, 150), 1)

    # Joint positions — bottom left
    y0 = h - 160
    cv2.rectangle(frame, (10, y0 - 22), (220, h - 10), (20, 20, 20), -1)
    for i, (k, v) in enumerate(sorted(position.items())):
        cv2.putText(frame, f"{k}: {v:+.1f}deg", (18, y0 + i * 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200, 200, 200), 1)

    # Legend — right side
    cv2.rectangle(frame, (w - 215, 10), (w - 5, 15 + len(LEGEND) * 20 + 5), (20, 20, 20), -1)
    for i, line in enumerate(LEGEND):
        cv2.putText(frame, line, (w - 211, 28 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1)

    # Mode badge
    colors = {"simulation": (0, 165, 255), "real": (0, 80, 255), "dry_run": (120, 120, 120)}
    cv2.putText(frame, f"[{mode.upper()}]", (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, colors.get(mode, (200, 200, 200)), 2)

    return frame


def main():
    args = parse_args()
    logger.info(f"Mode: {args.mode} | Hold: {args.hold} frames | Step: {args.step} deg/frame")

    hands      = mp.solutions.hands.Hands(max_num_hands=1,
                                           min_detection_confidence=0.75,
                                           min_tracking_confidence=0.75)
    mp_draw    = mp.solutions.drawing_utils
    classifier = GestureClassifier(hold_frames=args.hold)
    dispatcher = CommandDispatcher(step=args.step)
    controller = RobotController(robot_name=args.robot, mode=args.mode)

    cap = cv2.VideoCapture(args.cam)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    if not cap.isOpened():
        logger.error(f"Cannot open camera {args.cam}")
        sys.exit(1)

    controller.connect()

    # Send HOME after connect — simulation might still be loading, retry once
    controller.send_joints(HOME_POSITION)
    if controller.mode == "simulation":
        # Wait briefly for sim to be ready, then send HOME again
        time.sleep(3.0)
        controller.send_joints(HOME_POSITION)

    logger.info("Ready. Show your right hand. Press Q to quit.")

    prev_confirmed_gesture = Gesture.UNKNOWN

    try:
        while True:
            t0 = time.time()

            # ── PERCEIVE ─────────────────────────────────────────────────────
            ret, frame = cap.read()
            if not ret:
                continue
            frame = cv2.flip(frame, 1)
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            hand_result = hands.process(rgb)

            hand_lm = None
            if hand_result.multi_hand_landmarks:
                hand_lm = hand_result.multi_hand_landmarks[0].landmark
                if args.debug:
                    mp_draw.draw_landmarks(frame,
                                           hand_result.multi_hand_landmarks[0],
                                           mp.solutions.hands.HAND_CONNECTIONS)

            # ── REASON ───────────────────────────────────────────────────────
            result  = classifier.classify(hand_lm)
            command = dispatcher.dispatch(result.gesture, result.confirmed)

            # ── ACT ──────────────────────────────────────────────────────────
            if command:
                if command.is_home:
                    # Edge-trigger: only on the first confirmed frame
                    if result.gesture != prev_confirmed_gesture:
                        controller.send_joints(HOME_POSITION)
                        dispatcher.reset_to_home()
                        logger.info("-> HOME (L shape)")
                elif not command.is_stop:
                    controller.send_joints(dispatcher.current_position)
                    logger.info(f"-> {command.label} | _1={dispatcher.current_position['_1']:+.0f} _2={dispatcher.current_position['_2']:+.0f} _3={dispatcher.current_position['_3']:+.0f} _6={dispatcher.current_position['_6']:+.0f}")

            prev_confirmed_gesture = result.gesture if result.confirmed else Gesture.UNKNOWN

            # ── UI ───────────────────────────────────────────────────────────
            if args.debug:
                if not hand_lm:
                    cv2.putText(frame, "Show your hand", (frame.shape[1]//2 - 110, frame.shape[0]//2),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 200), 2)

                draw_ui(frame, result, dispatcher.current_position, args.mode, args.hold)
                cv2.imshow(WINDOW, frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            elapsed = time.time() - t0
            time.sleep(max(0, 1 / args.fps - elapsed))

    except KeyboardInterrupt:
        logger.info("Stopped by user")
    finally:
        controller.disconnect()
        hands.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
