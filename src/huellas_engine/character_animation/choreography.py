"""Procedural, deterministic choreography from an episode's audio timeline.

Every gesture starts and ends at its track's neutral value, so gestures can
be scheduled back to back without discontinuities. Values stay inside the
ranges validated for each rig (see docs/character_animation_engine.md).
"""

import random
from dataclasses import dataclass, field

from .motion import Track

MIN_GAP = 0.6  # seconds between consecutive gestures on one track
MIN_SHOT = 1.5  # shortest allowed shot, seconds

# Per role and track: (low, high) validated limits, neutral value, idle sine.
# Head/tail/lean in degrees (positive = counter-clockwise on screen); lift as
# a fraction of the character's height. Akira's tail and lean are one-sided
# so the cropped edges of his source art always move off-frame, never in.
TRACKS = {
    "dog": {
        "head": ((-5.0, 12.0), 0.0, (0.6, 6.3, 0.0)),
        "tail": ((0.0, 12.0), 2.0, (1.2, 3.3, 0.4)),
        "lift": ((0.0, 0.025), 0.0, None),
        "lean": ((0.0, 3.0), 0.0, None),
        "blink": ((0.0, 1.0), 0.0, None),
    },
    "cat": {
        "head": ((-4.0, 10.0), 0.0, (0.7, 5.1, 1.7)),
        "tail": ((-10.0, 10.0), 0.0, (4.0, 4.2, 0.0)),
        "lift": ((0.0, 0.04), 0.0, None),
        "lean": ((-3.0, 3.0), 0.0, None),
        "blink": ((0.0, 1.0), 0.0, None),
    },
}
LIMITS = {role: tracks["head"][0] for role, tracks in TRACKS.items()}
IDLE_SWAY = {role: tracks["head"][2] for role, tracks in TRACKS.items()}
BREATH = {"dog": (0.004, 2.6, 0.0), "cat": (0.005, 2.1, 1.0)}


@dataclass
class Timeline:
    """Gesture keys for one track of one character (scene-relative time)."""

    limits: tuple
    neutral: float
    sine: tuple | None
    duration: float
    keys: list = field(default_factory=list)
    busy_until: float = -10.0

    def __post_init__(self):
        if not self.keys:
            self.keys = [(0.0, self.neutral)]

    def clamp(self, value):
        low, high = self.limits
        return max(low, min(high, value))

    def free_at(self, start, end):
        return start >= self.busy_until + MIN_GAP and end <= self.duration - 0.3

    def add(self, start, points):
        """points: [(dt, value, easing)] relative to start, ending at neutral."""
        if points[-1][1] != self.neutral:
            raise ValueError("Un gesto debe terminar en el valor neutro")
        self.keys.append((start, self.neutral, "hold"))
        for dt, value, easing in points:
            self.keys.append((start + dt, self.clamp(value), easing))
        self.busy_until = start + points[-1][0]

    def try_add(self, start, points):
        if self.free_at(start, start + points[-1][0]):
            self.add(start, points)
            return True
        return False

    def track(self):
        keys = sorted(self.keys, key=lambda k: k[0])
        sine = None
        if self.sine:
            amp, period, phase = self.sine
            sine = {"amplitude": amp, "period": period, "phase": phase}
        return Track(keys=keys, sine=sine)


def _timelines(role, duration):
    return {
        name: Timeline(limits, neutral, sine, duration)
        for name, (limits, neutral, sine) in TRACKS[role].items()
    }


# --- gesture shapes -------------------------------------------------------

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


def wag(duration, low, high, neutral, beat=0.24):
    """Tail wag: alternate between low/high every `beat` s, back to neutral."""
    points, t, up = [], 0.0, True
    while t + beat < duration:
        t += beat
        points.append((t, high if up else low, "ease_in_out"))
        up = not up
    points.append((t + 0.4, neutral, "ease_in_out"))
    return points


def flick(amount):
    return [(0.25, amount, "ease_in_out"), (0.85, 0.0, "ease_in_out")]


def quick_blink():
    return [(0.07, 1.0, "ease_in"), (0.11, 1.0, "hold"), (0.25, 0.0, "ease_out")]


