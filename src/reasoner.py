"""
Reasoner — the "R" in the Perceive → Reason → Act loop.

Receives:
  - target_angles  : what the human arm is asking for (from JointMapper)
  - actual_angles  : what the robot joints are actually at (feedback from robot)
  - history        : last N states for trend detection

Decides:
  - adjusted_angles: what to actually send this cycle
  - should_act     : False if the delta is too small to be worth moving
  - error          : per-joint tracking error for monitoring

Without robot feedback (simulation or dry_run without telemetry), actual_angles
is estimated from the last commanded position — still useful for rate-limiting.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import deque
import time


@dataclass
class ReasonerState:
    cycle: int
    target: Dict[str, float]
    actual: Dict[str, float]
    error: Dict[str, float]       # target - actual per joint
    adjusted: Dict[str, float]    # what was sent
    should_act: bool
    timestamp: float


class Reasoner:
    """
    Applies safety checks, rate limiting, and error tracking between
    perception (pose) and action (joint command).
    """

    JOINT_IDS = ["1", "2", "3", "4", "5", "6"]

    def __init__(
        self,
        min_delta_deg: float = 0.5,     # ignore movements smaller than this
        max_delta_deg: float = 15.0,    # clamp max per-cycle joint change (safety)
        history_len: int = 30,
    ):
        self.min_delta = min_delta_deg
        self.max_delta = max_delta_deg
        self._estimated_actual: Dict[str, float] = {k: 0.0 for k in self.JOINT_IDS}
        self._history: deque[ReasonerState] = deque(maxlen=history_len)
        self._cycle = 0

    def reason(
        self,
        target: Dict[str, float],
        actual: Optional[Dict[str, float]] = None,
    ) -> ReasonerState:
        """
        Core reasoning step.

        actual — real joint positions read back from the robot.
                 If None, uses last commanded position as an estimate.
        """
        self._cycle += 1
        # Fall back to estimated state if no robot feedback available
        actual = actual if actual is not None else self._estimated_actual.copy()

        error = {k: target[k] - actual[k] for k in self.JOINT_IDS if k in target}

        # Rate-limit: clamp max movement per cycle to avoid violent jumps
        adjusted = {}
        for k in self.JOINT_IDS:
            if k not in target:
                adjusted[k] = actual.get(k, 0.0)
                continue
            delta = target[k] - actual[k]
            delta = max(-self.max_delta, min(self.max_delta, delta))
            adjusted[k] = actual[k] + delta

        # Decide whether to act: skip if all joints are already close enough
        max_error = max(abs(e) for e in error.values()) if error else 0.0
        should_act = max_error >= self.min_delta

        state = ReasonerState(
            cycle=self._cycle,
            target=target,
            actual=actual,
            error=error,
            adjusted=adjusted,
            should_act=should_act,
            timestamp=time.time(),
        )
        self._history.append(state)

        # Update our estimate of actual position
        if should_act:
            self._estimated_actual = adjusted.copy()

        return state

    def update_actual(self, actual: Dict[str, float]):
        """Call this when real robot telemetry arrives."""
        self._estimated_actual.update(actual)

    @property
    def last_error(self) -> Optional[Dict[str, float]]:
        return self._history[-1].error if self._history else None

    @property
    def is_converged(self) -> bool:
        """True if the last N cycles show shrinking error (robot is tracking well)."""
        if len(self._history) < 5:
            return False
        recent_max_errors = [
            max(abs(e) for e in s.error.values()) for s in list(self._history)[-5:]
        ]
        return recent_max_errors[-1] < recent_max_errors[0]
