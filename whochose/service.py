from .storage import Store
from . import task_scope, decisions
from .storage_errors import retry_busy


class Service:
    @retry_busy
    def __init__(self, data_root=None):
        self.store = Store(data_root)

    @retry_busy
    def get_task_context(self, workspace_root: str, action: str, task_id: str | None = None, scope: list[str] | None = None,
                         idempotency_key: str | None = None, description: str = "本次开发", session_id: str | None = None) -> dict:
        result = task_scope.context(self.store, workspace_root, action, task_id, scope, idempotency_key, description, session_id)
        if action == "complete":
            from .export import write_report
            result["report"] = write_report(self.store, result["task_id"])
        return result

    @retry_busy
    def get_user_decisions(self, task_id: str, scope: str | None = None) -> dict:
        return decisions.get_user(self.store, task_id, scope)

    @retry_busy
    def save_user_decisions(self, task_id: str, entries: list[dict], user_message_refs: list[dict], idempotency_key: str) -> dict:
        return decisions.save_user(self.store, task_id, entries, user_message_refs, idempotency_key)

    @retry_busy
    def save_implementation_choices(self, task_id: str, entries: list[dict], hunk_refs: list[str], idempotency_key: str) -> dict:
        from .implementation import save
        return save(self.store, task_id, entries, hunk_refs, idempotency_key)

    @retry_busy
    def get_task_changes(self, task_id: str, refresh: bool = True) -> dict:
        from .changes import refresh as refresh_changes
        return refresh_changes(self.store, task_id, refresh)

    @retry_busy
    def check_change_coverage(self, task_id: str) -> dict:
        from .changes import coverage
        return coverage(self.store, task_id)

    @retry_busy
    def get_review_report(self, task_id: str, include_details: bool = True) -> dict:
        from .review import report
        return report(self.store, task_id, include_details)
