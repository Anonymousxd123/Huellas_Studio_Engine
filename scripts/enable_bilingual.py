import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EPISODE_DIR = ROOT / "projects/episode_001"
EPISODE_FILE = EPISODE_DIR / "episode.json"
LOCALES = EPISODE_DIR / "locales"

EN = {
    "episode": {
        "title": "6 Things Your Dog and Cat Do That You Probably Misinterpret",
        "description": "Discover six surprising behaviors of dogs and cats, what they may mean, and how to understand your pets better."
    },
    "scenes": {
        "SC001": {
            "title": "The Mystery of Our Pets",
            "narration": "Does your cat follow you into the bathroom? Does your dog tilt its head when you talk? And why does your cat knock a glass off the table while looking straight at you? They're not necessarily crazy, and they're not always trying to ruin your life. Today we'll discover six pet behaviors you may have misunderstood.",
            "dialogue": [
                {"character": "dog", "text": "I'm just trying to understand humans."},
                {"character": "cat", "text": "Then start by understanding why they need to close the bathroom door."}
            ]
        },
        "SC002": {
            "title": "The Cat Who Follows You to the Bathroom",
            "narration": "Cats may follow us because they want company, attention, food, or simply because they're curious. They also learn our routines and take advantage of moments when we're still to interact with us.",
            "dialogue": [
                {"character": "dog", "text": "That's friendship! I follow my human everywhere too."},
                {"character": "cat", "text": "You only follow them because you heard a snack bag opening."}
            ]
        },
        "SC003": {
            "title": "Why Dogs Tilt Their Heads",
            "narration": "Dogs may tilt their heads when they hear sounds or voices. One possible explanation is that they're trying to process auditory information or adjust their visual perspective. There isn't one explanation that applies to every dog.",
            "dialogue": [
                {"character": "dog", "text": "You talk for twenty minutes and still haven't said the word walk."},
                {"character": "cat", "text": "I tilt my head when I hear a can opening."}
            ]
        },
        "SC004": {
            "title": "The Cat Who Knocks Everything Off the Table",
            "narration": "Cats have natural exploration and hunting instincts. Batting objects helps them investigate how things move. They may also do it out of boredom or because they've learned that knocking something over gets attention.",
            "dialogue": [
                {"character": "dog", "text": "That's vandalism!"},
                {"character": "cat", "text": "No. It's scientific research."}
            ]
        },
        "SC005": {
            "title": "The Dog Who Greets You with a Toy",
            "narration": "Many dogs greet their humans with their favorite toys. It may be a sign of excitement, an invitation to play, or a way to share a moment of interaction.",
            "dialogue": [
                {"character": "dog", "text": "You're back! I have something for you!"},
                {"character": "cat", "text": "And where is my present?"},
                {"character": "dog", "text": "You have a whole box of toys and you play with a receipt."}
            ]
        },
        "SC006": {
            "title": "The Cat Who Makes Biscuits",
            "narration": "Kittens make this kneading motion while nursing to stimulate milk flow. Many cats keep the behavior as adults. It may be associated with comfort, relaxation, and instinctive behavior.",
            "dialogue": [
                {"character": "dog", "text": "So, is the cat making biscuits?"},
                {"character": "cat", "text": "Yes. And I'm not sharing them with you."}
            ]
        },
        "SC007": {
            "title": "The Cat's Slow Blink",
            "narration": "Cats can communicate through slow blinking. Research has found positive responses to this signal during cat-human interactions. You can try it by looking calmly at your cat, slowly closing your eyes, and opening them again.",
            "dialogue": [
                {"character": "dog", "text": "I can do that too!"},
                {"character": "cat", "text": "That doesn't count. You fell asleep."}
            ]
        },
        "SC008": {
            "title": "The Takeaway and Goodbye",
            "narration": "Now you know that many things our pets do have interesting explanations. Every animal has its own personality. The more we learn about them, the better we can understand and care for them. Tell us which of these behaviors your pet does. This was Ah Mira Ese Dato. See you in the next episode!",
            "dialogue": [
                {"character": "dog", "text": "I just want to walk, play, and eat."},
                {"character": "cat", "text": "And I want everyone to respect my privacy."}
            ]
        }
    }
}


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def main():
    if not EPISODE_FILE.exists():
        raise FileNotFoundError(EPISODE_FILE)

    LOCALES.mkdir(parents=True, exist_ok=True)

    episode = json.loads(EPISODE_FILE.read_text(encoding="utf-8"))

    # Evitar sobrescribir una migración ya realizada.
    if (LOCALES / "es.json").exists() and all(
        "narration" not in scene
        for scene in episode.get("scenes", [])
    ):
        print("El episodio ya está migrado. No se modificó.")
        return

    # Backup antes de modificar el episodio.
    backup = EPISODE_DIR / "episode.json.backup"
    if not backup.exists():
        shutil.copy2(EPISODE_FILE, backup)

    spanish = {
        "language": "es",
        "episode": {
            "title": episode["title"],
            "description": (
                "Descubre seis comportamientos sorprendentes "
                "de perros y gatos y aprende a entender mejor "
                "a tus mascotas."
            )
        },
        "scenes": {}
    }

    for scene in episode["scenes"]:
        scene_id = scene["scene_id"]

        if scene_id not in EN["scenes"]:
            raise ValueError(f"Falta traducción inglesa para {scene_id}")

        spanish["scenes"][scene_id] = {
            "title": scene["title"],
            "narration": scene["narration"],
            "dialogue": scene["dialogue"]
        }

        # Los datos visuales permanecen en el episodio maestro.
        scene.pop("title", None)
        scene.pop("narration", None)
        scene.pop("dialogue", None)

    english = {
        "language": "en",
        "episode": EN["episode"],
        "scenes": EN["scenes"]
    }

    episode.pop("language", None)
    episode["default_language"] = "es"
    episode["supported_languages"] = ["es", "en"]
    episode["shared_visual_assets"] = True
    episode["localization_strategy"] = "shared_visuals_separate_audio"

    save_json(LOCALES / "es.json", spanish)
    save_json(LOCALES / "en.json", english)
    save_json(EPISODE_FILE, episode)

    print("MIGRACIÓN BILINGÜE COMPLETADA")
    print("Backup:", backup)
    print("Idiomas: español e inglés")
    print("Escenas:", len(episode["scenes"]))
    print("Visuales compartidos: sí")


if __name__ == "__main__":
    main()
