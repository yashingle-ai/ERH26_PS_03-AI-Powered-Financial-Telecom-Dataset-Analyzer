#!/usr/bin/env python3
"""Stage a raw case folder into upload-ready batches.

A real case folder is not shaped like something you can hand to a browser: it is
nested dozens of levels deep, mixes evidence the pipeline reads (statements, CDR,
spreadsheets) with evidence it cannot (CCTV footage, photographs), and repeats
filenames like `statement.csv` across a dozen bank subfolders.

This flattens the readable subset into `<kind>/` folders whose contents can be
selected and uploaded in one go.

Two things it deliberately does NOT do:

* **Rename away the origin.** The source path is folded into the filename
  (`bank__AXIS__stmt.csv`), because `source_file` is what appears in the
  provenance of every event derived from it. A flattened `stmt.csv` that could
  have come from any of twelve banks is not evidence.
* **Silently drop anything.** Every skipped file is counted and reported by
  reason. A staging step that quietly loses evidence is worse than no staging
  step, because the gap is invisible downstream.

Usage:
    python scripts/stage_for_upload.py "datasets/FIR 65-2024"
    python scripts/stage_for_upload.py "datasets/FIR 65-2024" --out datasets/upload-ready
    python scripts/stage_for_upload.py "datasets/FIR 65-2024" --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

#: Mirrors UPLOAD_EXTENSIONS in backend/app/api/main.py. Kept in step so staging
#: never produces a file the upload endpoint will refuse.
SUPPORTED = {".csv", ".txt", ".xlsx", ".xls", ".pdf", ".docx", ".zip"}

#: Legacy OLE2 Word. Detected and cleanly rejected by the pipeline (gap G2), and
#: refused by the upload endpoint, so staging them would only produce noise.
KNOWN_UNREADABLE = {".doc"}

#: Default per-file cap on the API (ERAKSHAK_MAX_UPLOAD_MB).
DEFAULT_MAX_MB = 256

#: Default files per request (ERAKSHAK_MAX_UPLOAD_FILES) — drives batch sizing.
DEFAULT_BATCH = 200

#: Path fragments that indicate what a file is. First match wins, so order
#: matters: "ipdr" is checked before "ip", "cdr" before "call".
KIND_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("ipdr", ("ipdr", "ip detail", "ip log", "internet")),
    ("cdr", ("cdr", "call detail", "call record", "tower", "sdr", "imei", "ctrace")),
    ("bank", ("bank", "statement", "account", "upi", "wallet", "paytm", "kyc", "ncrp", "nccrp")),
]

_UNSAFE = re.compile(r"[^\w.\-]+", re.UNICODE)


def classify(rel: Path) -> str:
    """Guess a kind from the source path.

    Only decides which subfolder a file lands in — the parser identifies files by
    content, so a misfiled statement is still read as a statement. Getting this
    approximately right keeps the upload batches meaningful to a human.
    """
    haystack = str(rel).lower()
    for kind, needles in KIND_HINTS:
        if any(n in haystack for n in needles):
            return kind
    return "other"


def flat_name(rel: Path, limit: int = 120) -> str:
    """Fold a nested path into one filename that still names its origin.

    Long Gujarati paths blow past Windows' 260-char limit once flattened, so the
    middle is dropped and a short hash of the full path restores uniqueness —
    truncation alone would collide precisely on the deep paths that need it most.
    """
    suffix = rel.suffix.lower()
    parts = [_UNSAFE.sub("_", p).strip("_") for p in rel.with_suffix("").parts]
    stem = "__".join(p for p in parts if p) or "file"
    if len(stem) > limit:
        digest = hashlib.sha1(str(rel).encode("utf-8", "replace")).hexdigest()[:8]
        stem = f"{stem[: limit - 9]}_{digest}"
    return f"{stem}{suffix}"


def iter_candidates(root: Path):
    """Yield every file under root, with the junk the OS leaves behind filtered out."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("._") or "__MACOSX" in path.parts:
            continue      # AppleDouble sidecars: metadata, never evidence
        yield path


