"""Create a current, reproducible distribution of the offline Petzl directory."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import zipfile

BASE = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))
# Explicit allowlist: no browser storage, cache, private bookmarks or temp files.
FILES = (
    "index.html", "Petzl攀岩教程目录.md", "Petzl攀岩教程目录.csv", "使用说明.md",
    "catalog.json", "覆盖与链接核验.json", "更新目录.ps1", "crawl_petzl.py",
    "verify_links.py", "assemble_catalog.py", "build_ui.py", "package_catalog.py",
    "index.template.html", "tokens.css", "title_translations.json", "resources.json", "catalog_overrides.json",
    "crawl_snapshot.json", "selected_articles.json", "verification.json", "selection_report.json",
    "robots_snapshot.txt", "titles_for_translation.json",
)


def write_readme(base: Path, catalog: dict) -> None:
    articles = catalog["articles"]
    resources = catalog.get("resources", [])
    meta = catalog.get("meta", {})
    core = sum(row.get("scope") == "主目录" for row in articles)
    extension = len(articles) - core
    verified = sum(row.get("http_status") == 200 and row.get("title_matches") is True for row in articles)
    pending = sum(row.get("translation_status") == "待译" or row.get("title_zh", "").startswith("待译") for row in articles)
    topics = {topic for row in articles for topic in row.get("topics", [])}
    dates = sorted(row["verified_at"] for row in articles if row.get("verified_at"))
    verification_time = " 至 ".join([dates[0], dates[-1]]) if dates else "尚未记录"
    source = json.loads((base / "crawl_snapshot.json").read_text(encoding="utf-8-sig"))
    activities = [row for row in source.get("sources", []) if row.get("kind") == "activity"]
    products = [row for row in source.get("sources", []) if row.get("kind") == "product"]
    category_lines = [
        f'- {row["label"]}：官网列 {row.get("reported_count", "未知")} 条，'
        f'实际取得 {row.get("row_count", "未知")} 条，去重 {row.get("unique_id_count", "未知")} 篇。'
        for row in activities
    ]
    lines = [
        "# Petzl 攀岩教程目录", "",
        f'目录快照日期：{meta.get("date", "未记录")}。个人查阅索引，非 Petzl 官方产品。',
        f'本次打包时间：{datetime.now(TZ).isoformat(timespec="seconds")}。正文链接实际核验时间：{verification_time}。', "",
        "## 开始使用", "",
        "双击 index.html，在 Chrome、Edge 等浏览器中打开。",
        "目录、筛选、收藏与已读功能可离线使用；打开 Petzl 原文需要联网。",
        f'默认展示全部 {len(articles)} 篇；“收录范围”可切换主目录 {core} 篇或装备扩展 {extension} 篇。',
        f'另列 {len(resources)} 项官方手册、FAQ 与装备资料入口；部分手册需自行填写官网表单，再通过邮件取得文件。', "",
        "- 可搜中文问题、英文原题及型号；空格分开的搜索词为同时包含。",
        "- 按活动、官方章节、装备、主题和阅读状态组合筛选；出现零结果时逐项放宽条件。",
        "- 收藏与已读保存到当前浏览器。导出收藏生成浏览器 HTML 书签，只备份收藏链接，不备份已读状态。",
        "- 切换浏览器、改变文件路径或清理浏览数据可能影响收藏与已读；建议定期导出收藏。", "",
        "## 文件用途", "",
        "- index.html：内嵌目录与样式，单独复制即可使用。",
        f'- Petzl攀岩教程目录.md：按 {len(topics)} 个主题排列，可用文档阅读器、Obsidian 或 Ctrl+F 查找。',
        "- Petzl攀岩教程目录.csv：UTF-8 BOM，可用 Excel 筛选并添加个人笔记。",
        "- catalog.json：结构化目录，包含唯一编号、题名、来源、标签与实际核验状态。",
        "- 覆盖与链接核验.json：栏目对账、重复 URL 别名及逐篇核验依据。",
        "- 更新目录.ps1：备份 → 重新抓取 → 逐篇核验 → 生成目录 → 同步使用说明与 ZIP。失败时恢复原目录。",
        "- crawl_petzl.py / verify_links.py / assemble_catalog.py / build_ui.py / package_catalog.py：仅依赖 Python 标准库的维护脚本。",
        "- title_translations.json：维护的题名映射，中文为 AI 辅助整理并校对；新题名无映射时显示待译并保留英文。",
        f'- resources.json：单独整理的 {len(resources)} 项官方补充资料；更新脚本不会提交表单或自动扩张这份精选列表。',
        "- selection_report.json：记录已收录、已排除与待范围复核的候选，避免新增器材页把无关领域混入。",
        "- verification_failure.json：仅在核验失败时生成，保存失败原因，不替换成功核验结果；不收入分享 ZIP。",
        "- _抓取校验资料：缓存、审查记录与更新备份，不影响离线使用，也不收入分享 ZIP。", "",
        "## 收录与核验依据", "",
        *category_lines,
        f'按文章编号去重后为 {core} 篇主目录；另检查 {len(products)} 个器材栏目，补入 {extension} 篇相关技术。',
        f'正文核验合格 {verified}/{len(articles)}：HTTP 200 且详情正文标题与英文原题一致。待译标题 {pending} 篇。',
        "核验日期来自每篇实际访问记录；生成或打包时间不代表重新访问过官网。精选手册与 FAQ 的核验状态另见目录数据。", "",
        meta.get("coverage_note", ""), "",
        meta.get("scope_note", "覆盖范围以已记录的活动栏目和器材种子为准。"), "",
        meta.get("language_note", "中文为检索译题，并非 Petzl 官方中文译本。"), "",
        "## 更新方式", "",
        "在此文件夹的 PowerShell 中运行：", "", "~~~powershell", ".\\更新目录.ps1", "~~~", "",
        "需要 Python 3.10+ 和网络，无需 pip 依赖。脚本优先使用本机 Codex 内置 Python，也支持正常安装的 Python；跳过 WindowsApps 占位程序。",
        "更新时忽略旧抓取和详情缓存。分类计数不完整、任一详情访问失败或标题不匹配时停止更新并恢复旧输出；失败详情写入 verification_failure.json。",
        "直接运行 verify_links.py 默认只复用 URL、标题、成功状态一致且未超过 7 天的结果，并保留原核验时间；加 --refresh 强制逐篇访问。",
        "更新成功会生成当天日期的 ZIP，并同步使用说明；旧日期 ZIP 保留，方便对照历史快照。", "",
        "## 方法与易错点", "",
        "目录按照活动场景 → 要解决的问题 → 对应器材 → 官方原文组织：活动约束场景，主题帮助定位问题，装备标签帮助查型号，唯一文章编号支持去重与追溯。",
        "维护流程为发现官方栏目 → 展开列表并对账 → 按编号去重 → 补查器材栏目 → 译题与分类 → 校验 HTTP 和详情标题 → 生成多种格式 → 核对打包内容。",
        "整理类似资料时，先检查分页，再区分栏目归属条数与唯一文章数。更新应验证失败路径，避免把暂时访问失败误当作内容已删除。",
        "尤其留意：收站、下放 lowering、自主下降 rappelling 分别表达不同动作；多段攀岩不自动等同于传统攀岩。已读只代表阅读记录，技术适用条件、限制与警示需核对官方原文和对应型号说明书。",
    ]
    path = base / "使用说明.md"
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def package(base: Path = BASE) -> Path:
    catalog = json.loads((base / "catalog.json").read_text(encoding="utf-8-sig"))
    for name in FILES:
        if name != "使用说明.md" and not (base / name).is_file():
            raise FileNotFoundError(f"Required distribution file is missing: {name}")
    write_readme(base, catalog)
    date = datetime.now(TZ).date().isoformat()
    output = base / f"Petzl攀岩教程目录_{date}.zip"
    temporary = output.with_name(output.name + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in FILES:
                archive.write(base / name, arcname="Petzl教程目录/" + name)
        with zipfile.ZipFile(temporary) as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise ValueError(f"Archive CRC check failed: {corrupt}")
            if len(archive.namelist()) != len(FILES):
                raise ValueError("Archive file count does not match the distribution allowlist")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Packaged {output}: {len(FILES)} files; {len(catalog['articles'])} articles; {len(catalog.get('resources', []))} resources")
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    args = parser.parse_args(argv)
    try:
        package(args.base.resolve())
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"Packaging failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

