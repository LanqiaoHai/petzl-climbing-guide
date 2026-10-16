"""Prepare a clean, static GitHub Pages repository without publishing anything.

Run from the maintained catalogue directory:
    python prepare_github_publish.py

The generated _发布GitHub directory contains docs/, source/, and README.md.
Only explicit allowlisted files are copied. No Git repository, credentials,
network request, or remote write is created by this script.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

BASE = Path(__file__).resolve().parent
PAGES_URL = "https://lanqiaohai.github.io/petzl-climbing-guide/"
OUTPUT_NAME = "_发布GitHub"
MARKDOWN = "Petzl攀岩教程目录.md"
CSV = "Petzl攀岩教程目录.csv"
SOURCE_FILES = (
    "crawl_petzl.py", "verify_links.py", "assemble_catalog.py", "build_ui.py",
    "package_catalog.py", "prepare_github_publish.py", "更新目录.ps1",
    "index.template.html", "tokens.css", "title_translations.json",
    "resources.json", "catalog_overrides.json",
)
ZIP_FILES = set(SOURCE_FILES) | {
    "index.html", MARKDOWN, CSV, "使用说明.md", "catalog.json",
    "覆盖与链接核验.json", "crawl_snapshot.json", "selected_articles.json",
    "verification.json", "selection_report.json", "robots_snapshot.txt",
    "titles_for_translation.json",
}
TEXT_SUFFIXES = {".html", ".json", ".md", ".csv", ".py", ".ps1", ".css", ".txt"}
LOCAL_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|/(?:Users|home)/|/mnt/"
    r"data/)"
)
SECRET = re.compile(
    r"(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"sk-(?:proj-)?[A-Za-z0-9_-]{24,}|"
    r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----)"
)
ZIP_NAME = re.compile(r"Petzl攀岩教程目录_(\d{4}-\d{2}-\d{2})\.zip")


def scan_public_text(name: str, content: bytes) -> None:
    """Reject private local paths and common secret formats without echoing them."""
    if Path(name).suffix.lower() not in TEXT_SUFFIXES:
        return
    text = content.decode("utf-8-sig")
    if LOCAL_PATH.search(text):
        raise ValueError(f"Private absolute path detected in {name}; publish preparation stopped.")
    if SECRET.search(text):
        raise ValueError(f"Potential credential detected in {name}; publish preparation stopped.")


def read_public_file(root: Path, name: str) -> bytes:
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Required regular file missing or symlinked: {name}")
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError(f"Unexpectedly large publication input: {name}")
    content = path.read_bytes()
    scan_public_text(name, content)
    return content


def catalogue_statistics(catalog: dict) -> dict:
    articles = catalog.get("articles")
    resources = catalog.get("resources", [])
    meta = catalog.get("meta", {})
    if not isinstance(articles, list) or not isinstance(resources, list) or not isinstance(meta, dict):
        raise ValueError("Catalogue must contain article/resource arrays and a metadata object.")
    article_ids = [article.get("id") for article in articles]
    if any(not article_id for article_id in article_ids) or len(set(article_ids)) != len(article_ids):
        raise ValueError("Catalogue contains a missing or duplicate article ID.")
    core = sum(article.get("scope") == "主目录" for article in articles)
    verified = sum(
        article.get("http_status") == 200 and article.get("title_matches") is True
        for article in articles
    )
    result = {
        "total": len(articles), "core": core, "extension": len(articles) - core,
        "resources": len(resources), "verified": verified,
        "topics": len({topic for article in articles for topic in article.get("topics", [])}),
        "date": str(meta.get("date", "")),
        "source_fetched_from": str(meta.get("source_fetched_from", "")),
        "source_fetched_until": str(meta.get("source_fetched_until", "")),
        "verification_started_at": str(meta.get("verification_started_at", "")),
        "verification_completed_at": str(meta.get("verification_completed_at", "")),
    }
    date.fromisoformat(result["date"])
    for key, actual in (
        ("total_count", result["total"]), ("core_count", result["core"]),
        ("extension_count", result["extension"]), ("resource_count", result["resources"]),
        ("verified_count", result["verified"]),
    ):
        if key in meta and meta[key] != actual:
            raise ValueError(f"Catalogue metadata does not match article data: {key}")
    if not articles or verified != len(articles):
        raise ValueError("All published article links must have HTTP 200 and matching detail titles.")
    downloads = meta.get("downloads", {})
    if downloads.get("csv", CSV) != CSV or downloads.get("markdown", MARKDOWN) != MARKDOWN:
        raise ValueError("Catalogue download filenames do not match the maintained Chinese filenames.")
    archive_name = downloads.get("zip", f"Petzl攀岩教程目录_{result['date']}.zip")
    match = ZIP_NAME.fullmatch(str(archive_name))
    if not match or match.group(1) != result["date"]:
        raise ValueError("ZIP download name must match the current catalogue snapshot date.")
    result["zip"] = str(archive_name)
    return result


def verify_embedded_catalog(html_bytes: bytes, expected: dict) -> None:
    html = html_bytes.decode("utf-8-sig")
    match = re.search(
        r'<script\b[^>]*\bid=["\x27]catalog-data["\x27][^>]*>(.*?)</script\s*>',
        html, re.S | re.I,
    )
    if not match or json.loads(match.group(1)) != expected:
        raise ValueError("index.html embeds a different catalogue; rebuild the HTML before publishing.")


def validate_archive(content: bytes, current: dict[str, bytes]) -> None:
    """Inspect every archived file, including durable JSON provenance metadata."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        infos = archive.infolist()
        if len(infos) > 100 or sum(info.file_size for info in infos) > 32 * 1024 * 1024:
            raise ValueError("Archive exceeds the clean-distribution size or file-count limit.")
        found = {}
        for info in infos:
            if info.is_dir():
                continue
            path = PurePosixPath(info.filename)
            if (
                path.is_absolute() or ".." in path.parts or len(path.parts) != 2
                or path.parts[0] != "Petzl教程目录" or path.name not in ZIP_FILES
                or "\\" in info.filename or ":" in info.filename
            ):
                raise ValueError("Archive contains a non-allowlisted or unsafe path.")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("Archive contains a symlink.")
            if path.name in found:
                raise ValueError("Archive contains a duplicate filename.")
            data = archive.read(info)
            scan_public_text(path.name, data)
            found[path.name] = data
        required = set(SOURCE_FILES) - {"prepare_github_publish.py"}
        required |= {"index.html", MARKDOWN, CSV, "catalog.json"}
        missing = required - set(found)
        if missing:
            raise ValueError("Archive lacks maintenance inputs: " + ", ".join(sorted(missing)))
        for name in ("index.html", MARKDOWN, CSV, "catalog.json"):
            if found[name] != current[name]:
                raise ValueError(f"Archive contains a stale {name}; run package_catalog.py again.")
        for name in required & set(SOURCE_FILES):
            if found[name] != current[name]:
                raise ValueError(f"Archive contains a stale maintenance input: {name}")
        corrupt = archive.testzip()
        if corrupt:
            raise ValueError("Archive failed its CRC integrity check.")


