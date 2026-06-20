# SO-101 Hand Gesture Reference

Each gesture has a unique finger configuration. There is no ambiguity —
every gesture is identified purely by **which fingers are extended**, with
direction detection used only for single-index pointing (which is robust).

---

## Gesture Map

### 1. Index Pointing — Base Pan (Joint 1)

**Extend only the index finger. Point left or right.**

```
→  INDEX POINTING RIGHT   →  base rotates RIGHT
←  INDEX POINTING LEFT    →  base rotates LEFT
```

Keep all other fingers curled. The arm holds the direction as long as you hold the pose.

---

### 2. Index Pointing — Shoulder Up/Down (Joint 2)

**Extend only the index finger. Point up or down.**

```
↑  INDEX POINTING UP      →  shoulder raises
↓  INDEX POINTING DOWN    →  shoulder lowers
```

---

### 3. Rock Horns — Elbow Extend (Joint 3 forward)

**Extend index finger AND pinky finger. Curl middle and ring fingers. Thumb can be in or out.**

```
🤘  INDEX + PINKY extended
    middle + ring CURLED
    → elbow extends (arm reaches forward)
```

Classic rock/metal hand sign. Hold until elbow reaches desired position.

---

### 4. Three Fingers — Elbow Retract (Joint 3 back)

**Extend index + middle + ring. Pinky curled. Thumb in.**

```
🖖 (without pinky)  INDEX + MIDDLE + RING extended
                    pinky CURLED
                    → elbow retracts (arm pulls back)
```

---

### 5. Peace / V Sign — Grip Open (Joint 6)

**Extend index finger AND middle finger. Ring and pinky curled. Direction does not matter.**

```
✌️  INDEX + MIDDLE extended
    ring + pinky CURLED
    → gripper opens
```

Can point in any direction — the direction is ignored, only the V configuration matters.

---

### 6. Fist — Grip Close (Joint 6)

**All four fingers curled. Thumb also tucked in (not pointing up).**

```
✊  ALL FOUR fingers CURLED
    thumb tucked (not pointing up)
    → gripper closes
```

Make sure the thumb is pressed against the fingers, not sticking up — that is the home gesture.

---

### 7. Thumbs Up — HOME Position

**All four fingers curled (fist). Thumb pointing straight UP.**

```
👍  ALL FOUR fingers CURLED
    THUMB pointing STRAIGHT UP (well above wrist)
    → all joints return to 0° (L-shape rest position)
```

The thumb must be clearly vertical — tilted thumbs will be ignored to avoid accidental home triggers.

---

### 8. Open Palm — STOP

**All five fingers extended, palm facing the camera.**

```
🖐️  ALL FOUR fingers + thumb EXTENDED
    → robot stops moving, holds current position
```

Use this whenever you want to pause and hold the robot in place.

---

## Quick Reference Card

| Gesture | Fingers up | Action | Joint |
|---------|-----------|--------|-------|
| Point → | Index only | Pan right | J1 |
| Point ← | Index only | Pan left | J1 |
| Point ↑ | Index only | Arm up | J2 |
| Point ↓ | Index only | Arm down | J2 |
| Rock horns 🤘 | Index + Pinky | Elbow extend | J3 |
| Three fingers | Index+Middle+Ring | Elbow retract | J3 |
| Peace ✌️ | Index + Middle | Grip open | J6 |
| Fist ✊ | None (thumb in) | Grip close | J6 |
| Thumbs up 👍 | None (thumb up) | HOME / reset | all |
| Open palm 🖐️ | All four | STOP / hold | — |

---

## Tips for Reliability

- **Pointing gestures**: Extend the index finger fully and let the others curl naturally. A straight index gives the most accurate angle detection.
- **Rock horns**: Make sure middle and ring are firmly curled — a loose middle finger can be confused with a 3-finger gesture.
- **Peace vs 3-fingers**: Peace is index+middle; 3-fingers adds the ring. The distinction is whether the ring finger is extended.
- **Fist vs Thumbs up**: The only difference is whether the thumb is pointing straight up. Keep the thumb pressed against the fingers for a clean fist.
- **Hold the gesture still**: The system requires 5 consecutive frames of the same gesture before sending a command. Steady hand = faster response.
