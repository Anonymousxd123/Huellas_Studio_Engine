import json
import shutil
import subprocess
from pathlib import Path

from .subtitle_engine import write_subtitles


def build_animatic_command(
    episode_dir,
    language,
    output_path=None,
    ffmpeg="ffmpeg",
    fps=24,
    width=1920,
    height=1080,
    allow_silent=True
):
    episode_dir = Path(episode_dir)
    if fps <= 0 or width <= 0 or height <= 0:
        raise ValueError("FPS y resolución deben ser positivos")

    ffmpeg_path = shutil.which(ffmpeg)
    if ffmpeg_path is None:
        raise FileNotFoundError(
            f"No se encontró FFmpeg ('{ffmpeg}') en PATH"
        )

    episode = json.loads(
        (episode_dir / "episode.json").read_text(encoding="utf-8")
    )
    scenes = episode.get("scenes", [])
    if not scenes:
        raise ValueError("El episodio no contiene escenas")

    inputs = []
    durations = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        duration = float(scene["duration_seconds"])
        if duration <= 0:
            raise ValueError(f"Duración inválida en {scene_id}")

        image = (
            episode_dir / "scenes" / scene_id / "composed"
            / f"{scene_id}_composed.png"
        )
        if not image.is_file():
            raise FileNotFoundError(
                f"Falta la composición estática de {scene_id}: {image}"
            )
        inputs.append(image)
        durations.append(duration)

    total_duration = sum(durations)
    output_path = Path(
        output_path or (
            episode_dir / "renders" / f"animatic_{language}.mp4"
        )
    ).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    subtitle_path = episode_dir / "subtitles" / f"{language}.srt"
    if not subtitle_path.is_file():
        write_subtitles(episode_dir, languages=[language])
    if not subtitle_path.is_file():
        raise FileNotFoundError(subtitle_path)

    audio_path = episode_dir / "audio" / language / "final_mix.wav"
    has_audio = audio_path.is_file()
    if not has_audio and not allow_silent:
        raise FileNotFoundError(
            f"No existe mezcla de voz: {audio_path}"
        )

    command = [ffmpeg_path, "-y"]
    for image, duration in zip(inputs, durations):
        command.extend([
            "-loop", "1",
            "-framerate", str(fps),
            "-t", f"{duration:.3f}",
            "-i", str(image)
        ])

    filters = []
    video_labels = []
    for index in range(len(inputs)):
        label = f"v{index}"
        filters.append(
            f"[{index}:v]"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps={fps},format=yuv420p[{label}]"
        )
        video_labels.append(f"[{label}]")

    filters.append(
        "".join(video_labels)
        + f"concat=n={len(inputs)}:v=1:a=0[vout]"
    )
    command.extend(["-filter_complex", ";".join(filters), "-map", "[vout]"])

    next_input = len(inputs)
    if has_audio:
        command.extend(["-i", str(audio_path)])
        command.extend([
            "-map", f"{next_input}:a:0",
            "-af", "apad",
            "-t", f"{total_duration:.3f}",
            "-c:a", "aac",
            "-b:a", "192k"
        ])
    elif allow_silent:
        command.extend([
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-map", f"{next_input}:a:0",
            "-t", f"{total_duration:.3f}",
            "-c:a", "aac",
            "-b:a", "192k"
        ])

    subtitle_input = next_input + 1
    command.extend(["-i", str(subtitle_path)])
    command.extend([
        "-map", f"{subtitle_input}:0",
        "-c:s", "mov_text",
        "-metadata:s:s:0", f"language={language[:3]}",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path)
    ])
    return command


def render_animatic(*args, **kwargs):
    command = build_animatic_command(*args, **kwargs)
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False
    )
    if result.returncode != 0:
        raise RuntimeError(
            "FFmpeg no pudo renderizar el animatic:\n"
            + (result.stderr[-6000:] if result.stderr else "Sin detalles")
        )
    return Path(command[-1])
