"""Spring motion for Qt.

`QPropertyAnimation` interpolates between a start and an end over a fixed duration. That is fine
for something nobody can interrupt, and wrong for everything else: retarget it mid-flight and it
restarts from wherever it decided the start was, which is the visible jump you see in careless
UIs. A spring has no fixed duration and no start value — it only ever has a current value, a
velocity, and a target. Retargeting is just assigning a new target, and the motion stays
continuous because the velocity carries through.

Parameterised the way Apple exposes it, in damping ratio and response, rather than in
mass/stiffness/damping:

    damping 1.0  critically damped — reaches the target and stops, no overshoot
    damping 0.8  a little bounce, appropriate only after a gesture that carried momentum
    response     roughly how long it takes to get there, in seconds

Nothing in this app is dragged, so the house default is critically damped.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QObject, QTimer, Signal

from .theme import Motion

_TICK_MS = 16          # ~60 Hz; the display's own clock is the reference for smoothness
_SETTLE = 0.5          # px: below this, and slow, the motion is over
_SETTLE_V = 1.0        # px/s


class Spring:
    """One scalar under spring physics. Pure — no Qt, no clock, so it can be unit tested."""

    def __init__(
        self,
        value: float = 0.0,
        response: float = Motion.STANDARD_RESPONSE,
        damping: float = Motion.STANDARD_DAMPING,
    ) -> None:
        self.value = value
        self.target = value
        self.velocity = 0.0
        self.response = max(1e-3, response)
        self.damping = damping

    def retarget(self, target: float, velocity: float | None = None) -> None:
        """Aim somewhere new WITHOUT touching the current value. That is the whole point: the
        animation continues from what is on screen instead of snapping to a fresh start."""
        self.target = target
        if velocity is not None:
            self.velocity = velocity

    def jump_to(self, value: float) -> None:
        self.value = self.target = value
        self.velocity = 0.0

    @property
    def settled(self) -> bool:
        return abs(self.value - self.target) < _SETTLE and abs(self.velocity) < _SETTLE_V

    def step(self, dt: float) -> float:
        omega = 2 * math.pi / self.response
        # Semi-implicit Euler: velocity first, then position. Stable at 60 Hz for these stiffnesses,
        # where plain Euler visibly overshoots on the snappier responses.
        accel = -(omega**2) * (self.value - self.target) - 2 * self.damping * omega * self.velocity
        self.velocity += accel * dt
        self.value += self.velocity * dt
        if self.settled:
            self.value = self.target
            self.velocity = 0.0
        return self.value


class SpringDriver(QObject):
    """Drives one or more springs off a single timer and reports each frame.

    One timer for the whole group rather than one per spring: 2D motion is two independent
    springs (a single spring on a 2D distance desynchronises when the axes have different
    velocities), and they must advance on the same frame or the shape wobbles.
    """

    frame = Signal()
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._springs: list[Spring] = []
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    def add(self, spring: Spring) -> Spring:
        self._springs.append(spring)
        return spring

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        dt = _TICK_MS / 1000
        for spring in self._springs:
            spring.step(dt)
        self.frame.emit()
        if all(s.settled for s in self._springs):
            self._timer.stop()
            self.finished.emit()
