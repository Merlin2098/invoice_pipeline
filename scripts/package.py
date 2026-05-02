from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = REPO_ROOT / "artifacts" / "data_platform_bundle.zip"
INCLUDE_DIRS = [REPO_ROOT / "src"]


def build_bundle() -> Path:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(ARTIFACT_PATH, "w", compression=ZIP_DEFLATED) as archive:
        for directory in INCLUDE_DIRS:
            for file_path in sorted(directory.rglob("*")):
                if file_path.is_dir() and file_path.name == "__pycache__":
                    continue
                if file_path.suffix == ".pyc":
                    continue
                if "__pycache__" in file_path.parts:
                    continue
                if file_path.is_file():
                    archive.write(file_path, file_path.relative_to(REPO_ROOT))
        archive.write(REPO_ROOT / "requirements.txt", "requirements.txt")
    return ARTIFACT_PATH


def clean_bundle() -> None:
    if ARTIFACT_PATH.exists():
        ARTIFACT_PATH.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or remove the deployment bundle."
    )
    parser.add_argument(
        "--clean", action="store_true", help="Remove the generated bundle."
    )
    args = parser.parse_args()

    if args.clean:
        clean_bundle()
        return

    artifact = build_bundle()
    print(artifact)


if __name__ == "__main__":
    main()
