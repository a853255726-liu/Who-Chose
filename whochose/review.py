"""One shared selection/aggregation for HTML, Markdown and MCP."""
import json
from pathlib import Path
from .contracts import public_text, now
from . import changes

LABELS = {"USER_SPECIFIED": "用户指定", "AI_SUPPLEMENTED": "AI 自主选择", "UNKNOWN": "来源未确定"}


def code_status(root, code):
    location = code["path"] + (":" + str(code["start_line"]) if code["start_line"] else "")
    if code.get("deleted"):
        return {**code, "location": location, "current": not (Path(root) / code["path"]).exists(),
                "can_copy": False, "note": "文件已删除；这是本任务当时的版本位置"}
    try:
        raw, _ = changes.read_code(root, code["path"])
        current = changes.digest(raw) == code["file_sha256"]
    except (OSError, ValueError, UnicodeError):
        current = False
    return {**code, "location": location, "current": current, "can_copy": current,
            "note": "复制代码位置" if current else "位置可能已变化；请按记录版本复核"}


def source_description(data):
    source = data["source_class"]
    if source == "USER_SPECIFIED":
        if data.get("user_confirmation") == "PROJECT_DOCUMENT":
            snippets = []
            for requirement in data["source_evidence_refs"]:
                for ref in requirement.get("source_evidence_refs", []):
                    snippets.append(f'项目说明 {ref["path"]}:{ref["start_line"]} [SHA256 {ref["file_sha256"]}]：\n{ref["quote"]}')
            return "项目要求", "依据项目说明中的要求实现。", "引用的项目说明", "\n".join(snippets)
        confirmed_ai = data["proposal_origin"] == "AI"
        snippets = []
        for user in data["source_evidence_refs"]:
            if confirmed_ai and user.get("proposal_summary"):
                snippets.append("最初由 AI 提议：" + user["proposal_summary"])
            for ref in user.get("source_evidence_refs", []):
                snippets.append("用户原话：“" + ref["quote"][:500] + "”")
        return ("AI 提议 · 用户确认" if confirmed_ai else "用户指定",
                "AI 提出此方案后，你明确同意。" if confirmed_ai else "依据你明确提出的要求实现。",
                "决定如何确认的" if confirmed_ai else "你当时的要求", "\n".join(snippets))
    if source == "AI_SUPPLEMENTED":
        origin = data["rationale_origin"]
        reason = data["rationale"] if origin == "CONTEMPORANEOUS" else "开发时未记录理由。" if origin == "MISSING" else "开发时理由未记录；下面是事后分析。"
        detail = ("开发阶段记录的理由：" + data["rationale"]) if origin == "CONTEMPORANEOUS" else "开发时未记录理由。"
        if origin == "RETROSPECTIVE":
            detail += "事后分析（不代表当时动机）：" + data["rationale"]
        return LABELS[source], reason, "为什么这样选择", detail
    return LABELS[source], "已关联本次实现，但缺少足够来源依据。", "为什么来源未确定", "缺少可核实的用户要求或开发阶段选择记录，尚不能确定由谁提出；不据此猜测提出者。"


