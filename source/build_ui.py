#!/usr/bin/env python3
"""Build the offline Petzl tutorial index with Python's standard library.

Run:
    python build_ui.py
    python build_ui.py --input catalog.json --output index.html

The output embeds both the catalogue and the design tokens. It opens directly
through file:// and requires no local server, external fonts, CDN, or fetch.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
DATA_MARKER = "__CATALOG_JSON__"
TOKEN_MARKER = "/*__TOKENS__*/"


def load_catalog(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        catalog = json.load(handle)
    if not isinstance(catalog, dict):
        raise ValueError("catalog.json must contain an object.")
    if not isinstance(catalog.get("meta", {}), dict):
        raise ValueError("meta must be an object.")
    for key in ("articles", "resources"):
        if not isinstance(catalog.get(key, []), list):
            raise ValueError(f"{key} must be an array.")
    seen = set()
    for position, article in enumerate(catalog.get("articles", []), 1):
        if not isinstance(article, dict):
            raise ValueError(f"Article {position} must be an object.")
        article_id = str(article.get("id", "")).strip()
        if not article_id:
            raise ValueError(f"Article {position} has no id.")
        if article_id in seen:
            raise ValueError(f"Duplicate article id: {article_id}")
        seen.add(article_id)
        if not (article.get("title_en") or article.get("title_zh")):
            raise ValueError(f"Article {article_id} has no title.")
        if not article.get("url"):
            raise ValueError(f"Article {article_id} has no source URL.")
        for field in ("aliases", "activities", "official_sections", "equipment", "topics"):
            if field in article and not isinstance(article[field], list):
                raise ValueError(f"Article {article_id}: {field} must be an array.")
    return catalog


def embedded_json(value: dict) -> str:
    """Escape HTML-sensitive characters, including any closing script tag."""
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (
        serialized.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build(catalog_path: Path, template_path: Path, tokens_path: Path, output_path: Path) -> None:
    catalog = load_catalog(catalog_path)
    template = template_path.read_text(encoding="utf-8-sig")
    tokens = tokens_path.read_text(encoding="utf-8-sig")
    for marker in (DATA_MARKER, TOKEN_MARKER):
        if template.count(marker) != 1:
            raise ValueError(f"The template must contain exactly one {marker} marker.")
    output = template.replace(TOKEN_MARKER, tokens).replace(DATA_MARKER, embedded_json(catalog))
    if output_path.resolve() in {catalog_path.resolve(), template_path.resolve(), tokens_path.resolve()}:
        raise ValueError("Output must not overwrite an input file.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8", newline="\n")
    print(f"Built {output_path} ({len(catalog.get('articles', []))} tutorials, {len(catalog.get('resources', []))} resources)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=BASE / "catalog.json", help="Catalogue JSON")
    parser.add_argument("--template", type=Path, default=BASE / "index.template.html", help="HTML template")
    parser.add_argument("--tokens", type=Path, default=BASE / "tokens.css", help="Design token CSS")
    parser.add_argument("--output", type=Path, default=BASE / "index.html", help="Standalone HTML output")
    args = parser.parse_args()
    try:
        build(args.input, args.template, args.tokens, args.output)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Cannot build Petzl index: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

