"""Render a whole episode with rig animation, voice and subtitles in one run.

Renders scene chunks in parallel (resumable: finished chunks are reused),
concatenates them without re-encoding, then muxes each language's final mix
and subtitles (same format as the animatic: AAC + mov_text).

Example:
    python scripts/render_episode_animation.py --episode episode_001 --languages es en
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from huellas_engine.character_animation.compositor import (  # noqa: E402
    load_background, place_characters, render_range,
)
from huellas_engine.character_animation.episode import (  # noqa: E402
    build_scene_specs, chunk_ranges, spec_fingerprint,
)

LANGUAGE_TAGS = {"es": "spa", "en": "eng"}
_WORKER_CACHE = {}


def engine_hash():
    files = sorted((ROOT / "src/huellas_engine/character_animation").glob("*.py"))
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def probe_frames(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
             "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return int(out)
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return -1


def render_chunk(job):
    """Worker: render one chunk. Rigs/backgrounds are cached per process."""
    spec, key, start, end, output, crf = job
    if key not in _WORKER_CACHE:
        _WORKER_CACHE.clear()  # one scene at a time keeps memory bounded
        _WORKER_CACHE[key] = (load_background(spec), place_characters(spec))
    background, placed = _WORKER_CACHE[key]
    tmp = Path(str(output) + ".partial.mp4")
    started = time.time()
    render_range(spec, placed, background, start, end, tmp, crf=crf)
    tmp.replace(output)
    return output, end - start, time.time() - started


def concat(chunks, output):
    listing = output.with_suffix(".txt")
    listing.write_text("".join(f"file '{c.resolve()}'\n" for c in chunks), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(output)],
                   check=True)
    listing.unlink()


def mux(video, audio, subtitles, language, duration, output):
    tag = LANGUAGE_TAGS.get(language, language[:3])
    command = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video)]
    maps = ["-map", "0:v:0"]
    if audio.is_file():
        command += ["-i", str(audio)]
        maps += ["-map", "1:a:0"]
    if subtitles.is_file():
        command += ["-i", str(subtitles)]
        maps += ["-map", f"{2 if audio.is_file() else 1}:0"]
    command += maps + ["-c:v", "copy"]
    if audio.is_file():
        command += ["-c:a", "aac", "-b:a", "192k", "-af", "apad",
                    "-metadata:s:a:0", f"language={tag}"]
    if subtitles.is_file():
        command += ["-c:s", "mov_text", "-metadata:s:s:0", f"language={tag}"]
    command += ["-t", f"{duration:.3f}", "-movflags", "+faststart", str(output)]
    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", default="episode_001")
    parser.add_argument("--languages", nargs="+", default=["es", "en"])
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 3))
    parser.add_argument("--chunk-seconds", type=float, default=10.0)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--scenes", nargs="*", help="Render only these scenes (preview)")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    episode_dir = ROOT / "projects" / args.episode
    out = Path(args.out) if args.out else episode_dir / "animation" / "episode_rig_v1"
    out.mkdir(parents=True, exist_ok=True)
    engine = engine_hash()

    jobs, plan = [], {}
    for language in args.languages:
        specs = build_scene_specs(episode_dir, language, ROOT)
        if args.scenes:
            specs = [s for s in specs if s[0] in args.scenes]
        plan[language] = []
        for scene_id, start, spec in specs:
            key = f"{language}-{scene_id}-{spec_fingerprint(spec, engine)}"
            chunk_dir = out / "chunks" / language / key
            chunk_dir.mkdir(parents=True, exist_ok=True)
            frames = round(spec.duration * spec.fps)
            chunks = []
            for a, b in chunk_ranges(frames, round(args.chunk_seconds * spec.fps)):
                path = chunk_dir / f"{scene_id}_{a:05d}_{b:05d}.mp4"
                chunks.append(path)
                if path.is_file() and probe_frames(path) == b - a:
                    continue
                jobs.append((spec, key, a, b, path, args.crf))
            plan[language].append({"scene_id": scene_id, "start": start,
                                   "duration": spec.duration, "chunks": chunks,
                                   "background": str(spec.background), "key": key})

    total_frames = sum(j[3] - j[2] for j in jobs)
    print(f"Fragmentos pendientes: {len(jobs)} ({total_frames} fotogramas), "
          f"trabajadores: {args.workers}", flush=True)
    started = time.time()
    done_frames = 0
    if jobs:
        # Group jobs by scene so each worker reuses its prepared rigs.
        jobs.sort(key=lambda j: (j[1], j[2]))
        env_threads = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                       "VECLIB_MAXIMUM_THREADS": "1"}
        os.environ.update(env_threads)
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(render_chunk, job) for job in jobs]
            for future in as_completed(futures):
                path, frames, seconds = future.result()
                done_frames += frames
                elapsed = time.time() - started
                eta = elapsed / done_frames * (total_frames - done_frames)
                print(f"  {done_frames}/{total_frames} fotogramas  "
                      f"{elapsed / 60:.1f} min  ETA {eta / 60:.1f} min  ({path.name})",
                      flush=True)

    results = {}
    for language, scenes in plan.items():
        chunks = [c for scene in scenes for c in scene["chunks"]]
        duration = sum(scene["duration"] for scene in scenes)
        video = out / f"{args.episode}_{language}_video.mp4"
        concat(chunks, video)
        final = out / f"{args.episode}_rig_{language}.mp4"
        mux(video, episode_dir / "audio" / language / "final_mix.wav",
            episode_dir / "subtitles" / f"{language}.srt", language, duration, final)
        video.unlink()
        results[language] = {"output": str(final), "duration": duration,
                             "frames": probe_frames(final)}
        print(f"OK {final}  ({duration:.0f}s, {results[language]['frames']} fotogramas)")

    manifest = {
        "episode": args.episode, "engine_hash": engine,
        "render_minutes": round((time.time() - started) / 60, 1),
        "results": results,
        "scenes": {lang: [{k: (str(v) if k != "chunks" else len(v)) for k, v in s.items()}
                          for s in scenes] for lang, scenes in plan.items()},
    }
    (out / "episode_render_manifest.json").write_text(json.dumps(manifest, indent=2),
                                                     encoding="utf-8")


if __name__ == "__main__":
    main()
