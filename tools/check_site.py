#!/usr/bin/env python3
"""Verify the site against the acceptance checklist in the design spec.

Run from anywhere:  python3 tools/check_site.py
Exit code 0 = every check passed, 1 = at least one check failed.
"""
from __future__ import annotations

import hashlib
import html.parser
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PAGES = ["index.html", "publications/index.html", "privacy/index.html"]
CSS = "assets/css/site.css"
JS = "assets/js/site.js"

# The phone number that must never appear in a published file, stored as a
# SHA-256 digest of its nine digits. Keeping the digest rather than the number
# means this public repository does not itself leak what it is guarding against.
PHONE_SHA256 = "7c0d3f6d13c8d5aee9e6e810d57c7f518d366e361f628ccaa6170a1e0ba0429c"
PHONE_LENGTH = 9

FONT_FILES = [
    "ibm-plex-sans-latin-400-normal.woff2",
    "ibm-plex-sans-latin-600-normal.woff2",
    "ibm-plex-sans-latin-ext-400-normal.woff2",
    "ibm-plex-sans-latin-ext-600-normal.woff2",
    "ibm-plex-mono-latin-400-normal.woff2",
    "ibm-plex-mono-latin-ext-400-normal.woff2",
    "source-serif-4-latin-400-normal.woff2",
    "source-serif-4-latin-ext-400-normal.woff2",
    "source-serif-4-latin-400-italic.woff2",
    "source-serif-4-latin-ext-400-italic.woff2",
]

EXPECTED_PUBLICATIONS = 19
EXPECTED_TALKS = 28
EXPECTED_THESES = 2

# Zero by design. The arXiv posting "Sentiment analysis model for Twitter data
# in Polish language" (arXiv:1911.00985) is the 2015 Warsaw University of
# Technology diploma thesis made public in 2019, not a separate work. It is
# linked from the thesis entry; listing it twice would inflate the record.
EXPECTED_PREPRINTS = 0

ORCID = "0000-0002-6539-566X"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

