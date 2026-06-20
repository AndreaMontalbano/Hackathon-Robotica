"""
Gesture test — verifica il classificatore in tempo reale senza robot.

Run: python demo/test_gestures.py

Mostra:
  - skeleton della mano
  - gesto rilevato + stato di conferma
  - angolo del dito indice
"""

import sys
import os
import cv2
import mediapipe as mp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gesture_classifier import GestureClassifier, Gesture


COLORS = {
    Gesture.POINT_RIGHT:   (0, 255, 100),
    Gesture.POINT_LEFT:    (0, 255, 100),
    Gesture.POINT_UP:      (0, 255, 100),
    Gesture.POINT_DOWN:    (0, 255, 100),
    Gesture.FIST:          (0, 100, 255),
    Gesture.OPEN_PALM:     (200, 200, 200),
    Gesture.PEACE:         (255, 200, 0),
    Gesture.THUMBS_UP:     (0, 220, 255),
    Gesture.UNKNOWN:       (80, 80, 80),
}

def main():
    hands = mp.solutions.hands.Hands(
        max_num_hands=1,
        min_detection_confidence=0.75,
        min_tracking_confidence=0.75,
    )
    draw   = mp.solutions.drawing_utils
    clf    = GestureClassifier(hold_frames=8)
    cap    = cv2.VideoCapture(0)

    print("Gesture test running. Press Q to quit.")
    print("Gestures: point (↑↓←→), fist, open palm, peace sign, thumbs up")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.flip(frame, 1)
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res   = hands.process(rgb)

        hand_lm = None
        if res.multi_hand_landmarks:
            hand_lm = res.multi_hand_landmarks[0].landmark
            draw.draw_landmarks(frame, res.multi_hand_landmarks[0],
                                mp.solutions.hands.HAND_CONNECTIONS)

        result = clf.classify(hand_lm)
        color  = COLORS.get(result.gesture, (200, 200, 200))
        label  = result.gesture.name.replace("_", " ")

        # Gesture label
        cv2.putText(frame, label, (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.3,
                    (0, 255, 0) if result.confirmed else color, 3)

        # Confirmation status
        status = "CONFIRMED ✓" if result.confirmed else f"hold... ({result.hold_count}/8)"
        cv2.putText(frame, status, (20, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 0) if result.confirmed else (0, 200, 255), 2)

        # Pointing angle
        if result.pointing_angle is not None:
            cv2.putText(frame, f"angle: {result.pointing_angle:.0f}°", (20, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        cv2.imshow("Gesture Test", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    hands.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
