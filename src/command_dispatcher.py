"""
Command dispatcher — maps a confirmed Gesture to an incremental SO-101 joint command.

Gesture → Command:
  POINT_RIGHT    → pan base right      (J1 +)
  POINT_LEFT     → pan base left       (J1 -)
  POINT_UP       → raise shoulder      (J2 -)
  POINT_DOWN     → lower shoulder      (J2 +)
  DEPTH_FORWARD  → extend elbow fwd    (J3 +)   rock horns (index + pinky)
  DEPTH_BACK     → retract elbow       (J3 -)   3 fingers (index+middle+ring)
  FIST           → close gripper       (J6 +)
  PEACE          → open gripper        (J6 -)   V sign, direction-agnostic
  THUMBS_UP      → home position (all zeros)
  OPEN_PALM      → stop / hold
  UNKNOWN        → stop / hold
"""

from dataclasses import dataclass
from typing import Dict, Optional
from gesture_classifier import Gesture


@dataclass
class RobotCommand:
    label: str
    deltas: Dict[str, float]
    is_home: bool = False
    is_stop: bool = False


def _build_gesture_map(step: float) -> Dict[Gesture, RobotCommand]:
    return {
        Gesture.POINT_RIGHT:   RobotCommand("PAN RIGHT",       {"_1": +step}),
        Gesture.POINT_LEFT:    RobotCommand("PAN LEFT",        {"_1": -step}),
        Gesture.POINT_UP:      RobotCommand("ARM UP",          {"_2": -step}),
        Gesture.POINT_DOWN:    RobotCommand("ARM DOWN",        {"_2": +step}),
        Gesture.DEPTH_FORWARD: RobotCommand("DEPTH FORWARD",   {"_3": +step}),
        Gesture.DEPTH_BACK:    RobotCommand("DEPTH BACK",      {"_3": -step}),
        Gesture.FIST:          RobotCommand("GRIP CLOSE",      {"_6": -step}),
        Gesture.PEACE:         RobotCommand("GRIP OPEN",       {"_6": +step}),
        Gesture.THUMBS_UP:     RobotCommand("HOME",            {}, is_home=True),
        Gesture.OPEN_PALM:     RobotCommand("STOP",            {}, is_stop=True),
        Gesture.UNKNOWN:       RobotCommand("HOLD",            {}, is_stop=True),
    }


JOINT_LIMITS: Dict[str, tuple] = {
    "_1": (-90,  90),
    "_2": (-90,  90),
    "_3": (  0, 135),
    "_4": (-90,  90),
    "_5": (-90,  90),
    "_6": (  0, 100),
}

HOME_POSITION: Dict[str, float] = {
    "_1": 0, "_2": 0, "_3": 0, "_4": 0, "_5": 0, "_6": 0
}


class CommandDispatcher:
    def __init__(self, step: float = 3.0):
        self._gesture_map = _build_gesture_map(step)
        self._current: Dict[str, float] = HOME_POSITION.copy()

    def dispatch(self, gesture: Gesture, confirmed: bool) -> Optional[RobotCommand]:
        if not confirmed:
            return None

        command = self._gesture_map.get(gesture)
        if command is None or command.is_stop:
            return None

        if command.is_home:
            self._current = HOME_POSITION.copy()
            return command

        proposed = self._current.copy()
        for joint_id, delta in command.deltas.items():
            lo, hi = JOINT_LIMITS[joint_id]
            proposed[joint_id] = max(lo, min(hi, proposed[joint_id] + delta))

        if proposed == self._current:
            return None

        self._current = proposed
        return command

    @property
    def current_position(self) -> Dict[str, float]:
        return self._current.copy()

    def reset_to_home(self):
        self._current = HOME_POSITION.copy()

    def sync(self, actual: Dict[str, float]):
        self._current.update(actual)
