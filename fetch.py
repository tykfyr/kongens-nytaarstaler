#!/usr/bin/env python3
"""
Fetch latest King's New Year speech from Kongehuset "nytårstaler" page.

Key detail (based on current HTML):
- The FIRST accordion contains "H.M. Kongens nytårstaler" (no year in title)
- The years are in the LINKS inside the accordion content (e.g. "Nytårstalen 2025")
- Links may be absolute (https://www.kongehuset.dk/...) or relative (/nyheder/...)

Output:
- Writes taler/<YEAR>.md if not already present
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


INDEX_URL = "https://www.kongehuset.dk/monarkiet-i-danmark/nytaarstaler/"
BASE_URL = "https://www.kongehuset.dk"

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def get_html(url: str) -> str:
    r = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "kongens-nytaarstaler-bot/1.0 (+https://github.com/tykfyr/kongens-nytaarstaler)"
        },
    )
    r.raise_for_status()
    return r.text


def get_first_accordion(soup: BeautifulSoup):
    accordions = soup.select("div.accordion")
    if not accordions:
        raise RuntimeError("Fandt ingen .accordion på siden.")
    return accordions[0]


def extract_year_from_link(a) -> int | None:
    """
    Try to find a year from:
    - link text: "Nytårstalen 2025"
    - title attribute
    - href
    """
    txt = (a.get_text(" ", strip=True) or "")
    title = (a.get("title") or "")
    href = (a.get("href") or "")

    for s in (txt, title, href):
        m = YEAR_RE.search(s)
        if m:
            return int(m.group(0))
    return None


def find_latest_speech_url(index_html: str) -> tuple[int, str]:
    soup = BeautifulSoup(index_html, "html.parser")
    root = get_first_accordion(soup)

    # Find ALL links in first accordion content
    links = root.select(".accordion__container__item__content a[href]")
    if not links:
        raise RuntimeError("Fandt ingen links i første accordion.")

    candidates: list[tuple[int, str]] = []
    for a in links:
        year = extract_year_from_link(a)
        if not year:
            continue

        href = (a.get("href") or "").strip()
        if not href:
            continue

        # Normalize to absolute URL
        url = href if href.startswith("http") else urljoin(BASE_URL, href)
        candidates.append((year, url))

    if not candidates:
        raise RuntimeError("Fandt ingen årstal i links i første accordion (Kongen).")

    # Pick highest year
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0]


def extract_title_and_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else "Kongens nytårstale"

    main = soup.find("main") or soup
    paragraphs = [p.get_text(" ", strip=True) for p in main.find_all("p")]
    text = "\n\n".join([p for p in paragraphs if p])

    if len(text) < 500:
        raise RuntimeError("Udtræk gav meget lidt tekst (markup kan have ændret sig).")

    return title, text


def write_markdown(year: int, title: str, source_url: str, text: str) -> Path:
    out_dir = Path("taler")
    out_dir.mkdir(parents=True, exist_ok=True)

    out_file = out_dir / f"{year}.md"
    if out_file.exists():
        return out_file

    fetched = datetime.now().strftime("%Y-%m-%d")
    md = f"""# {title}

Kilde: {source_url}
Hentet: {fetched}

---

{text}
"""
    out_file.write_text(md, encoding="utf-8")
    return out_file


def main() -> int:
    index_html = get_html(INDEX_URL)

    year, speech_url = find_latest_speech_url(index_html)

    out_file = Path("taler") / f"{year}.md"
    if out_file.exists():
        print(f"OK: {out_file} findes allerede. Ingen ændringer.")
        return 0

    speech_html = get_html(speech_url)
    title, text = extract_title_and_text(speech_html)

    written = write_markdown(year, title, speech_url, text)
    print(f"Skrev: {written}")
    print(f"URL: {speech_url}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.RequestException as e:
        print(f"HTTP ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)