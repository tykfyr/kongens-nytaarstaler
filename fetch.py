#!/usr/bin/env python3
"""
Fetch latest King's New Year speech link from Kongehuset "nytårstaler" page.

Rules:
- The page contains multiple accordions (first = Kongen, second = Dronningen).
- We ONLY parse links from the FIRST accordion on the page.
- We pick the highest year found in that accordion.
- We then fetch the speech page and extract readable text paragraphs.
- We write taler/<YEAR>.md if it doesn't already exist.

Usage:
  python scripts/fetch_latest.py
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


INDEX_URL = "https://www.kongehuset.dk/monarkiet-i-danmark/nytaarstaler/"
BASE_URL = "https://www.kongehuset.dk"

# Year in titles like: "H.M. Kongens nytårstale 2024"
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

# Typical path format today (can change, so we keep a fallback)
SPEECH_HREF_RE = re.compile(r"^/nyheder/laes-.*-nytaarstale-\d{4}/?$")


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
    first = soup.select_one("div.accordion")
    if not first:
        raise RuntimeError("Fandt ingen .accordion på siden.")
    return first


def choose_best_link(item) -> str | None:
    """
    Pick the best link inside an accordion item.

    Priority:
    1) Link that matches SPEECH_HREF_RE (current known speech URL pattern)
    2) Link whose text/title contains 'nytårstale' (case-insensitive)
    3) First internal link (fallback)
    """
    links = item.select('.accordion__container__item__content a[href^="/"]')
    if not links:
        return None

    # 1) known url pattern
    for a in links:
        href = (a.get("href") or "").strip()
        if SPEECH_HREF_RE.match(href):
            return href

    # 2) heuristic on link text/title
    for a in links:
        txt = (a.get_text(" ", strip=True) or "").lower()
        title = (a.get("title") or "").lower()
        if "nytårstale" in txt or "nytårstale" in title:
            return (a.get("href") or "").strip()

    # 3) fallback
    return (links[0].get("href") or "").strip()


def find_latest_from_first_accordion(index_html: str) -> tuple[int, str]:
    soup = BeautifulSoup(index_html, "html.parser")
    root = get_first_accordion(soup)

    candidates: list[tuple[int, str]] = []

    for item in root.select(".accordion__container__item"):
        title_btn = item.select_one(".accordion__container__item__title__toggle")
        title_text = title_btn.get_text(" ", strip=True) if title_btn else ""

        m = YEAR_RE.search(title_text)
        if not m:
            continue
        year = int(m.group(0))

        href = choose_best_link(item)
        if not href or not href.startswith("/"):
            continue

        candidates.append((year, BASE_URL + href))

    if not candidates:
        raise RuntimeError("Fandt ingen kandidater i første accordion (Kongen).")

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0]


def extract_title_and_text(html: str) -> tuple[str, str]:
    """
    Extract title + readable paragraphs from the speech page.
    This is intentionally pragmatic, not perfect.
    """
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else "Kongens nytårstale"

    main = soup.find("main") or soup
    paragraphs = [p.get_text(" ", strip=True) for p in main.find_all("p")]
    text = "\n\n".join([p for p in paragraphs if p])

    # Simple sanity check: avoid saving empty/garbled pages
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

    year, speech_url = find_latest_from_first_accordion(index_html)

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