#!/usr/bin/env python3
"""Conservative distribution scan. No network, no note contents in output."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = {
    "email": r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
    "host path": r"/(?:Users|home)/[\w.-]+|[A-Za-z]:[\\/]Users[\\/]",
    "private identifier": r"Q" + r"oo\.\d{3}",
    "token": r"(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})",
    "private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
}
FORBIDDEN = {".git", ".env", ".DS_Store", ".obsidian", "__pycache__", "secrets"}


def scan(root):
    failures = []
    count = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            failures.append(f"link: {relative}")
            continue
        if path.name in FORBIDDEN or path.name.startswith(".env.") or path.suffix == ".pyc":
            failures.append(f"forbidden file: {relative}")
        if path.is_file():
            count += 1
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeError, OSError):
                failures.append(f"not readable UTF-8: {relative}")
                continue
            for label, pattern in PATTERNS.items():
                if re.search(pattern, content):
                    failures.append(f"{label}: {relative}")
    return count, failures


if __name__ == "__main__":
    count, failures = scan(ROOT)
    for failure in failures:
        print(failure)
    print(f"distribution: {count} files; {len(failures)} findings")
    raise SystemExit(bool(failures))
