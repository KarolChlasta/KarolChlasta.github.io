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

# Directory prefix -> the value of <html lang> for pages under it.
LANGS = {"": "en-GB", "pl": "pl", "fr": "fr"}

# Logical page -> path segment per language. The empty prefix is the root.
PATHS = {
    "home":         {"": "",              "pl": "",             "fr": ""},
    "publications": {"": "publications",  "pl": "publikacje",   "fr": "publications"},
    "privacy":      {"": "privacy",       "pl": "prywatnosc",   "fr": "confidentialite"},
}


def page_file(page: str, lang: str) -> str:
    """Repository-relative path of one page in one language."""
    parts = [p for p in (lang, PATHS[page][lang]) if p]
    return "/".join(parts + ["index.html"])


def page_url(page: str, lang: str) -> str:
    parts = [p for p in (lang, PATHS[page][lang]) if p]
    return "https://karol.chlasta.pl/" + ("/".join(parts) + "/" if parts else "")


PAGES = [page_file(p, l) for l in LANGS for p in PATHS]
LD_PAGES = {page_file("home", l): LANGS[l] for l in LANGS}
EN_ALIAS = "en/index.html"

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


def language_versions_exist() -> list[str]:
    fails = [f"missing {p}" for p in PAGES if not (ROOT / p).exists()]
    if not (ROOT / EN_ALIAS).exists():
        fails.append(f"missing {EN_ALIAS}")
    return fails


def lang_attribute_matches_path() -> list[str]:
    """<html lang> must agree with the directory the file sits in."""
    fails = []
    for lang, code in LANGS.items():
        for page in PATHS:
            rel = page_file(page, lang)
            src = read(rel)
            if not src:
                continue
            if f'<html lang="{code}">' not in src:
                fails.append(f'{rel}: expected <html lang="{code}">')
    return fails


def canonical_is_self() -> list[str]:
    """Each page is its own canonical. A translated page pointing at the
    English original would ask search engines to drop it from the index."""
    fails = []
    for lang in LANGS:
        for page in PATHS:
            rel, url = page_file(page, lang), page_url(page, lang)
            src = read(rel)
            if not src:
                continue
            if f'<link rel="canonical" href="{url}">' not in src:
                fails.append(f"{rel}: canonical is not {url}")
    return fails


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


# The annotation is page copy, so it is translated; the data-lang marker
# that drives this check is not.
LANG_NOTE = {"": "(in Polish)", "pl": "(po polsku)", "fr": "(en polonais)"}


def polish_annotated() -> list[str]:
    fails = []
    for lang in LANGS:
        rel = page_file("publications", lang)
        src = read(rel)
        note = LANG_NOTE[lang]
        for cls in ("pub", "talk"):
            pattern = re.compile(
                r'<li class="' + cls + r'"[^>]*data-lang="pl"[^>]*>(.*?)</li>', re.S
            )
            for i, entry in enumerate(pattern.findall(src), 1):
                if note not in entry:
                    fails.append(f'{rel}: {cls} entry {i} lacks "{note}"')
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
    if 'lang="en-GB"' not in src:
        fails.append('index.html missing lang="en-GB"')
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


# Regional-indicator symbols. Windows renders these as two-letter country
# codes rather than flags, so they must never appear in a served file.
REGIONAL_INDICATORS = re.compile(r"[\U0001F1E6-\U0001F1FF]")


def no_emoji_flags() -> list[str]:
    fails = []
    for rel in PAGES + [CSS, JS]:
        if REGIONAL_INDICATORS.search(read(rel)):
            fails.append(f"{rel} contains an emoji flag; use the inline SVG sprite")
    return fails


def switcher_styles_present() -> list[str]:
    css = read(CSS)
    fails = []
    for needle in (".lang", ".flag", ".sr", "--flagline"):
        if needle not in css:
            fails.append(f"{CSS} defines no {needle}")
    # --flagline must flip with the theme, like every other token.
    for block in ("prefers-color-scheme: dark", ':root[data-theme="dark"]'):
        start = css.find(block)
        if start == -1 or "--flagline" not in css[start:start + 400]:
            fails.append(f"{CSS}: --flagline not set inside {block!r}")
    return fails


