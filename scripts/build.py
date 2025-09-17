"""Build helpers for GeradorEtiquetas executables.

Quick start:
    $ python -m scripts.build --mode onefile --binding pyqt5
    $ python -m scripts.build --mode portable --binding pyside6

The command automatically re-executes inside ``.venv``/``venv`` when available,
checks that only one Qt binding is installed and drives PyInstaller via its
Python API so the behaviour is consistent across platforms.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

from PyInstaller.__main__ import run as pyinstaller_run

APP_NAME = "GeradorEtiquetas"
MAIN_SCRIPT = "main.py"
ASSETS_DIR = Path("assets")
ICON_PATH = ASSETS_DIR / "color.ico"
COMMON_HIDDEN_IMPORTS = [
    "pywintypes",
    "pythoncom",
    "win32timezone",
    "win32print",
    "win32api",
]
QT_CONFIG = {
    "pyqt5": {
        "module": "PyQt5",
        "hidden": ["PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets"],
        "excludes": ["PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"],
        "env": "PyQt5",
    },
    "pyside6": {
        "module": "PySide6",
        "hidden": ["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"],
        "excludes": ["PyQt5", "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets"],
        "env": "PySide6",
    },
}
VENV_ENV_FLAG = "LABELS_APP_VENV_ACTIVE"


def ensure_package_importable() -> None:
    """Ensure the repository root is importable when executed as a script."""

    if __package__ in {None, ""}:
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))


def ensure_virtualenv(repo_root: Path) -> None:
    """Re-execute the script within the discovered virtual environment."""

    if os.environ.get(VENV_ENV_FLAG):
        return

    inside_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix) or sys.prefix != getattr(
        sys, "real_prefix", sys.prefix
    )
    if inside_venv:
        return

    candidates = [repo_root / ".venv", repo_root / "venv"]
    for candidate in candidates:
        if not candidate.exists():
            continue
        if os.name == "nt":
            python_bin = candidate / "Scripts" / "python.exe"
        else:
            python_bin = candidate / "bin" / "python"
        if python_bin.exists():
            env = os.environ.copy()
            env[VENV_ENV_FLAG] = "1"
            cmd = [str(python_bin), "-m", "scripts.build", *sys.argv[1:]]
            os.execve(str(python_bin), cmd, env)
    # No virtual environment detected; keep using the current interpreter.


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build executables using PyInstaller")
    parser.add_argument(
        "--mode",
        choices=("onefile", "onedir", "portable"),
        default="onefile",
        help="Tipo de build a ser gerado (padrão: onefile)",
    )
    parser.add_argument(
        "--binding",
        choices=tuple(QT_CONFIG.keys()),
        default=os.environ.get("QT_BINDING", "pyqt5").lower(),
        help="Qt binding a utilizar (padrão: QT_BINDING ou pyqt5)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove diretórios de build antes de compilar",
    )
    return parser.parse_args(argv)


def check_qt_environment(binding_key: str) -> None:
    """Ensure exactly one Qt binding is present."""

    binding = QT_CONFIG[binding_key]
    available = {
        key: importlib.util.find_spec(cfg["module"]) is not None for key, cfg in QT_CONFIG.items()
    }
    if sum(available.values()) > 1:
        raise SystemExit(
            "Both PyQt5 and PySide6 are installed. Please uninstall the unused binding before building."
        )
    if not available[binding_key]:
        raise SystemExit(
            f"The selected Qt binding '{binding_key}' is not installed. Install requirements-{binding_key}.txt first."
        )

    os.environ["QT_BINDING"] = binding["env"]


def build_hidden_imports(binding_key: str) -> Iterable[str]:
    binding = QT_CONFIG[binding_key]
    for module in binding["hidden"] + COMMON_HIDDEN_IMPORTS:
        yield module


def build_excludes(binding_key: str) -> Iterable[str]:
    yield from QT_CONFIG[binding_key]["excludes"]


def prepare_pyinstaller_args(repo_root: Path, mode: str, binding_key: str, clean: bool) -> list[str]:
    dist_dir = repo_root / "dist"
    build_dir = repo_root / "build"
    spec_dir = build_dir

    args = ["--noconfirm", "--name", APP_NAME, "--distpath", str(dist_dir), "--workpath", str(build_dir)]
    args += ["--specpath", str(spec_dir)]
    args += ["--windowed", "--icon", str(repo_root / ICON_PATH)]

    if mode in {"onefile", "portable"}:
        args.append("--onefile")
    else:
        args.append("--onedir")

    if mode != "onefile":
        args.append("--noupx")

    if mode != "portable":
        assets_arg = f"{repo_root / ASSETS_DIR}{os.pathsep}assets"
        args += ["--add-data", assets_arg]

    for module in build_hidden_imports(binding_key):
        args += ["--hidden-import", module]

    for module in build_excludes(binding_key):
        args += ["--exclude-module", module]

    if clean:
        if dist_dir.exists():
            shutil.rmtree(dist_dir)
        if build_dir.exists():
            shutil.rmtree(build_dir)

    args.append(str(repo_root / MAIN_SCRIPT))
    return args


def run_pyinstaller(args: Sequence[str]) -> None:
    try:
        pyinstaller_run(list(args))
    except SystemExit as exc:  # pragma: no cover - PyInstaller exits via SystemExit
        raise SystemExit(exc.code) from exc


def rename_artifacts(repo_root: Path, mode: str) -> Path:
    from _version import __version__

    dist_dir = repo_root / "dist"
    version_tag = f"{APP_NAME}_v{__version__}"
    extension = ".exe" if os.name == "nt" else ""

    if mode == "onedir":
        src_dir = dist_dir / APP_NAME
        if not src_dir.exists():
            raise FileNotFoundError(f"Expected build output at {src_dir}")
        dest_dir = dist_dir / version_tag
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        src_dir.rename(dest_dir)
        return dest_dir

    src_file = dist_dir / f"{APP_NAME}{extension}"
    if not src_file.exists():
        raise FileNotFoundError(f"Expected executable at {src_file}")
    dest_file = dist_dir / f"{version_tag}{extension}"
    if dest_file.exists():
        dest_file.unlink()
    src_file.rename(dest_file)
    return dest_file


def copy_assets_for_portable(repo_root: Path, artifact: Path) -> None:
    dist_dir = artifact.parent if artifact.is_file() else artifact
    destination = dist_dir / ASSETS_DIR.name
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(repo_root / ASSETS_DIR, destination)


def sign_artifact(path: Path) -> None:
    if os.name != "nt":
        return
    signtool = shutil.which("signtool")
    if not signtool:
        print("signtool.exe not found; skipping code signing.")
        return
    target = path
    if path.is_dir():
        target = path / f"{APP_NAME}.exe"
    print(f"Signing {target}...")
    subprocess.run([signtool, "sign", "/fd", "SHA256", "/a", "/tr", "http://timestamp.digicert.com", str(target)], check=False)


def main(argv: Sequence[str] | None = None) -> None:
    ensure_package_importable()
    repo_root = Path(__file__).resolve().parent.parent
    ensure_virtualenv(repo_root)
    os.chdir(repo_root)

    args = parse_args(argv)
    if args.binding not in QT_CONFIG:
        raise SystemExit(f"Unsupported binding: {args.binding}")

    check_qt_environment(args.binding)

    pyinstaller_args = prepare_pyinstaller_args(repo_root, args.mode, args.binding, args.clean)
    run_pyinstaller(pyinstaller_args)

    artifact = rename_artifacts(repo_root, args.mode)

    if args.mode == "portable":
        copy_assets_for_portable(repo_root, artifact)

    sign_artifact(artifact)

    print(f"Build completed: {artifact}")


if __name__ == "__main__":  # pragma: no cover - manual execution entry point
    main()
