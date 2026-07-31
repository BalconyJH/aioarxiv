#!/usr/bin/env python3
"""Verify built aioarxiv distributions and exercise them outside the source tree."""

from __future__ import annotations

import argparse
from base64 import urlsafe_b64encode
import csv
from email import message_from_bytes
from hashlib import sha256
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Final
import zipfile

if TYPE_CHECKING:
    from email.message import Message

PACKAGE_NAME: Final = "aioarxiv"
REQUIRES_PYTHON: Final = ">=3.10"

_INSTALL_SMOKE: Final = r"""
from importlib.metadata import version
import os
from pathlib import Path

import aioarxiv

expected_version = os.environ["AIOARXIV_EXPECTED_VERSION"]
repository_root = Path(os.environ["AIOARXIV_REPOSITORY_ROOT"]).resolve()

module_path = Path(aioarxiv.__file__).resolve()
if module_path.is_relative_to(repository_root):
    raise RuntimeError(
        f"Smoke imported the source checkout instead of the installed artifact: "
        f"{module_path}"
    )

installed_version = version("aioarxiv")
if installed_version != expected_version:
    raise RuntimeError(
        f"Installed version {installed_version!r} != expected {expected_version!r}"
    )
"""


class DistributionVerificationError(RuntimeError):
    """A built artifact does not satisfy the release contract."""


def _log(message: str) -> None:
    sys.stdout.write(f"{message}\n")
    sys.stdout.flush()


def _normalize_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _only_artifact(paths: list[Path], kind: str) -> Path:
    if len(paths) != 1:
        found = ", ".join(sorted(path.name for path in paths)) or "none"
        raise DistributionVerificationError(
            f"Expected exactly one {kind}, found {len(paths)}: {found}."
        )
    return paths[0]


def _validate_metadata(
    metadata: Message, *, expected_version: str, artifact: Path
) -> None:
    """Check the core metadata fields shared by wheel METADATA and sdist PKG-INFO."""
    name = metadata.get("Name")
    if name is None or _normalize_distribution_name(name) != PACKAGE_NAME:
        raise DistributionVerificationError(
            f"{artifact.name} has unexpected project name {name!r}."
        )

    version = metadata.get("Version")
    if version != expected_version:
        raise DistributionVerificationError(
            f"{artifact.name} has version {version!r}, expected {expected_version!r}."
        )

    requires_python = metadata.get("Requires-Python")
    if requires_python is None or requires_python.replace(" ", "") != REQUIRES_PYTHON:
        raise DistributionVerificationError(
            f"{artifact.name} has unexpected Requires-Python {requires_python!r}."
        )


def _verify_record_entry(
    path: str, data: bytes, record: dict[str, tuple[str, str]]
) -> None:
    digest, size = record[path]
    expected_digest = "sha256=" + urlsafe_b64encode(
        sha256(data).digest()
    ).decode().rstrip("=")
    if digest != expected_digest:
        raise DistributionVerificationError(
            f"Wheel RECORD digest mismatch for {path!r}."
        )
    if size != str(len(data)):
        raise DistributionVerificationError(
            f"Wheel RECORD size mismatch for {path!r}: {size!r}."
        )


def _verify_wheel(wheel: Path, *, expected_version: str) -> None:
    """Validate wheel metadata and re-check every RECORD digest and size."""
    with zipfile.ZipFile(wheel) as archive:
        corrupt_member = archive.testzip()
        if corrupt_member is not None:
            raise DistributionVerificationError(
                f"Wheel contains a corrupt member: {corrupt_member!r}."
            )
        names = [name for name in archive.namelist() if not name.endswith("/")]
        metadata_path = _only_artifact(
            [Path(name) for name in names if name.endswith(".dist-info/METADATA")],
            "wheel METADATA file",
        ).as_posix()
        record_path = _only_artifact(
            [Path(name) for name in names if name.endswith(".dist-info/RECORD")],
            "wheel RECORD file",
        ).as_posix()
        metadata = message_from_bytes(archive.read(metadata_path))
        _validate_metadata(metadata, expected_version=expected_version, artifact=wheel)

        record_rows = csv.reader(archive.read(record_path).decode("utf-8").splitlines())
        record = {row[0]: (row[1], row[2]) for row in record_rows if len(row) == 3}
        if set(names) != set(record):
            raise DistributionVerificationError(
                "Wheel RECORD does not match the archive contents: "
                f"missing={sorted(set(names) - set(record))}, "
                f"stale={sorted(set(record) - set(names))}."
            )
        for name in names:
            # RECORD cannot contain its own digest; every other member is checked.
            if name == record_path:
                continue
            _verify_record_entry(name, archive.read(name), record)


