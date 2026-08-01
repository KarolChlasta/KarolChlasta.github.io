#!/usr/bin/env python3
"""Copy the current academic CV into the site, refusing to publish a bad one.

Source of truth is the CV repository, not this one:
    /datadisk/od-kchlasta/6.Doc/Career/Out/CV/cv/CV-Karol Chlasta-Academic.pdf

Run:  python3 tools/publish_cv.py

Three gates before the file is copied. The phone gate is the reason this
script exists: the published CV must not carry the number, and checking it by
eye each time is exactly the kind of step that gets skipped.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path("/datadisk/od-kchlasta/6.Doc/Career/Out/CV/cv/CV-Karol Chlasta-Academic.pdf")
TARGET = ROOT / "assets/cv/karol-chlasta-cv-academic.pdf"

# Digest of the nine digits, never the digits themselves — this file is public.
PHONE_SHA256 = "7c0d3f6d13c8d5aee9e6e810d57c7f518d366e361f628ccaa6170a1e0ba0429c"
PHONE_LENGTH = 9

# A current CV mentions all of these. If one is missing, an older export has
# probably been picked up by mistake.
CURRENCY = ["Wyden", "Kozminski", "Montpellier", "WarsawIQ", "PFRON"]


def digest_hit(text: str) -> bool:
    digits = re.sub(r"\D", "", text)
    return any(
        hashlib.sha256(digits[i:i + PHONE_LENGTH].encode()).hexdigest() == PHONE_SHA256
        for i in range(len(digits) - PHONE_LENGTH + 1)
    )


def main() -> int:
    if not SOURCE.exists():
        print(f"source not found: {SOURCE}")
        return 1

    from pypdf import PdfReader

    reader = PdfReader(SOURCE)
    text = "".join(page.extract_text() or "" for page in reader.pages)

    print(f"source: {SOURCE.name}  {len(reader.pages)} pages, "
          f"{SOURCE.stat().st_size / 1024:.0f} KB")

    problems = []
    if digest_hit(text):
        problems.append("it still contains the phone number")
    missing = [k for k in CURRENCY if k not in text]
    if missing:
        problems.append(f"missing from the text: {', '.join(missing)} — is this an old export?")
    if len(reader.pages) < 5:
        problems.append(f"only {len(reader.pages)} pages, expected the full academic CV")

    if problems:
        print("\nREFUSING to publish:")
        for p in problems:
            print(f"  - {p}")
        return 1

    if TARGET.exists():
        same = hashlib.sha256(TARGET.read_bytes()).hexdigest() == \
               hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        if same:
            print("\nalready published, byte for byte — nothing to do")
            return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, TARGET)
    print(f"\npublished to {TARGET.relative_to(ROOT)}")
    print("checks passed: no phone number, all currency markers present")
    print("next: python3 tools/check_site.py, then commit and push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
