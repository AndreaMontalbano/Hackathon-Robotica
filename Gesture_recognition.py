import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import cv2
import mediapipe as mp


# -----------------------------
# MediaPipe setup
# -----------------------------
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

cap = cv2.VideoCapture(0)


# -----------------------------
# Utility functions
# -----------------------------
def distance(a, b):
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def finger_extended(lm, tip_id, pip_id, mcp_id):
    wrist = lm[0]

    return (
        distance(lm[tip_id], wrist)
        > distance(lm[pip_id], wrist)
        > distance(lm[mcp_id], wrist)
    )


# -----------------------------
# Pointing direction
# -----------------------------
def pointing_direction_two_fingers(lm):

    # centro tra indice e medio alla base
    base_x = (lm[5].x + lm[9].x) / 2
    base_y = (lm[5].y + lm[9].y) / 2

    # centro tra le due punte
    tip_x = (lm[8].x + lm[12].x) / 2
    tip_y = (lm[8].y + lm[12].y) / 2

    dx = tip_x - base_x
    dy = tip_y - base_y

    threshold = 0.05

    if abs(dx) < threshold and abs(dy) < threshold:
        return "POINT"

    if abs(dx) > abs(dy):
        if dx > 0:
            return "POINT RIGHT"
        else:
            return "POINT LEFT"

    else:
        if dy > 0:
            return "POINT DOWN"
        else:
            return "POINT UP"


# -----------------------------
# Gesture recognition
# -----------------------------
def recognize_gesture(hand_landmarks):

    lm = hand_landmarks.landmark

    index_open = finger_extended(lm, 8, 6, 5)
    middle_open = finger_extended(lm, 12, 10, 9)
    ring_open = finger_extended(lm, 16, 14, 13)
    pinky_open = finger_extended(lm, 20, 18, 17)

    # mano aperta
    if (
        index_open
        and middle_open
        and ring_open
        and pinky_open
    ):
        return "OPEN HAND"

    # pugno
    if (
        not index_open
        and not middle_open
        and not ring_open
        and not pinky_open
    ):
        return "FIST"

    # indice + medio
    if (
        index_open
        and middle_open
        and not ring_open
        and not pinky_open
    ):
        return pointing_direction_two_fingers(lm)

    return "UNKNOWN"


# -----------------------------
# Main loop
# -----------------------------
with mp_hands.Hands(
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
) as hands:

    while True:

        ret, frame = cap.read()

        if not ret:
            break

        frame = cv2.flip(frame, 1)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        results = hands.process(rgb)

        gesture = "NO HAND"

        if results.multi_hand_landmarks:

            for hand_landmarks in results.multi_hand_landmarks:

                mp_draw.draw_landmarks(
                    frame,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS
                )

                gesture = recognize_gesture(hand_landmarks)

        cv2.putText(
            frame,
            gesture,
            (30, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (0, 255, 0),
            3
        )

        cv2.imshow("Gesture Recognition", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

cap.release()
cv2.destroyAllWindows()