def _verify_sdist(sdist: Path, *, expected_version: str) -> None:
    """Validate sdist metadata and the presence of the importable package."""
    with tarfile.open(sdist, mode="r:gz") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        metadata_member = _only_artifact(
            [
                Path(member.name)
                for member in members
                if re.fullmatch(r"[^/]+/PKG-INFO", member.name)
            ],
            "source distribution PKG-INFO file",
        ).as_posix()
        file = archive.extractfile(archive.getmember(metadata_member))
        if file is None:
            raise DistributionVerificationError(
                f"Could not read source distribution member {metadata_member!r}."
            )
        metadata = message_from_bytes(file.read())
        _validate_metadata(metadata, expected_version=expected_version, artifact=sdist)

        package_marker = f"/{PACKAGE_NAME}/__init__.py"
        if not any(member.name.endswith(package_marker) for member in members):
            raise DistributionVerificationError(
                f"Source distribution does not contain {PACKAGE_NAME}/__init__.py."
            )


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _run(command: list[str], *, cwd: Path, env: dict[str, str], label: str) -> None:
    _log(f"==> {label}")
    try:
        subprocess.run(command, cwd=cwd, env=env, check=True)  # noqa: S603
    except subprocess.CalledProcessError as error:
        raise DistributionVerificationError(
            f"{label} failed with exit code {error.returncode}."
        ) from error


def _run_install_smokes(
    wheel: Path,
    sdist: Path,
    *,
    expected_version: str,
    python_version: str,
    uv: str,
    repository_root: Path,
    smoke_sdist: bool,
) -> None:
    """Install each artifact into an isolated venv and import it there."""
    artifacts = [("wheel", wheel)]
    if smoke_sdist:
        artifacts.append(("sdist", sdist))

    with TemporaryDirectory(prefix="aioarxiv-dist-smoke-") as temporary:
        root = Path(temporary).resolve()
        env = os.environ.copy()
        for inherited_name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
            env.pop(inherited_name, None)
        env.update(
            {
                "AIOARXIV_EXPECTED_VERSION": expected_version,
                "AIOARXIV_REPOSITORY_ROOT": str(repository_root),
                "PYTHONNOUSERSITE": "1",
                "UV_NO_PROGRESS": "1",
            }
        )

        for name, artifact in artifacts:
            venv = root / name
            run_dir = root / f"{name}-run"
            run_dir.mkdir()
            _run(
                [uv, "venv", "--python", python_version, str(venv)],
                cwd=run_dir,
                env=env,
                label=f"Create isolated {name} environment",
            )
            python = _venv_python(venv)
            _run(
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    str(artifact.resolve()),
                ],
                cwd=run_dir,
                env=env,
                label=f"Install {name} into the isolated environment",
            )
            _run(
                [str(python), "-c", _INSTALL_SMOKE],
                cwd=run_dir,
                env=env,
                label=f"Run installed-{name} import and version smoke",
            )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dist_dir",
        nargs="?",
        default=Path("dist"),
        type=Path,
        help="Directory containing exactly one wheel and one .tar.gz sdist.",
    )
    parser.add_argument(
        "--expected-version",
        required=True,
        help="Version required in both distribution metadata files.",
    )
    parser.add_argument(
        "--python",
        default="3.12",
        help="Python version used by isolated smoke environments.",
    )
    parser.add_argument(
        "--uv",
        default=os.environ.get("UV", "uv"),
        help="uv executable used to create isolated environments.",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Validate archives without installing them.",
    )
    parser.add_argument(
        "--wheel-only-smoke",
        action="store_true",
        help="Install and smoke the wheel, but skip the source distribution install.",
    )
    return parser.parse_args()


def main() -> None:
    """Verify the built distributions according to the parsed CLI options."""
    args = _parse_args()
    dist_dir = args.dist_dir.expanduser().resolve()
    if not dist_dir.is_dir():
        raise DistributionVerificationError(
            f"Distribution directory does not exist: {dist_dir}."
        )

    wheel = _only_artifact(list(dist_dir.glob("*.whl")), "wheel")
    sdist = _only_artifact(list(dist_dir.glob("*.tar.gz")), "source distribution")
    _log(f"==> Verify archive metadata in {dist_dir}")
    _verify_wheel(wheel, expected_version=args.expected_version)
    _verify_sdist(sdist, expected_version=args.expected_version)

    if not args.metadata_only:
        _run_install_smokes(
            wheel,
            sdist,
            expected_version=args.expected_version,
            python_version=args.python,
            uv=args.uv,
            repository_root=Path(__file__).resolve().parents[1],
            smoke_sdist=not args.wheel_only_smoke,
        )
    _log("Distribution verification passed.")


if __name__ == "__main__":
    try:
        main()
    except DistributionVerificationError as error:
        sys.stderr.write(f"Distribution verification failed: {error}\n")
        raise SystemExit(1) from None