FLAG_ORDER = ["pl", "en", "fr"]
LANG_NAMES = {"pl": "Polski", "en": "English", "fr": "Français"}
# hreflang code -> directory prefix
CODE_TO_LANG = {"en": "", "pl": "pl", "fr": "fr"}


def switcher_on_every_page() -> list[str]:
    """Three links, fixed order, exactly one marked current.

    The order never varies with the page's own language: moving the active
    flag to the front would make the positions jump between pages.
    """
    fails = []
    block = re.compile(r'<div class="lang">(.*?)</div>', re.S)
    link = re.compile(r'<a\s+([^>]*)>', re.S)
    for lang in LANGS:
        for page in PATHS:
            rel = page_file(page, lang)
            src = read(rel)
            if not src:
                continue
            found = block.findall(src)
            if len(found) != 1:
                fails.append(f"{rel}: expected 1 switcher, found {len(found)}")
                continue
            attrs = link.findall(found[0])
            if len(attrs) != 3:
                fails.append(f"{rel}: switcher has {len(attrs)} links, expected 3")
                continue
            for i, code in enumerate(FLAG_ORDER):
                if f'hreflang="{code}"' not in attrs[i]:
                    fails.append(f"{rel}: link {i + 1} is not {code}; order must be PL, EN, FR")
            current = [a for a in attrs if 'aria-current="true"' in a]
            if len(current) != 1:
                fails.append(f"{rel}: {len(current)} links marked current, expected 1")
            elif f'hreflang="{HREFLANG[lang]}"' not in current[0]:
                fails.append(f"{rel}: the current marker is on the wrong language")
    return fails


def switcher_accessible_names() -> list[str]:
    """A flag is a picture. Each link needs a name a screen reader can say."""
    fails = []
    block = re.compile(r'<div class="lang">(.*?)</div>', re.S)
    anchor = re.compile(r'<a\s[^>]*hreflang="(\w+)"[^>]*>(.*?)</a>', re.S)
    for lang in LANGS:
        for page in PATHS:
            rel = page_file(page, lang)
            found = block.findall(read(rel))
            if not found:
                continue
            for code, inner in anchor.findall(found[0]):
                name = LANG_NAMES[code]
                if f'<span class="sr">{name}</span>' not in inner:
                    fails.append(f'{rel}: {code} link has no <span class="sr">{name}</span>')
                if f'#f-{"gb" if code == "en" else code}' not in inner:
                    fails.append(f"{rel}: {code} link does not use the flag symbol")
    return fails


def slug_map_consistent() -> list[str]:
    """Switcher targets must match the path map, and stay ASCII."""
    fails = []
    block = re.compile(r'<div class="lang">(.*?)</div>', re.S)
    anchor = re.compile(r'<a\s+href="([^"]+)"[^>]*hreflang="(\w+)"', re.S)
    for lang in LANGS:
        for page in PATHS:
            rel = page_file(page, lang)
            found = block.findall(read(rel))
            if not found:
                continue
            for href, code in anchor.findall(found[0]):
                expected = page_url(page, CODE_TO_LANG[code]).replace(
                    "https://karol.chlasta.pl", "")
                if href != expected:
                    fails.append(f"{rel}: {code} link points at {href}, expected {expected}")
                if not href.isascii():
                    fails.append(f"{rel}: {href} contains a non-ASCII character")
    return fails


THEME_DATA_ATTRS = ("data-label-dark", "data-label-light",
                    "data-aria-dark", "data-aria-light")


def theme_labels_externalised() -> list[str]:
    """The theme button's words live in the markup, not in site.js.

    site.js is shared by every language version, so any English string
    baked into it would leak onto the Polish and French pages.
    """
    fails = []
    js = read(JS)
    for banned in ("'Dark'", "'Light'", "'Switch to '"):
        if banned in js:
            fails.append(f"{JS} still hard-codes {banned}")
    for page in PAGES:
        for tag, attrs in tags_of(page):
            if tag != "button" or "theme-toggle" not in (attrs.get("class") or ""):
                continue
            for attr in THEME_DATA_ATTRS:
                if attrs.get(attr) is None:
                    fails.append(f"{page}: theme toggle missing {attr}")
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


