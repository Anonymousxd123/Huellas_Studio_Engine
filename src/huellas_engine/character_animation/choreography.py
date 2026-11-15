"""Procedural, deterministic choreography from an episode's audio timeline.

Every gesture starts and ends at the neutral pose (angle 0), so gestures can
be scheduled back to back without discontinuities. Angles stay inside the
ranges validated for each rig (see docs/character_animation_engine.md).
"""

import random
from dataclasses import dataclass, field

from .motion import Track

# Validated ranges (degrees). Positive = top of head toward the viewer's left.
LIMITS = {"dog": (-5.0, 12.0), "cat": (-4.0, 10.0)}
IDLE_SWAY = {"dog": (0.6, 6.3, 0.0), "cat": (0.7, 5.1, 1.7)}  # amp, period, phase
BREATH = {"dog": (0.004, 2.6, 0.0), "cat": (0.005, 2.1, 1.0)}
MIN_GAP = 0.6  # seconds between consecutive gestures of one character


@dataclass
class Timeline:
    """Gesture keys for one character inside one scene (scene-relative time)."""

    role: str
    duration: float
    keys: list = field(default_factory=lambda: [(0.0, 0.0)])
    busy_until: float = 0.0

    def clamp(self, value):
        low, high = LIMITS[self.role]
        return max(low, min(high, value))

    def free_at(self, start, end):
        return start >= self.busy_until + MIN_GAP and end <= self.duration - 0.3

    def add(self, start, points):
        """points: [(dt, value, easing)], relative to start; must end at 0."""
        if points[-1][1] != 0.0:
            raise ValueError("Un gesto debe terminar en la pose neutra")
        self.keys.append((start, 0.0, "hold"))
        for dt, value, easing in points:
            self.keys.append((start + dt, self.clamp(value), easing))
        self.busy_until = start + points[-1][0]

    def track(self):
        keys = sorted(self.keys, key=lambda k: k[0])
        amp, period, phase = IDLE_SWAY[self.role]
        return Track(keys=keys, sine={"amplitude": amp, "period": period, "phase": phase})


def curious_tilt(peak, hold=1.0):
    return [
        (0.3, -1.0, "ease_in_out"),
        (1.4, peak, "ease_in_out_back"),
        (1.4 + hold, peak, "hold"),
        (2.6 + hold, 0.0, "ease_in_out"),
    ]


def talk_bob(duration, rng):
    """Head beats while speaking: small alternating nods around a slight tilt."""
    points = [(0.35, 3.0, "ease_in_out")]
    t = 0.35
    high = True
    while t + 0.9 < duration:
        t += rng.uniform(0.38, 0.55)
        points.append((t, 4.5 if high else 1.0, "ease_in_out"))
        high = not high
    points.append((max(t + 0.5, duration + 0.2), 0.0, "ease_in_out"))
    return points


def listen_tilt(duration, peak):
    hold = max(0.2, duration - 1.6)
    return [
        (0.6, peak, "ease_in_out_back"),
        (0.6 + hold, peak, "hold"),
        (1.6 + hold, 0.0, "ease_in_out"),
    ]


def _imitation(dog, cat, start, rng):
    """SC003 signature beat: Akira tilts, Daniela copies him a beat later."""
    dog_points = curious_tilt(rng.uniform(10.5, 12.0), hold=1.6)
    cat_start = start + 2.6
    cat_points = curious_tilt(rng.uniform(8.0, 9.5), hold=1.3)
    if dog.free_at(start, start + dog_points[-1][0]) and cat.free_at(
        cat_start, cat_start + cat_points[-1][0]
    ):
        dog.add(start, dog_points)
        cat.add(cat_start, cat_points)
        return True
    return False


def scene_tracks(scene, cues, seed=2026):
    """Return {"dog": {joint: Track}, "cat": {...}} for one scene.

    `cues` are this scene's timeline cues with absolute times; `scene` carries
    scene_id, start (absolute seconds) and duration_seconds.
    """
    scene_id = scene["scene_id"]
    start = scene["start"]
    duration = float(scene["duration_seconds"])
    rng = random.Random(f"{seed}-{scene_id}")
    dog = Timeline("dog", duration)
    cat = Timeline("cat", duration)
    roles = {"dog": dog, "cat": cat}

    dialogue = sorted(
        (c for c in cues if c["kind"] == "dialogue" and c["speaker_id"] in roles),
        key=lambda c: c["start"],
    )
    # Narration first (chronological scheduling): gestures before the first
    # dialogue line; dialogue reactions are added afterwards.
    narration_end = (dialogue[0]["start"] - start - 0.8) if dialogue else duration - 1.0
    t = rng.uniform(1.2, 2.5)
    turn = rng.choice(["dog", "cat"])
    while t < narration_end - 4.0:
        if scene_id == "SC003" and _imitation(dog, cat, t, rng):
            t += 10.0 + rng.uniform(1.0, 3.0)
            continue
        actor = roles[turn]
        peak = rng.uniform(6.0, 11.0) if turn == "dog" else rng.uniform(5.0, 9.0)
        if scene_id == "SC008":
            peak *= 0.6  # calm ending
        points = curious_tilt(peak, hold=rng.uniform(0.8, 1.6))
        if actor.free_at(t, t + points[-1][0]) and t + points[-1][0] < narration_end:
            actor.add(t, points)
            # Occasionally the other one echoes the gesture a beat later.
            other = cat if actor is dog else dog
            echo_t = t + 2.2
            echo = curious_tilt(peak * 0.55, hold=0.6)
            if rng.random() < 0.4 and other.free_at(echo_t, echo_t + echo[-1][0]) \
                    and echo_t + echo[-1][0] < narration_end:
                other.add(echo_t, echo)
        turn = "cat" if turn == "dog" else "dog"
        t += rng.uniform(7.0, 11.0)

    for cue in dialogue:
        t0 = cue["start"] - start
        length = cue["end"] - cue["start"]
        speaker = roles[cue["speaker_id"]]
        listener = cat if speaker is dog else dog
        bob = talk_bob(length, rng)
        bob_start = max(0.0, t0 - 0.1)
        if speaker.free_at(bob_start, bob_start + bob[-1][0]):
            speaker.add(bob_start, bob)
        listen = listen_tilt(length, 5.0 if listener is dog else 4.0)
        lt0 = t0 + 0.3
        if listener.free_at(lt0, lt0 + listen[-1][0]):
            listener.add(lt0, listen)

    result = {}
    for role, timeline in roles.items():
        amp, period, phase = BREATH[role]
        result[role] = {
            "head": timeline.track(),
            "breath": Track(sine={"amplitude": amp, "period": period, "phase": phase}),
        }
    return result
