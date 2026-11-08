"""Offline HTML and Markdown from the same review selection."""
import json
from pathlib import Path
import re
import uuid
from .contracts import require, public_text
from .review import report

MARKER = "<!-- WhoChose generated report -->"


def safe_json(value):
    return json.dumps(value, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def html(report_data):
    root = Path(__file__).parent / "templates"
    template = (root / "review.html").read_text(encoding="utf-8")
    script = (root / "review.js").read_text(encoding="utf-8")
    return template.replace("__WHOCHOSE_SCRIPT__", script).replace("__WHOCHOSE_REPORT_JSON__", safe_json(report_data))


def md_text(value):
    value = public_text(value).replace("\r", " ").replace("\n", " ")
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_[\]{}()#+.!|])", r"\\\1", value)


def markdown(data):
    lines = [MARKER, "# " + md_text(data["title"]), "", "本次开发新增或改变的重要决定 · 只读", "",
        "任务：" + md_text(data["task_id"]), "生成时间：" + md_text(data["generated_at"]), "检查范围：" + md_text(", ".join(data["scope"])), ""]
    if data["gap_summary"]:
        lines.extend([md_text(data["gap_summary"]), ""])
    if data["excluded_path_count"]:
        lines.extend([f"已按规则排除 {data['excluded_path_count']} 个私密或生成路径。", ""])
    for block in data["blocks"]:
        lines.extend(["## " + md_text(block["name"]), ""])
        for item in block["decisions"]:
            lines.extend(["### " + md_text(item["title"]), "", md_text(item["label"]), "", md_text(item["reason"]), "",
                md_text(item["impact"]), "", md_text(item["detail_label"]) + "：" + md_text(item["detail"]), ""])
            for code in item.get("code_refs", []):
                lines.extend(["关联代码：" + md_text(code["location"]) + "（" + md_text(code["note"]) + "）", ""])
        if block["ordinary_changes"]:
            lines.extend(["<details><summary>其他调整</summary>", ""])
            for group in block["ordinary_changes"]:
                lines.append("- " + md_text(group["category"]) + "：" + md_text("；".join(group["summaries"])))
                for code in group["code_refs"]:
                    lines.append("  关联代码：" + md_text(code["location"]) + "（" + md_text(code["note"]) + "）")
            lines.extend(["", "</details>", ""])
    if not data["blocks"]:
        lines.extend(["本次检查范围内没有已记录且仍适用的实现选择。", ""])
    lines.extend([md_text(data["limitation"]), ""])
    return "\n".join(lines)


def write_report(store, task_id, format="html", output=None):
    require(format in {"html", "md"}, "INVALID_FORMAT", "Use html or md")
    with store.connect() as db:
        task = store.task(db, task_id)
    path = Path(output) if output else Path(task["workspace_root"]) / ("whochose-review." + format)
    require(path.suffix.lower() == "." + format, "INVALID_OUTPUT_PATH", "Output extension must match format")
    require(all(not p.is_symlink() and not (hasattr(p, "is_junction") and p.is_junction()) for p in [path, *path.parents]),
            "LINKED_PATH", "Output must not traverse symbolic links")
    if path.exists():
        require(path.read_text(encoding="utf-8").startswith(MARKER), "OUTPUT_EXISTS", "Will not overwrite an unrelated existing file")
    data = report(store, task_id, True)
    content = html(data) if format == "html" else markdown(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    return {"task_id": task_id, "format": format, "path": str(path.resolve()), "gap_summary": data["gap_summary"], "read_only": True}
