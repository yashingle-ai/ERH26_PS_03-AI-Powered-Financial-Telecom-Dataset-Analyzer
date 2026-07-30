"""Break `files_never_opened` into actionable vs not, without re-parsing anything.

A bare "1,788 files never opened" reads as 1,788 unread evidence tables. It is not: most
are photographs and Outlook containers. The only actionable bucket is files that could
plausibly hold a table but have no reader. Mirrors `_walk`'s decision (extension present in
detector.FORMAT_BY_EXT) and looks inside ZIPs via namelist(), so archive members are counted
the same way the pipeline counts them.

Usage: python -m scripts.census_skipped "datasets/FIR 65-2024" "datasets/FIR-0006-2025 U"
"""
from __future__ import annotations

import os
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.ingestion.detector import FORMAT_BY_EXT  # noqa: E402
from backend.app.ingestion.service import _KNOWN_UNREADABLE  # noqa: E402

#: Extensions that cannot hold a table by nature. Counted, but not work to be scheduled.
_NON_TABULAR = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".webp", ".emz",
    ".avi", ".mp4", ".mov", ".mkv", ".wmv", ".mp3", ".wav", ".m4a", ".amr", ".opus",
    ".lnk", ".ini", ".ds_store", ".url", ".exe", ".dll", ".ttf", ".otf", ".css", ".js",
}
#: Containers holding other files or non-tabular records.
_CONTAINERS = {".msg", ".eml", ".pst", ".ost", ".onetoc2", ".emmx", ".db", ".sqlite3",
               ".zip", ".7z", ".rar", ".gz", ".tar", ".xml"}
#: Could plausibly hold a table. This is the actionable bucket.
_MAYBE_TABULAR = {".doc", ".odt", ".ods", ".rpt", ".rtf", ".dbf", ".json", ".dat", ".prn"}


def bucket(ext: str) -> str:
    if ext in _NON_TABULAR:
        return "non-tabular (image/media/system)"
    if ext in _CONTAINERS:
        return "container (holds other files)"
    if ext in _MAYBE_TABULAR:
        return "POTENTIALLY TABULAR - no reader"
    return "unknown/other"


def main() -> None:
    for root in sys.argv[1:]:
        base = Path(root)
        by_bucket: Counter = Counter()
        by_ext: Counter = Counter()
        opened = 0
        for p in base.rglob("*"):
            if not p.is_file() or p.name.startswith(("._", "~$")) or "__MACOSX" in p.parts:
                continue
            ext = p.suffix.lower()
            if ext == ".zip":
                try:
                    with zipfile.ZipFile(p) as zf:
                        for m in zf.namelist():
                            if m.endswith("/"):
                                continue
                            mext = Path(m).suffix.lower()
                            if Path(m).name.startswith("._") or "__MACOSX" in m:
                                continue
                            if mext in FORMAT_BY_EXT:
                                opened += 1
                            else:
                                by_bucket[bucket(mext)] += 1
                                by_ext[mext or "(none)"] += 1
                except Exception:
                    pass
                by_bucket["container (holds other files)"] += 1
                by_ext[".zip"] += 1
                continue
            if ext in FORMAT_BY_EXT:
                opened += 1
            else:
                by_bucket[bucket(ext)] += 1
                by_ext[ext or "(none)"] += 1

        total = sum(by_bucket.values())
        print(f"\n=== {base.name} ===")
        print(f"opened by the pipeline : {opened:,}")
        print(f"never opened           : {total:,}")
        for b, n in by_bucket.most_common():
            print(f"   {n:6,}  {n/max(total,1):5.1%}  {b}")
        actionable = [(e, n) for e, n in by_ext.most_common()
                      if bucket(e if e != "(none)" else "") == "POTENTIALLY TABULAR - no reader"]
        print("   actionable extensions:",
              ", ".join(f"{e}={n}" for e, n in actionable) or "none")
        print("   declared unreadable reasons in code:",
              ", ".join(sorted(_KNOWN_UNREADABLE)))
        print("   top extensions:",
              ", ".join(f"{e}={n}" for e, n in by_ext.most_common(10)))


if __name__ == "__main__":
    main()