PERSON_ID = "https://karol.chlasta.pl/#person"


def ld_blocks(rel: str) -> list[dict]:
    """Return every parsed application/ld+json block on a page."""
    import json
    pattern = re.compile(
        r'<script type="application/ld\+json">(.*?)</script>', re.S
    )
    out = []
    for raw in pattern.findall(read(rel)):
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            out.append({"__parse_error__": str(exc)})
    flat = []
    for node in out:
        if isinstance(node, dict) and "@graph" in node:
            flat.extend(node["@graph"])
        else:
            flat.append(node)
    return flat


# Values that must follow each home page's own visible content: the first
# jobTitle entry and the postal address locality. Everything else that
# identifies the entity (@id, identifier, sameAs, ...) must NOT vary here;
# see structured_data_matches_page_language below.
LOCALISED_PERSON_FIELDS = {
    "": {"jobTitle": "Assistant Professor", "addressLocality": "Warsaw"},
    "pl": {"jobTitle": "adiunkt", "addressLocality": "Warszawa"},
    "fr": {"jobTitle": "maître de conférences", "addressLocality": "Varsovie"},
}

# Fields that pin the three pages to a single entity. Google's own guidance is
# that structured data must reflect visible content, but the identity of the
# entity being described is not visible content — it is what makes the three
# translated pages provably describe one person rather than three unrelated
# ones. These must be byte-identical across every home page.
STABLE_PERSON_FIELDS = ("@id", "identifier", "sameAs")


def structured_data_matches_page_language() -> list[str]:
    """The Person node must agree with what the page actually says.

    Task 11 found pl/index.html and fr/index.html both carrying the English
    Person node verbatim: a Polish page reading "adiunkt w Akademii Leona
    Koźmińskiego" whose own JSON-LD claimed "Assistant Professor" at
    "Kozminski University". That mismatch is exactly what Google's structured
    data guidelines warn against, so this check pins the translatable fields
    to each language and the identity fields to each other.
    """
    fails = []
    persons = {}
    for lang in LANGS:
        rel = page_file("home", lang)
        people = [node for node in ld_blocks(rel) if node.get("@type") == "Person"]
        if len(people) != 1:
            fails.append(f"{rel}: expected exactly 1 Person node, found {len(people)}")
            continue
        persons[lang] = people[0]

    for lang, expected in LOCALISED_PERSON_FIELDS.items():
        person = persons.get(lang)
        if person is None:
            continue
        rel = page_file("home", lang)
        locality = (person.get("address") or {}).get("addressLocality")
        if locality != expected["addressLocality"]:
            fails.append(
                f'{rel}: addressLocality is {locality!r}, expected {expected["addressLocality"]!r}'
            )
        job_titles = person.get("jobTitle") or []
        first_job = job_titles[0] if job_titles else None
        if first_job != expected["jobTitle"]:
            fails.append(
                f'{rel}: first jobTitle is {first_job!r}, expected {expected["jobTitle"]!r}'
            )

    langs_present = list(persons)
    if len(langs_present) > 1:
        base_lang = langs_present[0]
        base = persons[base_lang]
        base_rel = page_file("home", base_lang)
        for lang in langs_present[1:]:
            person = persons[lang]
            rel = page_file("home", lang)
            for field in STABLE_PERSON_FIELDS:
                if person.get(field) != base.get(field):
                    fails.append(
                        f"{rel}: {field} does not match {base_rel} "
                        "(the three pages must describe the same entity)"
                    )
    return fails


