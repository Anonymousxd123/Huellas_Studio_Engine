"""Keyframed motion curves with animation easing."""

import math
from dataclasses import dataclass, field

EASINGS = {
    "linear": lambda t: t,
    "hold": lambda t: 0.0,
    "ease_in": lambda t: t * t * t,
    "ease_out": lambda t: 1.0 - (1.0 - t) ** 3,
    # Smootherstep: zero velocity and acceleration at both ends.
    "ease_in_out": lambda t: t * t * t * (t * (6.0 * t - 15.0) + 10.0),
    # Ease out with a small overshoot that settles (cartoon follow-through).
    "back_out": lambda t: 1.0 + 2.2 * (t - 1.0) ** 3 + 1.2 * (t - 1.0) ** 2,
}


@dataclass
class Track:
    """Keys are (time_seconds, value, easing_into_this_key)."""

    keys: list = field(default_factory=list)
    sine: dict | None = None  # {"amplitude", "period", "phase"} added on top

    def __post_init__(self):
        times = [k[0] for k in self.keys]
        if times != sorted(times):
            raise ValueError("Las claves deben estar ordenadas por tiempo")
        for key in self.keys:
            if len(key) > 2 and key[2] not in EASINGS:
                raise ValueError(f"Easing desconocido: {key[2]}")

    @classmethod
    def from_dict(cls, data):
        return cls(
            keys=[tuple(k) for k in data.get("keys", [])],
            sine=data.get("sine"),
        )

    def value(self, t):
        result = 0.0
        if self.keys:
            if t <= self.keys[0][0]:
                result = self.keys[0][1]
            elif t >= self.keys[-1][0]:
                result = self.keys[-1][1]
            else:
                for (t0, v0, *_), (t1, v1, *rest) in zip(self.keys, self.keys[1:]):
                    if t0 <= t <= t1:
                        easing = EASINGS[rest[0] if rest else "ease_in_out"]
                        u = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                        result = v0 + (v1 - v0) * easing(u)
                        break
        if self.sine:
            result += self.sine["amplitude"] * math.sin(
                2.0 * math.pi * t / self.sine["period"]
                + self.sine.get("phase", 0.0)
            )
        return result


def sample_tracks(tracks, t):
    return {name: track.value(t) for name, track in tracks.items()}