def redact_tree(value):
    if isinstance(value, dict):
        return {k: redact_tree(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_tree(v) for v in value]
    return public_text(value) if isinstance(value, str) else value


def report(store, task_id, include_details=True):
    checked = changes.coverage(store, task_id)
    with store.connect() as db:
        task = store.task(db, task_id)
        closed = task["status"] != "OPEN"
        rows = db.execute("SELECT r.*,d.behavior_key FROM decision_revisions r JOIN decisions d ON d.id=r.decision_id WHERE r.task_id=? AND r.revision=" +
            ("(SELECT max(x.revision) FROM decision_revisions x WHERE x.decision_id=r.decision_id AND x.task_id=r.task_id)" if closed else "d.revision"), (task_id,)).fetchall()
        blocks = {r["id"]: {"id": r["id"], "key": r["block_key"], "name": r["name"], "decisions": [], "ordinary_changes": []}
                  for r in db.execute("SELECT * FROM functional_blocks WHERE task_id=? ORDER BY rowid", (task_id,))}
        stale = []
        def links(record_id, revision):
            code = [code_status(task["workspace_root"], json.loads(r["data"])) for r in db.execute("SELECT data FROM code_links WHERE record_id=? AND revision=?", (record_id, revision))]
            active = db.execute("SELECT 1 FROM hunk_links l JOIN change_hunks h ON h.id=l.hunk_id WHERE l.record_id=? AND l.revision=? AND h.active=1 AND h.task_id=? LIMIT 1", (record_id, revision, task_id)).fetchone()
            return code, bool(active and all(c["current"] for c in code))
        for row in rows:
            codes, current = links(row["decision_id"], row["revision"])
            if not current and not closed:
                stale.append({"record_id": row["decision_id"], "reason": "code_or_hunk_changed"})
                continue
            data = json.loads(row["data"])
            label, reason, detail_label, detail = source_description(data)
            impact = data["user_visible_consequence"]
            if data["consequence_basis"] == "CODE_INFERRED":
                impact = "根据实现推断：" + impact
            elif data["consequence_basis"] == "UNVERIFIED":
                impact = "尚未验证：" + impact
            else:
                impact = "本任务运行记录支持：" + impact
            item = {"id": row["decision_id"], "revision": row["revision"], "behavior_key": data["behavior_key"],
                "title": data["title"], "source_class": data["source_class"], "proposal_origin": data["proposal_origin"],
                "user_confirmation": data["user_confirmation"], "label": label, "reason": reason,
                "impact_level": data["impact_level"], "impact": impact, "detail_label": detail_label, "detail": detail,
                "meaningful_difference": data["meaningful_difference"], "consequence_basis": data["consequence_basis"],
                "rationale_origin": data["rationale_origin"], "rationale_captured_at": data["rationale_captured_at"],
                "code_refs": codes, "supersedes": data["supersedes"], "code_current": current}
            if data["supersedes"]:
                item["detail"] += "\n本次已替代此决定的上一版本；旧版本保留在本地记录中。"
            if any(c["record_id"] == row["decision_id"] for c in checked.get("source_conflicts", [])):
                project = data.get("user_confirmation") == "PROJECT_DOCUMENT"
                item["reason"] = ("引用的项目说明或要求记录已有变化，适用性需复核。" if project else
                                  "依据当时的用户要求实现；相关要求后来已有修订，适用性需复核。")
                item["detail"] += ("\n保留当时引用的项目说明和版本。" if project else
                                   "\n此处保留当时的真实确认；更新后的要求是否仍适用，需要复核。")
            if not include_details:
                for key in ("detail", "code_refs", "meaningful_difference", "rationale_captured_at"):
                    item.pop(key)
            blocks[row["block_id"]]["decisions"].append(item)
        grouped = {}
        for row in db.execute("SELECT * FROM ordinary_changes WHERE task_id=? ORDER BY created", (task_id,)):
            codes, current = links(row["id"], 1)
            if not current and not closed:
                stale.append({"record_id": row["id"], "reason": "ordinary_code_changed"})
                continue
            data = json.loads(row["data"])
            key = row["block_id"], data["category"]
            group = grouped.setdefault(key, {"category": data["category"], "summaries": [], "code_refs": [], "exclusions": []})
            if data["summary"] not in group["summaries"]:
                group["summaries"].append(data["summary"])
            for code in codes:
                if code not in group["code_refs"]:
                    group["code_refs"].append(code)
            if data.get("exclusion_reason"):
                group["exclusions"].append(data["exclusion_reason"])
        for (block_id, category), value in grouped.items():
            blocks[block_id]["ordinary_changes"].append(value)
    visible, counts = [], {s: 0 for s in LABELS}
    for block in blocks.values():
        block["decisions"].sort(key=lambda d: d["impact_level"] != "HIGH")
        for item in block["decisions"]:
            counts[item["source_class"]] += 1
        if block["decisions"] or block["ordinary_changes"]:
            visible.append(block)
    gaps = []
    if checked["counts"]["UNREVIEWED"]:
        gaps.append(f"还有 {checked['counts']['UNREVIEWED']} 处变化未说明")
    if checked["uninspected"] or checked["baseline_state"] == "PARTIAL_BASELINE":
        gaps.append("部分起始基线或文件无法检查")
    if stale:
        gaps.append(f"{len(stale)} 条开发记录的代码已变化，需补记")
    if checked.get("source_conflicts"):
        gaps.append("相关用户要求已有修订，当前实现的适用性需复核")
    return redact_tree({"schema_version": "whochose-review.v1", "task_id": task_id, "task_revision": task["task_revision"],
        "title": task["description"], "status": task["status"], "generated_at": now(), "completed_at": task["completed"],
        "scope": json.loads(task["scope"]), "baseline_state": checked["baseline_state"], "blocks": visible, "counts": counts,
        "coverage_counts": checked["counts"], "gap_summary": "；".join(gaps), "stale_records": stale if include_details else [],
        "unchecked_file_count": len(checked["uninspected"]), "excluded_path_count": len(checked.get("exclusions", [])),
        "automatic_hook_coverage": "not_guaranteed", "semantic_coverage_verified": False, "frozen_at_completion": closed,
        "limitation": "仅检查所选范围；自动观察可能不完整，改动覆盖不代表所有重要含义均已发现。"})