def person_has_stable_id() -> list[str]:
    """Every homepage must describe the same Person, pinned by @id.

    Without @id, three pages each declaring "a Person named Karol Chlasta"
    may or may not be merged into one entity by a consumer. With it, they
    provably describe one.
    """
    fails = []
    for page in LD_PAGES:
        people = [
            node for node in ld_blocks(page)
            if node.get("@type") == "Person"
        ]
        if len(people) != 1:
            fails.append(f"{page}: expected exactly 1 Person node, found {len(people)}")
            continue
        person = people[0]
        if person.get("@id") != PERSON_ID:
            fails.append(f'{page}: Person @id is {person.get("@id")!r}, expected {PERSON_ID!r}')
        if ORCID not in str(person.get("identifier", "")):
            fails.append(f"{page}: Person node does not carry the ORCID")
    return fails


# hreflang carries a *country* in its second component, so the region-free
# forms are deliberate: "en-GB" would exclude Ireland and the United States,
# "fr-FR" would exclude Switzerland, where Wyden is based.
HREFLANG = {"": "en", "pl": "pl", "fr": "fr"}


def hreflang_reciprocity() -> list[str]:
    """Every page lists all three versions and itself, plus x-default."""
    fails = []
    for lang in LANGS:
        for page in PATHS:
            rel = page_file(page, lang)
            src = read(rel)
            if not src:
                continue
            for other, code in HREFLANG.items():
                needle = f'<link rel="alternate" hreflang="{code}" href="{page_url(page, other)}">'
                if needle not in src:
                    fails.append(f"{rel}: missing alternate {code} -> {page_url(page, other)}")
            xdefault = f'<link rel="alternate" hreflang="x-default" href="{page_url(page, "")}">'
            if xdefault not in src:
                fails.append(f"{rel}: missing x-default")
    return fails


def en_alias_redirects() -> list[str]:
    src = read(EN_ALIAS)
    fails = []
    if 'http-equiv="refresh"' not in src:
        fails.append(f"{EN_ALIAS} has no meta refresh")
    if 'rel="canonical" href="https://karol.chlasta.pl/"' not in src:
        fails.append(f"{EN_ALIAS} does not declare the root as canonical")
    if "hreflang" in src:
        fails.append(f"{EN_ALIAS} must not participate in the hreflang set")
    return fails


def webpage_inlanguage() -> list[str]:
    """Each homepage needs a WebPage node stating its own language."""
    fails = []
    for page, lang in LD_PAGES.items():
        pages = [
            node for node in ld_blocks(page)
            if node.get("@type") == "WebPage"
        ]
        if len(pages) != 1:
            fails.append(f"{page}: expected exactly 1 WebPage node, found {len(pages)}")
            continue
        node = pages[0]
        if node.get("inLanguage") != lang:
            fails.append(f'{page}: WebPage inLanguage is {node.get("inLanguage")!r}, expected {lang!r}')
        main = node.get("mainEntity")
        ref = main.get("@id") if isinstance(main, dict) else main
        if ref != PERSON_ID:
            fails.append(f"{page}: WebPage mainEntity does not point at {PERSON_ID}")
    return fails


def sitemap_complete() -> list[str]:
    src = read("sitemap.xml")
    fails = []
    for lang in LANGS:
        for page in PATHS:
            url = page_url(page, lang)
            if f"<loc>{url}</loc>" not in src:
                fails.append(f"sitemap.xml does not list {url}")
    if "karol.chlasta.pl/en/" in src:
        fails.append("sitemap.xml lists the /en/ alias, which is a redirect")
    if src.count("<url>") != len(LANGS) * len(PATHS):
        fails.append(f"sitemap.xml has {src.count('<url>')} entries, expected 9")
    return fails


CHECKS = [
    no_cra_leftovers, required_files,
    language_versions_exist, lang_attribute_matches_path, canonical_is_self,
    internal_links, no_stale_refs,
    images_complete, fonts_present, no_phone_in_pdfs, publications, talks,
    theses_and_preprints, orcid_linked, polish_annotated, paper_licences,
    meta_complete, person_has_stable_id, structured_data_matches_page_language,
    webpage_inlanguage, sw_killswitch,
    theme_tokens, no_emoji_flags, switcher_styles_present, theme_labels_externalised, focus_visible, icons_are_ours, ai_crawler_policy,
    hreflang_reciprocity, en_alias_redirects,
    switcher_on_every_page, switcher_accessible_names, slug_map_consistent,
    sitemap_complete,
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