class Tags(html.parser.HTMLParser):
    """Collect every start tag with its attributes as a flat list."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))

    handle_startendtag = handle_starttag


def read(rel: str) -> str:
    path = ROOT / rel
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def tags_of(rel: str) -> list[tuple[str, dict]]:
    src = read(rel)
    if not src:
        return []
    parser = Tags()
    parser.feed(src)
    return parser.items


def blocks(rel: str, cls: str) -> list[str]:
    """Return the inner HTML of every <li class="cls" ...> ... </li>."""
    pattern = re.compile(r'<li class="' + cls + r'"[^>]*>(.*?)</li>', re.S)
    return pattern.findall(read(rel))


# --------------------------------------------------------------------------- #
# checks — each returns a list of failure messages (empty list = pass)
# --------------------------------------------------------------------------- #

def no_cra_leftovers() -> list[str]:
    fails = []
    if (ROOT / "asset-manifest.json").exists():
        fails.append("asset-manifest.json still exists")
    if (ROOT / "static").exists():
        fails.append("static/ still exists")
    if (ROOT / "social-image.png").exists():
        fails.append("social-image.png still exists (replaced by assets/img/og-card.jpg)")
    for leftover in ROOT.glob("precache-manifest*.js"):
        fails.append(f"{leftover.name} still exists")
    return fails


def required_files() -> list[str]:
    required = PAGES + [
        CSS, JS,
        "manifest.json", "robots.txt", "sitemap.xml", "CNAME", "llms.txt",
        "service-worker.js", "favicon.ico",
        "assets/img/icon-180.png", "assets/img/icon-192.png",
        "assets/img/icon-512.png",
        "assets/img/og-card.jpg",
    ]
    return [f"missing {r}" for r in required if not (ROOT / r).exists()]


def internal_links() -> list[str]:
    fails = []
    for page in PAGES:
        for tag, attrs in tags_of(page):
            for key in ("href", "src"):
                target = attrs.get(key)
                if not target:
                    continue
                if target.startswith(("#", "mailto:", "tel:", "data:")):
                    continue
                if "://" in target:
                    continue
                clean = target.split("#")[0].split("?")[0]
                if not clean:
                    continue
                if clean.startswith("/"):
                    resolved = ROOT / clean.lstrip("/")
                else:
                    resolved = (ROOT / page).parent / clean
                if resolved.is_dir():
                    resolved = resolved / "index.html"
                if not resolved.exists():
                    fails.append(f'{page}: <{tag} {key}="{target}"> does not resolve')
    return fails


def no_stale_refs() -> list[str]:
    fails = []
    banned = ["static/", "chunk.js", "instagram.com/karol", "precache", "Create React App"]
    for rel in PAGES + [CSS, JS, "manifest.json"]:
        src = read(rel)
        for needle in banned:
            if needle in src:
                fails.append(f"{rel} references {needle!r}")
    return fails


def images_complete() -> list[str]:
    fails = []
    for page in PAGES:
        for tag, attrs in tags_of(page):
            if tag != "img":
                continue
            src = attrs.get("src", "?")
            for required in ("width", "height", "alt"):
                if attrs.get(required) is None:
                    fails.append(f'{page}: <img src="{src}"> missing {required}')
            if attrs.get("alt") == "":
                fails.append(f'{page}: <img src="{src}"> has empty alt')
    return fails


def fonts_present() -> list[str]:
    fails = []
    css = read(CSS)
    for name in FONT_FILES:
        if not (ROOT / "assets/fonts" / name).exists():
            fails.append(f"missing assets/fonts/{name}")
        elif name not in css:
            fails.append(f"{name} present but not referenced in {CSS}")
    return fails


def no_phone_in_pdfs() -> list[str]:
    """No published PDF may carry the phone number.

    This originally checked only assets/cv/, which missed the real risk:
    journals print the corresponding author's telephone and fax in the
    first-page footnote. One published paper carried it and had already been
    committed before a scan of the whole directory caught it. Every PDF the
    site serves is checked now.

    The number itself is never written here — only the digest above — so this
    file cannot leak what it exists to catch.
    """
    candidates = []
    for folder in ("assets/cv", "assets/papers"):
        d = ROOT / folder
        if d.exists():
            candidates += sorted(d.glob("*.pdf"))
    if not candidates:
        return ["no PDF in assets/cv/ or assets/papers/"]
    try:
        from pypdf import PdfReader
    except ImportError:
        return ["pypdf not installed, cannot verify the CV"]
    fails = []
    for pdf in candidates:
        text = "".join(page.extract_text() or "" for page in PdfReader(pdf).pages)
        digits = re.sub(r"\D", "", text)
        # Slide a window over every run of digits, so the number is caught
        # whatever spacing, dashes or country prefix the document uses.
        for start in range(len(digits) - PHONE_LENGTH + 1):
            window = digits[start:start + PHONE_LENGTH]
            if hashlib.sha256(window.encode()).hexdigest() == PHONE_SHA256:
                fails.append(f"{pdf.name} still contains the phone number")
                break
    return fails


def publications() -> list[str]:
    entries = blocks("publications/index.html", "pub")
    fails = []
    if len(entries) != EXPECTED_PUBLICATIONS:
        fails.append(f"found {len(entries)} publication entries, expected {EXPECTED_PUBLICATIONS}")
    for i, entry in enumerate(entries, 1):
        if "<a " not in entry:
            fails.append(f"publication entry {i} has no link (needs a PDF or DOI)")
    return fails


def talks() -> list[str]:
    entries = blocks("publications/index.html", "talk")
    if len(entries) != EXPECTED_TALKS:
        return [f"found {len(entries)} talk entries, expected {EXPECTED_TALKS}"]
    return []


def theses_and_preprints() -> list[str]:
    fails = []
    for cls, expected in (("thesis", EXPECTED_THESES), ("preprint", EXPECTED_PREPRINTS)):
        entries = blocks("publications/index.html", cls)
        if len(entries) != expected:
            fails.append(f"found {len(entries)} {cls} entries, expected {expected}")
    return fails


def orcid_linked() -> list[str]:
    src = read("index.html")
    fails = []
    if ORCID not in src:
        fails.append(f"index.html does not link the ORCID {ORCID}")
    if "252" not in src or "h-index" not in src.lower():
        fails.append("index.html does not show the Scholar metrics (252 citations, h-index 6)")
    return fails


def polish_annotated() -> list[str]:
    src = read("publications/index.html")
    fails = []
    for cls in ("pub", "talk"):
        pattern = re.compile(
            r'<li class="' + cls + r'"[^>]*data-lang="pl"[^>]*>(.*?)</li>', re.S
        )
        for i, entry in enumerate(pattern.findall(src), 1):
            if "(in Polish)" not in entry:
                fails.append(f'{cls} entry {i} marked data-lang="pl" lacks "(in Polish)"')
    return fails


def paper_licences() -> list[str]:
    fails = []
    for i, entry in enumerate(blocks("publications/index.html", "pub"), 1):
        if "/assets/papers/" in entry and 'class="licence"' not in entry:
            fails.append(f"publication entry {i} hosts a PDF but states no licence")
    return fails


def meta_complete() -> list[str]:
    src = read("index.html")
    fails = []
    if "<title>" not in src:
        fails.append("index.html has no <title>")
    if 'rel="canonical"' not in src:
        fails.append("index.html has no canonical link")
    for prop in ("og:title", "og:description", "og:image"):
        if prop not in src:
            fails.append(f"index.html missing {prop}")
    if '"Person"' not in src:
        fails.append("index.html has no JSON-LD Person block")
    if "PhD student" in src:
        fails.append("index.html still describes Karol as a PhD student")
    if 'lang="en"' not in src:
        fails.append('index.html missing lang="en"')
    return fails


def sw_killswitch() -> list[str]:
    src = read("service-worker.js")
    fails = []
    if "unregister" not in src:
        fails.append("service-worker.js does not unregister itself")
    for needle in ("precache", "workbox", "importScripts"):
        if needle in src:
            fails.append(f"service-worker.js still contains {needle!r}")
    return fails


def theme_tokens() -> list[str]:
    css = read(CSS)
    fails = []
    for needle in (
        "prefers-color-scheme: dark",
        ':root[data-theme="dark"]',
        ':root[data-theme="light"]',
    ):
        if needle not in css:
            fails.append(f"{CSS} missing {needle!r}")
    for token in ("--paper", "--panel", "--ink", "--muted", "--hair", "--navy", "--gold"):
        if token not in css:
            fails.append(f"{CSS} missing token {token}")
    return fails


def icons_are_ours() -> list[str]:
    """The 2021 build shipped the Create React App logo as the favicon.

    It sat there for five years because nothing ever looked at it. This check
    fails if the React atom (its cyan is #61DAFB) comes back, or if an icon
    stops using the site's navy.
    """
    try:
        from PIL import Image
    except ImportError:
        return ["Pillow not installed, cannot inspect the icons"]
    react_cyan = (97, 218, 251)
    navy = (20, 58, 114)
    fails = []
    for name in ("assets/img/icon-192.png", "assets/img/icon-512.png"):
        path = ROOT / name
        if not path.exists():
            fails.append(f"missing {name}")
            continue
        colours = {c for _, c in Image.open(path).convert("RGB").getcolors(maxcolors=1 << 24)}
        if react_cyan in colours:
            fails.append(f"{name} still contains the React logo cyan")
        if navy not in colours:
            fails.append(f"{name} does not use the site navy #143a72")
    ico = ROOT / "favicon.ico"
    if ico.exists():
        sizes = sorted(Image.open(ico).ico.sizes())
        if (16, 16) not in sizes:
            fails.append(f"favicon.ico has no 16x16 entry, only {sizes}")
    return fails


def ai_crawler_policy() -> list[str]:
    """robots.txt should state a deliberate position on AI crawlers."""
    robots = read("robots.txt")
    fails = []
    if "Sitemap:" not in robots:
        fails.append("robots.txt does not point at the sitemap")
    for agent in ("GPTBot", "ClaudeBot", "Google-Extended", "CCBot"):
        if agent not in robots:
            fails.append(f"robots.txt says nothing about {agent}")
    if "/assets/papers/" not in robots:
        fails.append("robots.txt does not mention the papers directory")
    return fails


def focus_visible() -> list[str]:
    css = read(CSS)
    fails = []
    if re.search(r"outline\s*:\s*none", css):
        fails.append(f"{CSS} uses bare 'outline: none'")
    if ":focus-visible" not in css:
        fails.append(f"{CSS} defines no :focus-visible style")
    return fails


CHECKS = [
    no_cra_leftovers, required_files, internal_links, no_stale_refs,
    images_complete, fonts_present, no_phone_in_pdfs, publications, talks,
    theses_and_preprints, orcid_linked, polish_annotated, paper_licences,
    meta_complete, sw_killswitch, theme_tokens, focus_visible,
    icons_are_ours, ai_crawler_policy,
]


def main() -> int:
    failed = 0
    for check in CHECKS:
        problems = check()
        if problems:
            failed += 1
            print(f"FAIL  {check.__name__}")
            for problem in problems:
                print(f"        {problem}")
        else:
            print(f"PASS  {check.__name__}")
    print()
    if failed:
        print(f"{failed} of {len(CHECKS)} checks failed")
        return 1
    print(f"all {len(CHECKS)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
