#!/usr/bin/env python3
"""Resolve DOIs for the publications ORCID does not cover.

Writes a report for human approval. It does not edit the site — a top hit
from Crossref is a candidate, never a fact. For the migration paper, for
instance, Crossref's best match is the SSRN preprint rather than the
published record, which is why every row states the venue it found and
whether that venue agrees with the CV.

Run:  python3 tools/resolve_dois.py
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "docs/superpowers/notes/doi-candidates.md"

CONTACT = "karol@chlasta.pl"
API = "https://api.crossref.org/works"
ORCID_API = "https://pub.orcid.org/v3.0/0000-0002-6539-566X/works"

# (title as printed in the CV, journal or venue the CV names)
# Entries already resolved from ORCID are deliberately absent.
WANTED = [
    ("Enhancing dementia and cognitive decline detection with large language models "
     "and speech representation learning",
     "Frontiers in Neuroinformatics"),
    ("Sztuczna inteligencja w cyberbezpieczeństwie – wyzwania i możliwości",
     "Wielowymiarowość środowiska bezpieczeństwa"),
    ("Eksploracja metod uczenia maszynowego do weryfikacji adresów dla usprawnienia "
     "procesu zarządzania danymi organizacji",
     "Sztuczna inteligencja i automatyzacja procesów biznesowych"),
    ("AI-based screening for depression and social anxiety through eye tracking: "
     "An exploratory study",
     "International Journal of Marketing, Communication and New Media"),
    ("Liquid State Machines in parallel simulations of mammalian visual system "
     "on Raspberry Pi",
     "Bio-Algorithms and Med-Systems"),
    ("Designing Neural Simulation Pipeline for Liquid State Machines",
     "HPI Future SOC Lab Proceedings"),
    ("MyMigrationBot: A cloud-based Facebook social chatbot for migrant populations",
     "Annals of Computer Science and Information Systems"),
    ("Exploring neural columns for real-time information processing",
     "HPI Future SOC Lab Proceedings"),
    ("Exploring spiking neural networks for real-time information processing",
     "HPI Future SOC Lab Proceedings"),
    ("Liquid State Machines for real-time neural simulations",
     "Selected Topics in Applied Computer Science"),
]


def fetch(url: str, accept: str = "application/json") -> dict:
    request = urllib.request.Request(url, headers={
        "Accept": accept,
        "User-Agent": f"karol.chlasta.pl-build/1.0 (mailto:{CONTACT})",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def orcid_records() -> list[tuple[str, str, list[str]]]:
    data = fetch(ORCID_API)
    out = []
    for group in data.get("group", []):
        summary = group["work-summary"][0]
        title = summary["title"]["title"]["value"]
        year = ((summary.get("publication-date") or {}).get("year") or {}).get("value", "?")
        ids = [
            f'{e["external-id-type"]}:{e["external-id-value"]}'
            for e in (group.get("external-ids") or {}).get("external-id", [])
        ]
        out.append((year, title, ids))
    return sorted(out, key=lambda row: row[0], reverse=True)


def lookup(title: str) -> dict | None:
    query = urllib.parse.urlencode({
        "query.bibliographic": title,
        "rows": 1,
        "select": "DOI,title,container-title,issued",
    })
    items = fetch(f"{API}?{query}")["message"]["items"]
    return items[0] if items else None


def main() -> None:
    lines = [
        "# DOI candidates — awaiting approval",
        "",
        "## Authoritative: ORCID 0000-0002-6539-566X",
        "",
        "Curated by the author, so these are facts rather than candidates.",
        "",
        "| Year | Identifiers | Title |",
        "|---|---|---|",
    ]
    for year, title, ids in orcid_records():
        short = title if len(title) <= 66 else title[:63] + "…"
        lines.append(f"| {year} | {', '.join(f'`{i}`' for i in ids) or '—'} | {short} |")

    lines += [
        "",
        "## Candidates: Crossref by title",
        "",
        "Resolved for the publications ORCID does not list. **A `MISMATCH` means",
        "Crossref returned a different venue than the CV names** — usually a preprint",
        "record. Do not put a MISMATCH row on the site until it has been checked by",
        "hand. `NO RESULT` is expected for the HPI technical reports and the Polish",
        "book chapters, which are often not registered with Crossref at all; those",
        "entries link to the publisher instead.",
        "",
        "| # | Verdict | DOI | Crossref venue | CV venue | Title |",
        "|---|---|---|---|---|---|",
    ]

    accepted: list[tuple[str, str]] = []
    rejected: list[tuple[str, str, str]] = []
    for index, (title, expected) in enumerate(WANTED, 1):
        try:
            hit = lookup(title)
        except Exception:                                # noqa: BLE001
            lines.append(f"| {index} | LOOKUP FAILED | — | — | {expected} | {title[:57]}… |")
            rejected.append((title, "", "lookup failed"))
            continue
        if hit is None:
            lines.append(f"| {index} | NO RESULT | — | — | {expected} | {title[:57]}… |")
            rejected.append((title, "", "no result"))
            continue
        doi = hit.get("DOI", "")
        container = (hit.get("container-title") or [""])[0]
        verdict = "MATCH" if expected.lower()[:18] in container.lower() else "MISMATCH"
        if verdict == "MATCH":
            accepted.append((title, doi))
        else:
            rejected.append((title, doi, container))
        short = title if len(title) <= 60 else title[:57] + "…"
        lines.append(
            f"| {index} | {verdict} | `{doi}` | {container or '—'} | {expected} | {short} |"
        )
        time.sleep(1)                                    # be polite to Crossref

    lines += [
        "",
        "## Recommendation",
        "",
        f"**Use these {len(accepted)} DOIs** — the venue Crossref reports agrees with the CV:",
        "",
    ]
    for title, doi in accepted:
        lines.append(f"- `{doi}` — {title}")

    lines += [
        "",
        f"**Reject these {len(rejected)}.** Crossref matched on stray words and returned an",
        "unrelated record for each; putting them on the site would credit someone else's",
        "work. These entries link to the publisher's page instead of a DOI:",
        "",
    ]
    for title, doi, container in rejected:
        got = f"returned `{doi}` in *{container}*" if doi else container
        lines.append(f"- {title}\n  - {got}")

    lines += [""]

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwritten {REPORT}")


if __name__ == "__main__":
    main()