def markdown_readme(catalog: dict, stats: dict) -> bytes:
    meta = catalog["meta"]
    archive = stats["zip"]
    lines = [
        "# Petzl 攀岩教程中文索引", "",
        f"[打开在线目录]({PAGES_URL})", "",
        "这是个人整理的中文检索索引，非 Petzl 官方网站或官方中文译本。",
        "收录标题、分类、装备关键词和官方原文链接，帮助查找分散的技术资料；不复制教程正文。",
        "原文、插图、商标与相关资料的版权归各自作者或权利人所有。", "",
        f"当前目录日期：**{stats['date']}**。共 **{stats['total']} 篇**，"
        f"其中 {stats['core']} 篇攀岩主目录、{stats['extension']} 篇装备扩展；"
        f"另列 {stats['resources']} 项官方手册、FAQ 与资料入口。",
        f"正文链接核验：{stats['verified']}/{stats['total']} 个 HTTP 200 且详情标题匹配。"
        "这些统计直接从本次 catalog.json 计算，不是固定写入的数量。",
        meta.get("coverage_note", ""),
        meta.get("scope_note", ""),
        meta.get("language_note", ""), "",
        "## 下载", "",
        f"- [分类目录 Markdown](docs/{MARKDOWN})",
        f"- [CSV 表格](docs/{CSV})",
        f"- [完整离线目录 ZIP](docs/{archive})",
        "- [结构化目录 JSON](docs/catalog.json)", "",
        "ZIP 解压后双击 index.html 即可离线搜索与筛选；打开官方原文需要联网。",
        "收藏与已读只保存在当前浏览器，本仓库与发布脚本不读取或上传个人收藏。",
        "在线版支持导出收藏为浏览器书签。", "",
        "## 仓库结构", "",
        "- docs/：GitHub Pages 的静态页面、目录数据与下载文件。",
        "- source/：Python 标准库维护脚本、页面模板、设计 token、译题与人工覆盖规则。",
        "- README.md：当前统计、来源说明和维护方法。",
        "不包含网页抓取缓存、全量原文、临时调试脚本、浏览器存储或任何 GitHub 凭据。", "",
        "## 手动更新", "",
        "需要 Python 3.10+、PowerShell 与网络；无 pip 依赖。在仓库根目录运行：", "",
        "~~~powershell",
        "Set-Location source",
        ".\\更新目录.ps1",
        "python .\\prepare_github_publish.py --output ..\\_发布GitHub",
        "~~~", "",
        "更新脚本会重新读取官网公开栏目、核验链接、生成页面和当天目录包；"
        "失败时保留或恢复上一份可用目录。未译的新标题会保留英文并标记待译。",
        "完成后审阅 _发布GitHub 中生成的 docs/、source/ 与 README.md，"
        "将这些内容同步回仓库，再提交并推送。GitHub Pages 使用 main 分支的 /docs 目录。",
        "prepare_github_publish.py 仅准备静态文件，不创建仓库、不初始化 Git、不推送或发布。", "",
        "## 来源与使用范围", "",
        "- [Petzl 室内外攀岩技术栏目](https://www.petzl.com/us/en/sport/tech-tips/indoor-and-outdoor-climbing)",
        "- [Petzl 多段攀岩技术栏目](https://www.petzl.com/us/en/sport/tech-tips/multi-pitch-climbing)",
        "完整性以已对账的活动栏目及已记录的装备入口为依据。"
        "同一文章在多个栏目出现时按官方文章编号合并；跨活动资料保留适用范围。",
        "目录是查找工具。具体操作的前提、限制与警示须核对官方原文和对应装备说明书，"
        "“已读”仅代表阅读记录。", "",
    ]
    for label, key in (
        ("栏目实际访问开始", "source_fetched_from"),
        ("栏目实际访问结束", "source_fetched_until"),
        ("正文核验开始", "verification_started_at"),
        ("正文核验结束", "verification_completed_at"),
    ):
        if stats[key]:
            lines.append(f"- {label}：{stats[key]}")
    lines.append("")
    result = ("\n".join(lines)).encode("utf-8")
    scan_public_text("README.md", result)
    return result


