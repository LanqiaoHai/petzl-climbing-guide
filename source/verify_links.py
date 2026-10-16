"""Verify article pages without replacing successful inputs on failure."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import html
import json
import re
import sys
import time
import unicodedata

BASE = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (compatible; PersonalPetzlIndex/1.0; public metadata only)"
EXCLUDE = {
    "a77w0000000TOoAAAW", "a77w0000000TOoPAAW", "a77w0000000KytuAAC",
    "a77w0000000Kyo1AAC", "a77w0000000KyrPAAS", "a77w0000000KyrUAAS",
    "a77w0000000Kys3AAC", "a77w0000000Kyl2AAC", "a77bK000007SPp3QAG",
    "a771r000000TPyuAAG",
}
INCLUDE = {"a771r000000Co9qAAC", "a77w0000000PC34AAG"}
EXCLUDED_TITLE = re.compile(
    r"\b(?:ski(?:ing)?|crevasse(?:s)?|rebelays?|slacklin(?:e|ing)|caving|canyoning)\b",
    re.I,
)
ARTICLE_ID = re.compile(r"[._]SPO_([A-Za-z0-9]{18})\.html")
VIDEO = re.compile(
    r"(?:youtube(?:-nocookie)?\.com/embed/|player\.vimeo\.com/video/|<video\b)",
    re.I,
)


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def clean(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", "", value)).replace("�C", "–").replace("�c", "–")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


class ArticleParser(HTMLParser):
    """Collect only the detail body, excluding navigation and related cards."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.body = []
        self.title = []
        self.canonical = ""
        self.body_present = False
        self.title_seen = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        classes = set((attrs_dict.get("class") or "").split())
        parent = self.stack[-1] if self.stack else ("", False, False, False)
        inside = parent[1] or "product-content-body" in classes
        excluded = parent[2] or bool(classes & {"product-content-related", "product-content-recommendations"})
        title = parent[3] or (tag == "h1" and inside and not excluded and not self.title_seen)
        if "product-content-body" in classes:
            self.body_present = True
        if tag == "link" and "canonical" in (attrs_dict.get("rel") or "").split():
            self.canonical = attrs_dict.get("href") or ""
        if inside and not excluded:
            self.body.append(self.get_starttag_text() or "")
        if tag not in self.VOID:
            self.stack.append((tag, inside, excluded, title))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            frame = self.stack[index]
            if frame[0] != tag:
                continue
            if frame[1] and not frame[2]:
                self.body.append("</" + tag + ">")
            if tag == "h1" and frame[3]:
                self.title_seen = True
            del self.stack[index:]
            break

    def handle_data(self, value):
        if not self.stack:
            return
        _, inside, excluded, title = self.stack[-1]
        if inside and not excluded:
            self.body.append(value)
            if title:
                self.title.append(value)


def selection_status(row: dict) -> str:
    if row["scope"] == "主目录" or row["id"] in INCLUDE:
        return "selected"
    products = set(row.get("product_sources", []))
    if products and products.issubset({"RAD-LINE-6-MM", "RAD-SYSTEM"}):
        return "pending_scope"
    if row["id"] in EXCLUDE or EXCLUDED_TITLE.search(row["title_en"]):
        return "excluded"
    return "selected"


def select_articles(snapshot: dict) -> list[dict]:
    return [row for row in snapshot["articles"] if selection_status(row) == "selected"]


def cache_is_usable(article: dict, cached: dict, max_age_days: float = 7) -> bool:
    if not (cached.get("http_status") == 200 and cached.get("title_matches") is True
            and not cached.get("error") and cached.get("url") == article["url"]
            and clean(cached.get("page_title", "")).casefold() == clean(article["title_en"]).casefold()):
        return False
    try:
        verified_at = datetime.fromisoformat(cached["verified_at"])
        if verified_at.tzinfo is None:
            return False
        age = datetime.now(TZ) - verified_at
        return -timedelta(minutes=5) <= age <= timedelta(days=max_age_days)
    except (KeyError, TypeError, ValueError):
        return False


