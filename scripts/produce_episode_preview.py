import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from huellas_engine.audio_engine import build_voice_manifest
from huellas_engine.episode_paths import resolve_episode_dir
from huellas_engine.localization_engine import get_languages
from huellas_engine.kokoro_engine import synthesize_episode_audio
from huellas_engine.subtitle_engine import write_subtitles
from huellas_engine.video_engine import render_animatic

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(
        description="Build visual scenes, voice manifests, subtitles and MP4 previews"
    )
    parser.add_argument("--episode", default="episode_001")
    parser.add_argument("--languages", nargs="*",
                        help="Idiomas; por defecto todos los habilitados")
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--assets-dir")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--force-backgrounds", action="store_true")
    parser.add_argument("--skip-visuals", action="store_true",
                        help="Reuse existing composed scene images")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--with-voice", action="store_true",
                        help="Genera voces reales con Kokoro local antes del MP4")
    parser.add_argument("--tts-device", choices=["auto", "cpu", "mps", "cuda"],
                        default="auto")
    parser.add_argument("--force-voice", action="store_true",
                        help="Regenera los WAV aunque ya existan")
    args = parser.parse_args()

    ffmpeg = shutil.which(args.ffmpeg)
    if ffmpeg is None:
        raise FileNotFoundError(
            f"No se encontró FFmpeg ('{args.ffmpeg}'). Instálalo antes de producir."
        )

    episode_dir = resolve_episode_dir(args.episode, ROOT)
    episode = json.loads(
        (episode_dir / "episode.json").read_text(encoding="utf-8")
    )
    languages = args.languages or get_languages(episode_dir)

    if args.skip_visuals:
        missing = [
            episode_dir / "scenes" / scene["scene_id"] / "composed"
            / f"{scene['scene_id']}_composed.png"
            for scene in episode["scenes"]
            if not (
                episode_dir / "scenes" / scene["scene_id"] / "composed"
                / f"{scene['scene_id']}_composed.png"
            ).is_file()
        ]
        if missing:
            raise FileNotFoundError(
                "Faltan escenas compuestas: "
                + ", ".join(str(path) for path in missing)
            )
    else:
        command = [
            sys.executable,
            str(ROOT / "scripts" / "run_episode_composite.py"),
            "--episode", args.episode,
            "--url", args.url
        ]
        if args.assets_dir:
            command.extend(["--assets-dir", args.assets_dir])
        if args.seed is not None:
            command.extend(["--seed", str(args.seed)])
        if args.force_backgrounds:
            command.append("--force")
        subprocess.run(command, check=True, cwd=ROOT)

    print("\nPREPARANDO VOZ Y SUBTÍTULOS")
    for language in languages:
        if args.with_voice:
            voice_result = synthesize_episode_audio(
                episode_dir=episode_dir,
                language=language,
                profile_path=ROOT / "config" / "tts" / "voice_profiles.json",
                force=args.force_voice,
                device=args.tts_device
            )
            print(
                f"[OK] {language}: {voice_result['generated_jobs']} audios "
                f"generados, {voice_result['reused_jobs']} reutilizados"
            )
            print("Mezcla de voz:", voice_result["mix_path"])
        else:
            voice_path, manifest = build_voice_manifest(episode_dir, language)
            print(
                f"[OK] {language}: {manifest['total_jobs']} trabajos de voz "
                "preparados (sin síntesis)"
            )
            print("Manifiesto:", voice_path)

        subtitle_paths = write_subtitles(
            episode_dir, languages=[language]
        )
        print("Archivos de subtítulos:", len(subtitle_paths))

    print("\nRENDERIZANDO ANIMATICS")
    for language in languages:
        output = render_animatic(
            episode_dir,
            language,
            ffmpeg=ffmpeg
        )
        print(f"[OK] {language}: {output}")

    print("\nPAQUETE DE PREVISUALIZACIÓN COMPLETADO")
    print("Episodio:", episode["episode_id"])
    print("Idiomas:", ", ".join(languages))
    if args.with_voice:
        print("Audio: voces Kokoro locales incorporadas en final_mix.wav.")
    else:
        print("Audio: pista silenciosa; usa --with-voice para sintetizar Kokoro.")


if __name__ == "__main__":
    main()