def slow_blink(hold=0.8):
    """The cat 'I trust you' blink: slow close, hold, slow open."""
    return [(0.65, 1.0, "ease_in_out"), (0.65 + hold, 1.0, "hold"),
            (1.45 + hold, 0.0, "ease_in_out")]


def _schedule_blinks(timeline, special, rng, duration):
    """Slow blinks as given; natural quick blinks every ~3-5 s, kept clear of them."""
    events = list(special)
    t = rng.uniform(0.8, 2.5)
    while t < duration - 1.0:
        if all(abs(t - start) >= 1.5 for start, _ in special):
            events.append((t, quick_blink()))
        t += rng.uniform(2.8, 5.5)
    for start, points in sorted(events, key=lambda e: e[0]):
        timeline.try_add(start, points)


def hop(height, count=1, beat=0.34):
    points, t = [], 0.0
    for _ in range(count):
        points.append((t + beat * 0.45, height, "ease_out"))
        points.append((t + beat, 0.0, "ease_in"))
        t += beat
    points[-1] = (points[-1][0] + 0.05, 0.0, "ease_in_out")
    return points


def hold_pose(value, attack, hold, release):
    return [(attack, value, "ease_in_out"), (attack + hold, value, "hold"),
            (attack + hold + release, 0.0, "ease_in_out")]


# --- scheduling ------------------------------------------------------------

def _imitation(dog, cat, start, rng):
    """SC003 signature beat: Akira tilts, Daniela copies him a beat later."""
    dog_points = curious_tilt(rng.uniform(10.5, 12.0), hold=1.6)
    cat_start = start + 2.6
    cat_points = curious_tilt(rng.uniform(8.0, 9.5), hold=1.3)
    if dog["head"].free_at(start, start + dog_points[-1][0]) and cat["head"].free_at(
        cat_start, cat_start + cat_points[-1][0]
    ):
        dog["head"].add(start, dog_points)
        cat["head"].add(cat_start, cat_points)
        cat["lean"].try_add(cat_start + 0.2, hold_pose(1.8, 0.9, 1.4, 1.0))
        return cat_start + cat_points[-1][0]
    return None


def _normalise_shots(shots, duration):
    """Sorted cuts, each shot at least MIN_SHOT long; the scene opens wide."""
    result = [(0.0, "wide")]
    for start, name in sorted(shots):
        if start <= 0.0 or start > duration - MIN_SHOT:
            continue
        last_start, last_name = result[-1]
        if start - last_start < MIN_SHOT:
            if last_start == 0.0:
                start = MIN_SHOT  # keep the opening shot on screen long enough
            else:
                result.pop()  # the newer cut wins over a too-short shot
                last_start, last_name = result[-1]
        if name != result[-1][1]:
            result.append((start, name))
    return result


