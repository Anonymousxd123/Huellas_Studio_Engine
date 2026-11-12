from pathlib import Path


def resolve_episode_dir(value, root):
    """Resolve an episode ID or directory relative to the repository root."""
    root = Path(root).expanduser().resolve()
    candidate = Path(value).expanduser()

    if candidate.is_absolute():
        candidates = [candidate]
    else:
        candidates = [
            root / candidate,
            root / "projects" / candidate
        ]

    for path in candidates:
        path = path.resolve()
        if path.is_dir() and (path / "episode.json").is_file():
            return path

    searched = ", ".join(str(path.resolve()) for path in candidates)
    raise FileNotFoundError(
        f"No se encontró episode.json para '{value}'. Rutas revisadas: {searched}"
    )
