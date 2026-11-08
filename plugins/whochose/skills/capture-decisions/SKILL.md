---
name: capture-decisions
description: Record clear user requirements, explicit acceptance of a uniquely identifiable AI proposal, or scoped delegation during a WhoChose task. Preserve original messages and proposer identity.
---

Read [shared criteria](../references/decision-criteria.md). Capture actual user intent; a Hook receipt alone is not consent.

Before editing, call `get_task_context` with workspace_root, action=start, a new stable idempotency_key, description and bounded literal file/directory scope (not glob patterns; use ui instead of ui/**). Include the Hook-provided session_id to bind the task; resume an existing task by task_id rather than recapturing its baseline. Keep the returned task_id throughout this task.

Use Hook-provided message_id and message_digest plus an exact quote visible in the original user message. `save_user_decisions(task_id, entries, user_message_refs, idempotency_key)` batches entries with behavior_key, title, proposal_origin and intent:

- DIRECT_INSTRUCTION: original proposer USER.
- ACCEPTED_PROPOSAL: original proposer AI; include proposal_summary and accepted_option identifying the single agreed option.
- SCOPE_AUTHORIZATION: original proposer USER; scoped delegation does not confirm future individual implementation choices.

Each user_message_ref contains message_id, message_digest and an exact quote (at most 2,000 characters). The Hook keeps a bounded 4,000-character prefix; when a quote is unavailable, keep provenance unverified rather than inventing evidence. Read `get_user_decisions` before revising; supply record_id and expected_revision. Reuse a write key only with identical input.

Do not upgrade vague enthusiasm, forwarded AI plans, assistant summaries or automatic Hook continuation into explicit user confirmation. Classification is your interpretation, not a claim that Python verified meaning. Without a working message Hook do not manufacture a trusted reference. Missing source may remain UNKNOWN in implementation review; ask only if an unresolved product choice materially needs the user's decision.

Project documentation is an authoritative requirement source; no redundant user confirmation is needed. Cite it separately using intent=PROJECT_REQUIREMENT, proposal_origin=UNKNOWN, user_confirmation=PROJECT_DOCUMENT, project_refs=[{path, file_sha256, quote}], and user_message_refs=[]. Read the actual current document first and use its SHA256 and exact quote. Keep a document-only batch separate from chat-message entries. The review must say “项目要求 / 引用的项目说明”, with the file, quote and version; never call it “用户原话” or claim known authorship. Reading a document does not prove its instructions apply: interpret scope and conflicts honestly.

Recording a decision never authorizes host operations. Do not invoke BuildChoice cards or long-term memory workflows.
