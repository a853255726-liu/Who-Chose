"""One stdio MCP server, seven explicit business entry points."""
from functools import wraps
import os
import sqlite3
from .contracts import TOOLS, ContractError
from .service import Service
from .storage_errors import storage_error_result

DESCRIPTIONS = {
    "get_task_context": "Start before editing with workspace_root, bounded scope and idempotency_key; resume by task_id; complete checks and freezes coverage and writes offline HTML. Bind the Hook session_id when available.",
    "get_user_decisions": "Read effective explicit user decisions for this task. Use scope=relevant_history only when relevant prior workspace decisions are needed. Literal evidence does not prove intent.",
    "save_user_decisions": "Batch chat decisions with Hook message refs, or PROJECT_REQUIREMENT entries with project_refs (path, file_sha256, quote) and empty user_message_refs. Project requirements remain USER_SPECIFIED, labeled as document citations, not current personal confirmation. Preserve proposer; delegation does not confirm specifics.",
    "save_implementation_choices": "Batch actual DECISION or ORDINARY_CHANGE records linked to current hunk_refs. Record a brief rationale when making an important AI choice; inspect returned AI_RATIONALE_MISSING warnings without inventing past reasons. Require meaningful alternatives and supported sources; no invented user confirmations.",
    "get_task_changes": "Read bounded start-to-current task hunks and explicit exclusions. refresh=false may return a labeled cached scan; completed tasks remain frozen.",
    "check_change_coverage": "Refresh task changes and count decision-linked, ordinary, excluded and unreviewed hunks; retains baseline/source limitations. Does not prove semantic completeness.",
    "get_review_report": "Read current-task functional blocks, three-source decisions and grouped ordinary adjustments. Code refs and revision links remain queryable although HTML/Markdown hide code locations and routine revision notices. For an on-demand explanation use task_id and function name, then get_task_changes for the actual bounded diff; no whole chat or raw code embedded."
}


def create_server(data_root=None):
    from mcp.server.fastmcp import FastMCP
    server = FastMCP("whochose")
    service = Service(data_root)
    for name in TOOLS:
        method = getattr(service, name)
        def register(method, name):
            @wraps(method)
            def call(*args, **kwargs):
                try:
                    return method(*args, **kwargs)
                except ContractError as error:
                    return {"ok": False, "error": {"code": error.code, "message": str(error)}}
                except (OSError, UnicodeError, ValueError) as error:
                    return {"ok": False, "error": {"code": "INPUT_OR_IO_ERROR", "message": str(error)}}
                except sqlite3.Error as error:
                    return storage_error_result(error)
            server.tool(name=name, description=DESCRIPTIONS[name])(call)
        register(method, name)
    return server


def main():
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