def stage(source: Path, out_root: Path, *, max_mb: int, dry_run: bool) -> int:
    if not source.is_dir():
        print(f"error: {source} is not a directory", file=sys.stderr)
        return 2

    case = _UNSAFE.sub("-", source.name).strip("-").lower()
    dest_root = out_root / case
    max_bytes = max_mb * 1024 * 1024

    staged: dict[str, list[tuple[Path, Path, int]]] = defaultdict(list)
    skipped: Counter[str] = Counter()
    skipped_bytes = 0
    oversize: list[tuple[Path, int]] = []
    seen: set[Path] = set()

    for path in iter_candidates(source):
        rel = path.relative_to(source)
        suffix = path.suffix.lower()

        if suffix in KNOWN_UNREADABLE:
            skipped["legacy .doc (pipeline cannot read; convert to .docx)"] += 1
            continue
        if suffix not in SUPPORTED:
            skipped[f"unsupported type '{suffix or 'none'}'"] += 1
            continue

        size = path.stat().st_size
        if size == 0:
            skipped["empty file"] += 1
            continue
        if size > max_bytes:
            oversize.append((rel, size))
            skipped[f"over the {max_mb} MB per-file upload cap"] += 1
            skipped_bytes += size
            continue

        kind = classify(rel)
        target = dest_root / kind / flat_name(rel)
        # flat_name is hash-suffixed for long paths, but two short distinct paths
        # can still normalise to the same name. Never let one overwrite the other.
        n = 1
        while target in seen:
            target = target.with_name(f"{target.stem}-{n}{target.suffix}")
            n += 1
        seen.add(target)
        staged[kind].append((path, target, size))

    total_files = sum(len(v) for v in staged.values())
    total_bytes = sum(s for v in staged.values() for *_, s in v)

    print(f"\n{'DRY RUN — ' if dry_run else ''}staging {source}")
    print(f"  -> {dest_root}\n")
    print(f"  {'kind':<8} {'files':>6} {'size':>10}   upload batches")
    print(f"  {'-' * 8} {'-' * 6} {'-' * 10}   {'-' * 14}")
    for kind in ("bank", "cdr", "ipdr", "other"):
        items = staged.get(kind) or []
        if not items:
            continue
        mb = sum(s for *_, s in items) / 1048576
        batches = (len(items) + DEFAULT_BATCH - 1) // DEFAULT_BATCH
        print(f"  {kind:<8} {len(items):>6} {mb:>9.1f}M   {batches}")
    print(f"  {'-' * 8} {'-' * 6} {'-' * 10}")
    print(f"  {'TOTAL':<8} {total_files:>6} {total_bytes / 1048576:>9.1f}M\n")

    if skipped:
        print("  skipped (nothing is dropped silently):")
        for reason, n in skipped.most_common():
            print(f"    {n:>5}  {reason}")
        if oversize:
            print("\n  oversize files — upload these separately or raise "
                  "ERAKSHAK_MAX_UPLOAD_MB:")
            for rel, size in sorted(oversize, key=lambda x: -x[1])[:10]:
                print(f"    {size / 1048576:>8.1f} MB  {rel}")
        print()

    if dry_run:
        return 0

    if dest_root.exists():
        shutil.rmtree(dest_root)
    copied = 0
    for kind, items in staged.items():
        (dest_root / kind).mkdir(parents=True, exist_ok=True)
        for src, target, _ in items:
            shutil.copy2(src, target)
            copied += 1
            if copied % 100 == 0:
                print(f"  copied {copied}/{total_files}…", flush=True)

    print(f"  copied {copied} files.\n")
    print("  Next: open the Upload & Ingest page, name the dataset "
          f"'{case}', pick a kind, and drag in that kind's folder.")
    print(f"  Folders with more than {DEFAULT_BATCH} files need more than one "
          "upload — the counts above tell you how many.\n")
    return 0


def main() -> int:
    # Real case folders carry Gujarati and Devanagari filenames. Windows consoles
    # default to cp1252, which raises UnicodeEncodeError mid-report — the tool would
    # crash while printing the very files it is meant to tell you about.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="raw case folder")
    ap.add_argument("--out", type=Path, default=Path("datasets/upload-ready"),
                    help="staging root (default: datasets/upload-ready)")
    ap.add_argument("--max-mb", type=int, default=DEFAULT_MAX_MB,
                    help=f"per-file upload cap in MB (default: {DEFAULT_MAX_MB})")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be staged, copy nothing")
    args = ap.parse_args()
    return stage(args.source, args.out, max_mb=args.max_mb, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
