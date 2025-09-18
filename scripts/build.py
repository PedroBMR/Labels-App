"""Utilities to build the Labels-App executable with PyInstaller.

This module mirrors the responsibilities of the Windows PowerShell build
scripts so that the build can also run on Unix-like systems or from CI jobs
that prefer Python entry points.  It activates the project virtualenv when
available, validates that only one Qt binding is installed, invokes PyInstaller
with the right arguments and signs the resulting executable when `signtool`
is present on the system.
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

# ---------------------------------------------------------------------------
# Paths and configuration constants

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = PROJECT_ROOT / "dist"
ASSETS_DIR = PROJECT_ROOT / "assets"
SPEC_FILE = PROJECT_ROOT / "GeradorEtiquetas.spec"
DEFAULT_EXE_NAME = "GeradorEtiquetas"
TIMESTAMP_URL = "http://timestamp.digicert.com"

# Candidate folders that may contain a virtual environment managed by the
# project contributors.
VENV_NAMES = (".venv", "venv")

# Determine platform-specific folders used inside virtual environments.
PYTHON_NAME = "python.exe" if os.name == "nt" else "python"
SCRIPTS_DIR = "Scripts" if os.name == "nt" else "bin"

# Map of supported Qt bindings.  Each entry stores the top-level module that
# should be present, the pip requirements file to install and conflicting
# packages that must not coexist in the same environment.
QT_BINDINGS: dict[str, dict[str, Iterable[str] | str]] = {
    "PyQt5": {
        "module": "PyQt5",
        "requirements": "requirements-pyqt5.txt",
        "conflicts": ("PySide6", "PySide6-Addons", "PySide6-Essentials"),
    },
    "PySide6": {
        "module": "PySide6",
        "requirements": "requirements-pyside6.txt",
        "conflicts": ("PyQt5", "PyQt5-Qt5", "PyQt5-sip"),
    },
}

DEFAULT_BINDING = "PyQt5"


class BuildError(RuntimeError):
    """Raised when the build cannot proceed due to configuration issues."""


def debug(message: str) -> None:
    """Print debug messages only when the script runs in verbose mode."""

    if os.environ.get("BUILD_VERBOSE"):
        print(f"[build] {message}")


# ---------------------------------------------------------------------------
# Virtualenv helpers


def find_virtualenv_python() -> Path | None:
    """Return the Python interpreter inside the preferred virtualenv.

    The repository commonly uses either `.venv` or `venv`.  When neither folder
    exists the function returns ``None`` and the caller should fall back to the
    currently active interpreter.
    """

    for env_name in VENV_NAMES:
        candidate = PROJECT_ROOT / env_name / SCRIPTS_DIR / PYTHON_NAME
        debug(f"Checking virtualenv interpreter at {candidate}")
        if candidate.exists():
            return candidate
    return None


def ensure_virtualenv_on_path() -> None:
    """Add the detected virtualenv to ``PATH`` when running from the system.

    Ruff previously flagged the long expression that built the path as a single
    line.  We now compute the path step-by-step to stay within the configured
    line length limit and keep the logic easy to follow.
    """

    inside_venv = sys.prefix != sys.base_prefix
    if inside_venv:
        debug("Interpreter already running inside a virtual environment")
        return

    env_python = find_virtualenv_python()
    if env_python is None:
        debug("No project-managed virtualenv found")
        return

    env_bin = env_python.parent
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join((str(env_bin), original_path))
    os.environ.setdefault("VIRTUAL_ENV", str(env_bin.parent))
    debug(f"Activated virtualenv from {env_bin.parent}")


# ---------------------------------------------------------------------------
# Qt binding validation


def package_installed(name: str) -> bool:
    """Return ``True`` when the given Python package can be imported."""

    spec = importlib.util.find_spec(name)
    return spec is not None


def check_qt_environment(conflicts: Iterable[str]) -> set[str]:
    """Return the conflicting Qt packages detected in the environment."""

    return {
        conflict
        for conflict in conflicts
        if package_installed(conflict)
    }


def validate_binding(binding: str) -> None:
    """Ensure that the selected Qt binding is available and conflict free."""

    if binding not in QT_BINDINGS:
        supported = ", ".join(sorted(QT_BINDINGS))
        message = (
            f"Unknown Qt binding '{binding}'. "
            f"Choose one of {supported}."
        )
        raise BuildError(message)

    config = QT_BINDINGS[binding]
    module_name = config["module"]
    conflicts = config["conflicts"]

    if not package_installed(module_name):
        warning = (
            "[build] Warning: the selected Qt binding does not appear to be "
            "installed."
        )
        print(warning)

    detected_conflicts = check_qt_environment(conflicts)
    if detected_conflicts:
        conflicts_list = ", ".join(sorted(detected_conflicts))
        message = (
            "Both Qt bindings are installed "
            f"({conflicts_list}). "
            "Uninstall the unused binding before building the executable."
        )
        raise BuildError(message)


# ---------------------------------------------------------------------------
# PyInstaller command assembly


def assemble_pyinstaller_args(
    *,
    spec_path: Path,
    exe_name: str,
    binding: str,
    clean: bool,
    windowed: bool,
) -> list[str]:
    """Return the arguments used to call PyInstaller.

    Ruff reported overly long lines for the list assembly.  We now rely on
    intermediate variables and multiline literals so that each element stays
    within the configured 88-character limit.
    """

    base_command = [
        sys.executable,
        "-m",
        "PyInstaller",
    ]
    args: list[str] = [*base_command, "--noconfirm"]

    if clean:
        args.append("--clean")

    if spec_path.suffix == ".spec":
        args.append(str(spec_path))
        return args

    if windowed:
        args.append("--windowed")

    args.extend(["--name", exe_name])

    assets_spec = f"{ASSETS_DIR}{os.pathsep}{ASSETS_DIR.name}"
    args.extend(["--add-data", assets_spec])

    module_to_exclude = "PyQt5" if binding == "PySide6" else "PySide6"
    exclude_args = ["--exclude-module", module_to_exclude]
    args.extend(exclude_args)

    hidden_imports = [
        "--hidden-import",
        "pywintypes",
        "--hidden-import",
        "pythoncom",
        "--hidden-import",
        "win32timezone",
    ]
    args.extend(hidden_imports)

    args.append(str(spec_path))

    return args


def run_command(command: Sequence[str], *, cwd: Path | None = None) -> None:
    """Execute a subprocess, streaming the output to the console."""

    debug(f"Running command: {' '.join(command)}")
    subprocess.run(command, check=True, cwd=cwd)


def run_pyinstaller(command: Sequence[str]) -> None:
    """Run PyInstaller with the provided arguments."""

    run_command(command, cwd=PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Signing utilities


def sign_executable(executable: Path) -> None:
    """Sign the produced executable when `signtool` is available."""

    signtool = shutil.which("signtool")
    if signtool is None:
        print("[build] signtool.exe not found; skipping code signing.")
        return

    timestamp = TIMESTAMP_URL
    hash_algorithm = "SHA256"
    sign_command = [
        signtool,
        "sign",
        "/fd",
        hash_algorithm,
        "/a",
        "/tr",
        timestamp,
        str(executable),
    ]
    run_command(sign_command)


def copy_versioned_executable(executable: Path, *, exe_name: str) -> Path:
    """Copy the executable to a versioned filename so we keep build history."""

    version_module = PROJECT_ROOT / "_version.py"
    namespace: dict[str, str] = {}
    exec(version_module.read_text(), namespace)  # noqa: S102 - controlled input
    version = namespace.get("__version__", "0.0.0")

    target = DIST_DIR / f"{exe_name}_v{version}.exe"
    shutil.copy2(executable, target)
    return target


# ---------------------------------------------------------------------------
# CLI handling


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the build script."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binding",
        choices=sorted(QT_BINDINGS),
        default=os.environ.get("QT_BINDING", DEFAULT_BINDING),
        help="Qt binding to bundle. Defaults to the QT_BINDING environment variable",
    )
    parser.add_argument(
        "--name",
        default=os.environ.get("APP_NAME", DEFAULT_EXE_NAME),
        help="Executable base name. Defaults to APP_NAME or the project name.",
    )
    parser.add_argument(
        "--spec",
        type=Path,
        default=SPEC_FILE,
        help="PyInstaller spec file to use for the build process.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Ask PyInstaller to clean temporary build artefacts.",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Build without a console window regardless of the spec defaults.",
    )
    parser.add_argument(
        "--skip-sign",
        action="store_true",
        help="Skip signing the executable even when signtool is installed.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the build script."""

    args = parse_arguments(argv)
    ensure_virtualenv_on_path()
    validate_binding(args.binding)

    pyinstaller_args = assemble_pyinstaller_args(
        spec_path=args.spec,
        exe_name=args.name,
        binding=args.binding,
        clean=args.clean,
        windowed=args.windowed,
    )
    run_pyinstaller(pyinstaller_args)

    exe_path = DIST_DIR / f"{args.name}.exe"
    if exe_path.exists() and not args.skip_sign:
        sign_executable(exe_path)

    if exe_path.exists():
        copy_versioned_executable(exe_path, exe_name=args.name)
        print(f"[build] Executable available at {exe_path}")
    else:
        raise BuildError("PyInstaller did not produce the expected executable.")

    return 0


if __name__ == "__main__":
    exit_code = main()
    raise SystemExit(exit_code)

