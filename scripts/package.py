from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = REPO_ROOT / "artifacts" / "lambda" / "control_plane_bundle.zip"
INCLUDE_DIRS = [REPO_ROOT / "src", REPO_ROOT / "specs"]
CLOUD_REQUIREMENTS = REPO_ROOT / "requirements.cloud.txt"
LAMBDA_REQUIREMENTS = REPO_ROOT / "requirements.lambda.txt"
PYPROJECT = REPO_ROOT / "pyproject.toml"
UV_LOCK = REPO_ROOT / "uv.lock"
VENDORED_MODULES = ("yaml", "dateutil", "six")
LAMBDA_PLATFORM = "manylinux2014_x86_64"
LAMBDA_PYTHON_VERSION = "3.11"


def detect_package_manager(selected: str) -> str:
    if selected != "auto":
        return selected
    if CLOUD_REQUIREMENTS.exists():
        return "pip"
    if PYPROJECT.exists() and UV_LOCK.exists():
        return "uv"
    if PYPROJECT.exists():
        return "uv"
    return "pip"


def runtime_requirements_text(package_manager: str) -> str:
    if LAMBDA_REQUIREMENTS.exists():
        return LAMBDA_REQUIREMENTS.read_text(encoding="utf-8").strip() + "\n"
    if package_manager == "uv":
        result = subprocess.run(
            [
                "uv",
                "export",
                "--no-dev",
                "--extra",
                "cloud",
                "--format",
                "requirements.txt",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    return CLOUD_REQUIREMENTS.read_text(encoding="utf-8").strip() + "\n"


def _module_origin(module_name: str) -> Path:
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        raise RuntimeError(
            f"Could not resolve installed module '{module_name}'. Run the environment setup before packaging."
        )
    if spec.submodule_search_locations:
        return Path(next(iter(spec.submodule_search_locations)))
    return Path(spec.origin)


def add_vendor_dependencies(archive: ZipFile) -> None:
    added: set[Path] = set()
    for module_name in VENDORED_MODULES:
        origin = _module_origin(module_name)
        if origin in added:
            continue
        added.add(origin)
        if origin.is_dir():
            for file_path in sorted(origin.rglob("*")):
                if file_path.is_dir():
                    continue
                if "__pycache__" in file_path.parts or file_path.suffix == ".pyc":
                    continue
                archive.write(file_path, file_path.relative_to(origin.parent))
        else:
            archive.write(origin, origin.name)


def add_dependency_tree(archive: ZipFile, dependency_root: Path) -> None:
    for file_path in sorted(dependency_root.rglob("*")):
        if file_path.is_dir():
            continue
        if "__pycache__" in file_path.parts or file_path.suffix == ".pyc":
            continue
        archive.write(file_path, file_path.relative_to(dependency_root))


def add_lambda_dependencies(archive: ZipFile, requirements_text: str) -> None:
    if not requirements_text.strip():
        add_vendor_dependencies(archive)
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        requirements_path = temp_path / "requirements.txt"
        dependency_root = temp_path / "python"
        requirements_path.write_text(requirements_text, encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--target",
                str(dependency_root),
                "--platform",
                LAMBDA_PLATFORM,
                "--implementation",
                "cp",
                "--python-version",
                LAMBDA_PYTHON_VERSION,
                "--only-binary=:all:",
                "-r",
                str(requirements_path),
            ],
            cwd=REPO_ROOT,
            check=True,
        )
        add_dependency_tree(archive, dependency_root)


def build_bundle(package_manager: str) -> Path:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    requirements_text = runtime_requirements_text(package_manager)
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
        add_lambda_dependencies(archive, requirements_text)
        archive.writestr("requirements.txt", requirements_text)
    return ARTIFACT_PATH


def clean_bundle() -> None:
    if ARTIFACT_PATH.exists():
        try:
            ARTIFACT_PATH.unlink()
        except PermissionError:
            print(
                f"Could not remove {ARTIFACT_PATH} because it is currently in use. Close any process using the bundle and retry.",
                file=sys.stderr,
            )
    build_dir = ARTIFACT_PATH.parent / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or remove the deployment bundle."
    )
    parser.add_argument(
        "--clean", action="store_true", help="Remove the generated bundle."
    )
    parser.add_argument(
        "--package-manager",
        choices=("auto", "pip", "uv"),
        default="auto",
        help="Dependency source to use for the bundled requirements.txt.",
    )
    args = parser.parse_args()

    if args.clean:
        clean_bundle()
        return

    artifact = build_bundle(detect_package_manager(args.package_manager))
    print(artifact)


if __name__ == "__main__":
    main()
