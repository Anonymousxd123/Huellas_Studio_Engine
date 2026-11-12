import hashlib
import json
from pathlib import Path

from .database import connect_db

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def sha256_file(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def resolve_path(value, root):
    path = Path(value).expanduser()

    if path.is_absolute():
        return path.resolve()

    return (root / path).resolve()


def register_asset(conn, path, profile=None, generation_id=None):
    path = Path(path).resolve()

    if not path.is_file():
        return False

    digest = sha256_file(path)

    conn.execute("""
        INSERT INTO assets
        (path, filename, sha256, profile, size_bytes, generation_id)
        VALUES (?, ?, ?, ?, ?, ?)

        ON CONFLICT(path) DO UPDATE SET
            sha256=excluded.sha256,
            profile=COALESCE(excluded.profile, assets.profile),
            generation_id=COALESCE(
                excluded.generation_id,
                assets.generation_id
            )
    """, (
        str(path),
        path.name,
        digest,
        profile,
        path.stat().st_size,
        generation_id
    ))

    return True


def normalize_manifest(data):
    """
    Admite:
    1. Lista de resultados: [{seed, prompt_id, images}]
    2. Objeto: {profile, results: [...]}
    """

    if isinstance(data, list):
        return {}, data

    if isinstance(data, dict):
        results = data.get("results", [])

        if not isinstance(results, list):
            raise ValueError("El campo results debe ser una lista")

        return data, results

    raise ValueError(
        f"Formato de manifiesto no compatible: {type(data).__name__}"
    )


def catalog_projects(root="."):
    root = Path(root).resolve()
    projects_dir = root / "projects"

    conn = connect_db(root / "data/huellas.db")

    manifests = list(projects_dir.rglob("*_manifest.json"))

    processed = set()
    missing = []
    generations_added = 0

    for manifest_path in manifests:

        print(f"\nProcesando: {manifest_path}")

        data = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )

        metadata, results = normalize_manifest(data)

        profile_value = metadata.get("profile")

        if profile_value:
            profile = Path(str(profile_value)).stem
        else:
            profile = manifest_path.parent.parent.name

        for result in results:

            if not isinstance(result, dict):
                continue

            prompt_id = result.get("prompt_id")
            generation_id = None

            if prompt_id:

                cursor = conn.execute("""
                    INSERT OR IGNORE INTO generations
                    (prompt_id, profile, seed, manifest_path)
                    VALUES (?, ?, ?, ?)
                """, (
                    prompt_id,
                    profile,
                    result.get("seed"),
                    str(manifest_path)
                ))

                generations_added += cursor.rowcount

                generation = conn.execute(
                    "SELECT id FROM generations WHERE prompt_id = ?",
                    (prompt_id,)
                ).fetchone()

                generation_id = generation["id"]

            for image in result.get("images", []):

                image_path = resolve_path(image, root)

                if not image_path.is_file():
                    missing.append(str(image_path))
                    continue

                register_asset(
                    conn,
                    image_path,
                    profile,
                    generation_id
                )

                processed.add(str(image_path))

    # Detectar imágenes que no estén referenciadas en manifiestos.
    for path in projects_dir.rglob("*"):

        if not path.is_file():
            continue

        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        profile = path.parent.parent.name

        register_asset(conn, path, profile)
        processed.add(str(path.resolve()))

    conn.commit()

    total_assets = conn.execute(
        "SELECT COUNT(*) FROM assets"
    ).fetchone()[0]

    total_generations = conn.execute(
        "SELECT COUNT(*) FROM generations"
    ).fetchone()[0]

    profile_summary = conn.execute("""
        SELECT profile, COUNT(*) AS total
        FROM assets
        GROUP BY profile
        ORDER BY profile
    """).fetchall()

    conn.close()

    return {
        "manifests_found": len(manifests),
        "new_generations": generations_added,
        "assets_processed": len(processed),
        "missing_files": missing,
        "total_assets": total_assets,
        "total_generations": total_generations,
        "by_profile": [
            dict(row) for row in profile_summary
        ]
    }