def verify_article(article: dict, *, attempts: int = 3, timeout: float = 35,
                   sleep_fn=time.sleep) -> dict:
    result = {"id": article["id"], "url": article["url"], "verified_at": now()}
    for attempt in range(attempts):
        try:
            request = Request(article["url"], headers={"User-Agent": UA})
            with urlopen(request, timeout=timeout) as response:
                text = response.read().decode("utf-8", "replace")
                result.update(http_status=response.status, final_url=response.url)
            parser = ArticleParser()
            parser.feed(text)
            parser.close()
            body = "".join(parser.body)
            result["page_title"] = clean(" ".join(parser.title))
            result["title_matches"] = result["page_title"].casefold() == clean(article["title_en"]).casefold()
            result["canonical"] = html.unescape(parser.canonical) or result["final_url"]
            result["linked_article_ids"] = list(dict.fromkeys(ARTICLE_ID.findall(body)))
            result["has_video_embed"] = bool(VIDEO.search(html.unescape(body)))
            result["body_present"] = parser.body_present
            result["attempts"] = attempt + 1
            errors = []
            if result["http_status"] != 200:
                errors.append("HTTP status is not 200")
            if not result["title_matches"]:
                errors.append("Article heading does not match the catalogue title")
            if not parser.body_present:
                errors.append("Article detail body is missing")
            if errors:
                result["error"] = "; ".join(errors)
            break
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            retryable = not isinstance(error, HTTPError) or error.code in {408, 429} or error.code >= 500
            if retryable and attempt + 1 < attempts:
                sleep_fn(1 + attempt)
                continue
            result.update(http_status=error.code if isinstance(error, HTTPError) else "error",
                          error=str(error), page_title="", title_matches=False,
                          linked_article_ids=[], has_video_embed=False, attempts=attempt + 1)
            break
        except Exception as error:
            result.update(http_status="error", error=str(error), page_title="", title_matches=False,
                          linked_article_ids=[], has_video_embed=False, attempts=attempt + 1)
            break
    sleep_fn(0.3)
    return result


def atomic_json(path: Path, value) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def commit_results(base: Path, results: dict, articles: list[dict], selection_report=None) -> None:
    outputs = {base / "verification.json": results, base / "selected_articles.json": articles}
    if selection_report is not None:
        outputs[base / "selection_report.json"] = selection_report
    previous = {path: path.read_bytes() if path.exists() else None for path in outputs}
    written = []
    try:
        for path, value in outputs.items():
            atomic_json(path, value)
            written.append(path)
    except Exception:
        for path in written:
            if previous[path] is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(previous[path])
        raise


def run(base: Path = BASE, *, refresh: bool = False, max_age_days: float = 7,
        workers: int = 2, attempts: int = 3, timeout: float = 35,
        sleep_fn=time.sleep) -> int:
    snapshot = json.loads((base / "crawl_snapshot.json").read_text(encoding="utf-8"))
    articles = select_articles(snapshot)
    selection_report = {"selected_count": len(articles), "decisions": [
        {"id": row["id"], "title_en": row["title_en"], "product_sources": row.get("product_sources", []), "decision": selection_status(row)}
        for row in snapshot["articles"]
    ]}
    old_path = base / "verification.json"
    old = json.loads(old_path.read_text(encoding="utf-8")) if old_path.exists() else {}
    reused = []

    def job(article):
        cached = old.get(article["id"], {})
        if not refresh and cache_is_usable(article, cached, max_age_days):
            reused.append(article["id"])
            return article["id"], cached
        result = verify_article(article, attempts=attempts, timeout=timeout, sleep_fn=sleep_fn)
        print(article["id"], result["http_status"], "OK" if not result.get("error") else "CHECK", flush=True)
        return article["id"], result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = dict(pool.map(job, articles))
    failures = [row for row in results.values()
                if row.get("http_status") != 200 or row.get("title_matches") is not True or row.get("error")]
    if not articles:
        failures.append({"error": "No articles were selected; refusing to replace the successful directory."})
    if failures:
        report = {"attempted_at": now(), "article_count": len(articles), "failure_count": len(failures),
                  "cache_reused_ids": reused, "failures": failures, "verification": results,
                  "successful_outputs_preserved": True, "scope_selection": selection_report}
        failure_path = base / "verification_failure.json"
        atomic_json(failure_path, report)
        print(f"Verification failed for {len(failures)} article(s); previous inputs kept. See {failure_path}", file=sys.stderr)
        return 1
    commit_results(base, results, articles, selection_report)
    print(f"Verified {len(results)}/{len(articles)} articles; {len(reused)} cached results reused with their original dates.", flush=True)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Ignore all cached verification results")
    parser.add_argument("--max-cache-days", type=float, default=7)
    args = parser.parse_args(argv)
    if args.max_cache_days < 0:
        parser.error("--max-cache-days must be nonnegative")
    try:
        return run(refresh=args.refresh, max_age_days=args.max_cache_days)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"Verification did not complete; successful inputs kept: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