def validate_destination(source_root: Path, output: Path) -> Path:
    source_root = source_root.resolve()
    if output.is_symlink():
        raise ValueError("Output must not be a symlink.")
    output = output.resolve()
    if output.name != OUTPUT_NAME or output == source_root or output in source_root.parents:
        raise ValueError("Output must be a separate directory named _发布GitHub.")
    inside_source = output.is_relative_to(source_root)
    sibling_of_source = source_root.name == "source" and output.parent == source_root.parent
    if not (inside_source or sibling_of_source):
        raise ValueError("Output must stay inside the project, or beside its source/ directory.")
    if output.is_symlink():
        raise ValueError("Output must not be a symlink.")
    return output


def prepare(source_root: Path, output: Path) -> dict:
    source_root = source_root.resolve()
    output = validate_destination(source_root, output)
    generated_root = source_root
    if not (generated_root / "catalog.json").is_file() and source_root.name == "source":
        generated_root = source_root.parent / "docs"
    catalog_bytes = read_public_file(generated_root, "catalog.json")
    catalog = json.loads(catalog_bytes.decode("utf-8-sig"))
    stats = catalogue_statistics(catalog)
    current = {"catalog.json": catalog_bytes}
    for name in ("index.html", MARKDOWN, CSV):
        current[name] = read_public_file(generated_root, name)
    verify_embedded_catalog(current["index.html"], catalog)
    source_bytes = {name: read_public_file(source_root, name) for name in SOURCE_FILES}
    current.update(source_bytes)
    archive_path = generated_root / stats["zip"]
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ValueError("The catalogue-date ZIP is missing; run package_catalog.py first.")
    archive_bytes = archive_path.read_bytes()
    validate_archive(archive_bytes, current)
    files = {
        "docs/index.html": current["index.html"],
        "docs/" + MARKDOWN: current[MARKDOWN],
        "docs/" + CSV: current[CSV],
        "docs/catalog.json": catalog_bytes,
        "docs/" + stats["zip"]: archive_bytes,
        "docs/.nojekyll": b"",
        "README.md": markdown_readme(catalog, stats),
    }
    files.update({"source/" + name: content for name, content in source_bytes.items()})
    expected_dirs = {"docs", "source"}
    obsolete_archives = []
    # Never recursively delete an existing tree or follow symlinks.
    if output.exists():
        for existing in output.rglob("*"):
            relative = existing.relative_to(output).as_posix()
            if existing.is_symlink():
                raise ValueError("Existing publication output contains a symlink.")
            if existing.is_dir():
                if relative not in expected_dirs:
                    raise ValueError("Existing publication output contains an unexpected directory.")
                continue
            if relative in files:
                continue
            if existing.parent == output / "docs" and ZIP_NAME.fullmatch(existing.name):
                obsolete_archives.append(existing)
                continue
            raise ValueError("Existing publication output contains an unexpected file: " + relative)
    # All validation occurs before any output is created or overwritten.
    output.mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        destination = output / relative
        if not destination.resolve().is_relative_to(output):
            raise ValueError("Publication destination escaped the validated output directory.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    for obsolete in obsolete_archives:
        if obsolete.resolve().parent != (output / "docs").resolve():
            raise ValueError("Obsolete archive escaped the validated docs directory.")
        obsolete.unlink()
    return {
        "output_directory": OUTPUT_NAME, "pages_url": PAGES_URL,
        "statistics": stats,
        "files": [
            {"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            for name, content in sorted(files.items())
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE, help="Maintenance source directory")
    parser.add_argument("--output", type=Path, help="Clean _发布GitHub staging directory")
    args = parser.parse_args(argv)
    source_root = args.base.resolve()
    output = args.output or source_root / OUTPUT_NAME
    try:
        result = prepare(source_root, output)
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as error:
        print("GitHub publish preparation failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

