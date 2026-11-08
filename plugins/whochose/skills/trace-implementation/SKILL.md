---
name: trace-implementation
description: During actual WhoChose development, record important implemented choices and grouped ordinary changes, then check task diff coverage before finishing.
---

Read [shared criteria](../references/decision-criteria.md). Start the task baseline before editing; if editing already began, declare a partial baseline rather than attributing prior changes to this task. Keep the same task_id across sessions.

Review from the user's task: identify the situation, user action, and actual result before classifying the supporting diff. Use functional names for `functional_block_name`; write `title`, `user_visible_consequence`, and `meaningful_difference` so the user can judge the delivered behavior without understanding the code. Describe only what this task actually implements and preserve its material limits.

For example, a duplicate-record feature can be titled “疑似重复时默认取消，输入‘仍要保存’后才新增”, with the matching rule and recovery behavior explained in its consequence. A helper, an `allow_duplicate` parameter, or where validation runs is supporting evidence or an ordinary adjustment unless it creates a distinct material user consequence. Several functions serving that one behavior do not each require a decision card. Keep materially different behavior rules and provenance separate within the functional block.

When delivering the review, describe implemented functions and important behavior differences first, followed by the relevant checks and concrete gaps affecting use. Put code locations and design rationale in supporting detail. Do not substitute a list of functions, internal safeguards, test counts, or recorded hunks for the user's functional result; do not add a review round solely to follow these instructions.

At suitable batches call `get_task_changes(task_id, refresh=true)`. Each hunk includes its stable hunk_id, path and before/after snapshot hashes. Classify actual changes by user-visible consequences, not files or a target number of cards.

Call `save_implementation_choices(task_id, entries, hunk_refs, idempotency_key)` in batches. Every entry has kind, functional_block_key, functional_block_name, and its own nonempty hunk_refs; the outer hunk_refs is their union. Keep all hunks for a legitimate functional grouping. Code refs are checked against these changes; if omitted, real positions are derived from them.

For DECISION supply behavior_key, a plain-language title, user_visible_consequence, meaningful_difference, impact_level=HIGH or NORMAL, source_class, rationale_origin and consequence_basis. USER_SPECIFIED also needs user_decision_refs with current record_id/revision for the same concrete behavior. Project requirements use PROJECT_REQUIREMENT records, retaining proposal_origin=UNKNOWN and user_confirmation=PROJECT_DOCUMENT; do not rewrite them as current chat confirmation. A delegation cannot be used to confirm the selected choice. AI_SUPPLEMENTED needs development_evidence entries `{kind: DEVELOPMENT_NOTE, text: ...}` recording the actual selection; lack of a user message is insufficient. Without that evidence use UNKNOWN and proposal_origin=UNKNOWN.

Use rationale_origin=CONTEMPORANEOUS only for a reason actually recorded while doing the task. Use MISSING with no rationale otherwise; retrospective analysis must remain RETROSPECTIVE. Timestamps are assigned by the server, not invented. Normally use consequence_basis=CODE_INFERRED; RUNTIME_VERIFIED requires a real CLI verifier receipt matching the code versions, never a self-written test claim.

For ORDINARY_CHANGE supply category and summary instead of a proposer/reason chain. Group radius/spacing and behavior-preserving refactors under the proper functional block. A reasonable exclusion is an ordinary record with an explicit exclusion_reason; do not hide high-impact behavior this way.

Read current records before a revision; supply record_id and expected_revision. Reuse idempotency keys only for identical payloads. Failed/stale hunk refs require refreshing the diff; do not fabricate paths or reused ids.

Before delivering the completed task run `check_change_coverage`. When waiting for a user answer, end the turn immediately; keep the task open and do not insert a coverage-check reply or call complete. Explain remaining hunks, retain unavailable scope and missing evidence honestly, then call `get_task_context(action=complete, task_id, workspace_root, idempotency_key)`. Stop is only a turn boundary: it never blocks or starts another audit turn. Explicit complete performs and freezes the delivery check, including gaps. Missing historical evidence stays visible and does not require repeated attempts. Coverage checks do not prove semantic completeness or authorize host operations.
