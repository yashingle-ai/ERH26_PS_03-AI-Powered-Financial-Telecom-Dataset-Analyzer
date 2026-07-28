"""ZIP archive expansion (B1 follow-up) — recover evidence sealed inside archives.

Real case folders arrive as nested ZIPs: an operator mails a .zip, the investigator saves
it inside another .zip, and the structured CDR/bank exports end up two or three levels
down. `parse_directory` only ever walked the filesystem, so on FIR 65-2024 that left 92
archives unopened — 83 structured files (CSV/XLSX/XLS/TXT) plus 129 PDFs never reached the
parser, and nothing reported them as skipped.

Extraction is deliberately defensive: archives are untrusted input arriving from third
parties, so this module caps recursion depth, total expanded bytes, and per-member size,
and refuses members whose path escapes the destination directory.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from ...core.logging_config import get_logger

log = get_logger(__name__)

# macOS resource-fork mirrors and AppleDouble sidecars — same rule the directory walk uses.
_SKIP_PARTS = {"__MACOSX"}


def _is_noise(name: str) -> bool:
    parts = Path(name).parts
    if any(p in _SKIP_PARTS for p in parts):
        return True
    base = Path(name).name
    return base.startswith("._") or base.startswith("~$")


def _safe_destination(dest: Path, member: str) -> Path | None:
    """Resolve a member path inside `dest`, or None if it escapes.

    A crafted archive can carry `../../etc/passwd` or an absolute path; zipfile.extract
    sanitises some of this but not all of it across versions, so the check is explicit.
    """
    target = (dest / member).resolve()
    try:
        target.relative_to(dest.resolve())
    except ValueError:
        return None
    return target


def _zip_passwords() -> list[bytes]:
    """Optional analyst-supplied passwords for locked archive members (G4).

    `ERAKSHAK_ZIP_PASSWORD` (single) or `ERAKSHAK_ZIP_PASSWORDS` (comma-separated).
    Tried in order after an unlocked open fails.
    """
    import os
    raw = os.getenv("ERAKSHAK_ZIP_PASSWORDS") or os.getenv("ERAKSHAK_ZIP_PASSWORD") or ""
    out: list[bytes] = []
    for part in raw.split(","):
        p = part.strip()
        if p:
            out.append(p.encode("utf-8"))
    return out


def _write_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path,
                  passwords: list[bytes] | None = None) -> None:
    """Write one member, trying optional passwords when the member is encrypted."""
    passwords = passwords or []
    try:
        with zf.open(info) as src, target.open("wb") as fh:
            fh.write(src.read())
        return
    except RuntimeError as e:
        if "encrypted" not in str(e).lower() and "password" not in str(e).lower():
            raise
        if not passwords:
            raise
    for pwd in passwords:
        try:
            zf.setpassword(pwd)
            with zf.open(info) as src, target.open("wb") as fh:
                fh.write(src.read())
            return
        except RuntimeError:
            continue
    raise RuntimeError("encrypted")


def extract_archive(path: str, dest: Path, *, max_total_bytes: int,
                    max_depth: int = 3, _depth: int = 0,
                    _budget: list[int] | None = None) -> list[Path]:
    """Expand `path` under `dest`, recursing into nested archives. Returns extracted files.

    `max_total_bytes` is the *uncompressed* budget across the whole expansion, shared by
    nested archives — the guard against a zip bomb, where a small archive expands to
    gigabytes. Exceeding it stops extraction and logs; it never raises, because one bad
    archive must not abort ingestion of the rest of the case.
    """
    if _budget is None:
        _budget = [max_total_bytes]
    if _depth > max_depth:
        log.info("archive nesting deeper than %d levels, not descending: %s",
                 max_depth, Path(path).name)
        return []

    out: list[Path] = []
    nested: list[Path] = []
    encrypted = 0
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir() or _is_noise(info.filename):
                    continue
                if info.file_size > _budget[0]:
                    log.warning("archive %s exceeds expansion budget at %s — stopping",
                                Path(path).name, info.filename)
                    break
                target = _safe_destination(dest, info.filename)
                if target is None:
                    log.warning("refusing archive member escaping destination: %s",
                                info.filename)
                    continue
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    _write_member(zf, info, target, passwords=_zip_passwords())
                except RuntimeError as e:
                    # Operators routinely send password-protected archives; zipfile raises
                    # a bare RuntimeError for those. One locked member must not lose the
                    # rest of the archive, let alone abort the case.
                    if "encrypted" in str(e).lower() or "password" in str(e).lower():
                        encrypted += 1
                    else:
                        log.warning("member %s unreadable: %s", info.filename, e)
                    continue
                except (OSError, zipfile.BadZipFile) as e:
                    log.warning("member %s unreadable: %s", info.filename, e)
                    continue
                _budget[0] -= info.file_size
                if target.suffix.lower() == ".zip":
                    nested.append(target)
                else:
                    out.append(target)
    except (zipfile.BadZipFile, OSError) as e:
        # A corrupt archive is evidence too — report it, don't abort the batch.
        log.warning("could not read archive %s: %s", Path(path).name, e)
        return out

    if encrypted:
        # Surfaced at WARNING because it is actionable: the analyst holds the password.
        log.warning("archive %s: %d member(s) are password-protected and were skipped",
                    Path(path).name, encrypted)

    for inner in nested:
        sub = dest / f"{inner.stem}__nested"
        out.extend(extract_archive(str(inner), sub, max_total_bytes=max_total_bytes,
                                   max_depth=max_depth, _depth=_depth + 1, _budget=_budget))
    return out