def scene_tracks(scene, cues, seed=2026):
    """Return {"dog": {track: Track}, "cat": {...}, "shots": [(t, name)]}.

    `cues` are this scene's timeline cues with absolute times; `scene` carries
    scene_id, start (absolute seconds) and duration_seconds.
    """
    scene_id = scene["scene_id"]
    start = scene["start"]
    duration = float(scene["duration_seconds"])
    rng = random.Random(f"{seed}-{scene_id}")
    dog = _timelines("dog", duration)
    cat = _timelines("cat", duration)
    roles = {"dog": dog, "cat": cat}
    shots = [(0.0, "wide")]

    dialogue = sorted(
        (c for c in cues if c["kind"] == "dialogue" and c["speaker_id"] in roles),
        key=lambda c: c["start"],
    )

    # Scene-specific openers.
    if scene_id == "SC005":  # welcoming the human: happy bounces and wagging
        dog["lift"].try_add(1.0, hop(0.02, count=3))
        dog["tail"].try_add(0.8, wag(4.0, 3.0, 11.0, 2.0))
    if scene_id == "SC004":  # the glass: Akira recoils, Daniela's tail flicks
        dog["lift"].try_add(2.0, hop(0.012, count=1, beat=0.4))
        dog["lean"].try_add(2.0, hold_pose(2.5, 0.35, 1.2, 0.8))
        cat["tail"].try_add(1.0, flick(-6.0))
    if scene_id == "SC008":  # warm ending: gentle wag
        dog["tail"].try_add(1.5, wag(3.0, 1.5, 7.0, 2.0, beat=0.34))

    # Narration (chronological): gestures before the first dialogue line.
    narration_end = (dialogue[0]["start"] - start - 0.8) if dialogue else duration - 1.0
    t = rng.uniform(4.5, 6.0) if scene_id in ("SC004", "SC005") else rng.uniform(1.2, 2.5)
    turn = rng.choice(["dog", "cat"])
    beats = 0
    while t < narration_end - 4.0:
        if scene_id == "SC003":
            end = _imitation(dog, cat, t, rng)
            if end is not None:
                if beats % 2 == 1:  # every other beat: close coverage
                    shots += [(t, "dog_medium"), (t + 2.5, "cat_close"), (end + 0.4, "wide")]
                beats += 1
                t = end + rng.uniform(4.0, 6.0)
                continue
        actor = roles[turn]
        other = cat if actor is dog else dog
        peak = rng.uniform(6.0, 11.0) if turn == "dog" else rng.uniform(5.0, 9.0)
        if scene_id == "SC008":
            peak *= 0.6  # calm ending
        points = curious_tilt(peak, hold=rng.uniform(0.8, 1.6))
        if t + points[-1][0] < narration_end and actor["head"].try_add(t, points):
            if turn == "cat":
                actor["tail"].try_add(t + 0.5, flick(rng.choice([-6.0, 6.0])))
            elif rng.random() < 0.5:
                actor["tail"].try_add(t + 1.4, wag(1.6, 2.0, 8.0, 2.0))
            echo_t = t + 2.2
            echo = curious_tilt(peak * 0.55, hold=0.6)
            if rng.random() < 0.4 and echo_t + echo[-1][0] < narration_end:
                other["head"].try_add(echo_t, echo)
        turn = "cat" if turn == "dog" else "dog"
        t += rng.uniform(7.0, 11.0)

    # Dialogue: the speaker beats and gets the shot; the listener reacts.
    for cue in dialogue:
        t0 = cue["start"] - start
        length = cue["end"] - cue["start"]
        speaker_role = cue["speaker_id"]
        speaker = roles[speaker_role]
        listener = cat if speaker is dog else dog
        bob_start = max(0.0, t0 - 0.1)
        speaker["head"].try_add(bob_start, talk_bob(length, rng))
        if speaker_role == "dog":
            speaker["tail"].try_add(t0 + 0.2, wag(min(length, 3.0), 3.0, 10.0, 2.0))
        else:
            speaker["tail"].try_add(t0 + 0.1, flick(-6.0))
        lt0 = t0 + 0.3
        listener["head"].try_add(lt0, listen_tilt(length, 5.0 if listener is dog else 4.0))
        if listener is cat:
            cat["lean"].try_add(lt0, hold_pose(1.5, 0.6, max(0.2, length - 1.2), 0.8))
        shots.append((max(0.0, t0 - 0.15), "dog_medium" if speaker_role == "dog" else "cat_close"))
    if dialogue:
        shots.append((dialogue[-1]["end"] - start + 0.5, "wide"))

    # Blinks: SC007's slow blink (Daniela, then Akira imitates), SC008 calm.
    special = {"dog": [], "cat": []}
    if scene_id == "SC007":
        t = 3.0
        while t < narration_end - 6.0:
            special["cat"].append((t, slow_blink(0.9)))
            special["dog"].append((t + 2.8, slow_blink(0.6)))
            t += rng.uniform(11.0, 14.0)
    if scene_id == "SC008":
        t = 2.0
        turn = "cat"
        while t < duration - 4.0:
            special[turn].append((t, slow_blink(0.5)))
            turn = "dog" if turn == "cat" else "cat"
            t += rng.uniform(6.0, 9.0)
    for role in ("dog", "cat"):
        _schedule_blinks(roles[role]["blink"], special[role], rng, duration)

    result = {"shots": _normalise_shots(shots, duration)}
    for role, timelines in roles.items():
        amp, period, phase = BREATH[role]
        result[role] = {name: tl.track() for name, tl in timelines.items()}
        result[role]["breath"] = Track(sine={"amplitude": amp, "period": period, "phase": phase})
    return result
