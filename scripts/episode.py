import argparse
from pathlib import Path

from huellas_engine.scene_engine import (
    create_episode,
    load_episode,
    validate_episode,
    build_storyboard
)

ROOT = Path(__file__).resolve().parents[1]


def main():

    parser = argparse.ArgumentParser("Huellas Episode Manager")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new")
    new.add_argument("--id", required=True)
    new.add_argument("--title", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--episode", required=True)

    storyboard = sub.add_parser("storyboard")
    storyboard.add_argument("--episode", required=True)

    args = parser.parse_args()

    if args.command == "new":

        path = create_episode(
            ROOT, args.id, args.title
        )

        print("EPISODIO CREADO:", path)

    elif args.command == "validate":

        episode = load_episode(args.episode)
        errors = validate_episode(episode)

        if errors:
            print("ERRORES:")
            for error in errors:
                print("-", error)
        else:
            print("EPISODIO VALIDADO")

    elif args.command == "storyboard":

        path = build_storyboard(args.episode)
        print("STORYBOARD GENERADO:", path)


if __name__ == "__main__":
    main()