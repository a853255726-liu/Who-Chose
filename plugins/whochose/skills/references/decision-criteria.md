# Shared WhoChose criteria

## Review the implemented function

- Start with the user's intended task and explain the actual delivered behavior: in what situation, what the user does, what happens, and any material limitation. Organize functional blocks by user tasks such as “重复录入提醒” or “删除与恢复”.
- Write decision titles and consequences in user-facing terms. For example, “疑似重复时默认取消，明确选择后仍可保存” describes a behavior the user can review. Function names, flags, helper methods, validation layers, and class boundaries belong in implementation evidence.
- A code design deserves a separate DECISION only when it makes a material difference to user operations, results, data/recovery, permissions, cost, or a consequential constraint. Explain that effect and the meaningful alternative. Ordinary implementation mechanisms that support the same behavior are ORDINARY_CHANGE or evidence for the functional decision; do not invent a separate product choice for each mechanism.
- Group the code supporting one functional behavior across files and layers. Preserve separate records when behavior, source, consequence, or risk materially differs; functional grouping must not erase provenance or hide important choices.
- In the final feedback, lead with what the user can now do and how it behaves. Then state important deviations or unrequested behavior, the specific behavior checked, and any concrete remaining gap affecting use. Keep test counts, coverage bookkeeping, function signatures, and code design out of the lead. Do not add a mandatory review round or claim that recorded coverage proves the function meets the user's goal.
- Keep code locations, versions, source attribution, reasons, and evidence limits available as supporting detail. Simplifying the feedback must not invent user acceptance, change the source class, or upgrade code reading into runtime verification. A guidance-only change should be reported as a change to review instructions, not proof that future reviews already follow them.
- Keep technical code locations out of normal HTML/Markdown review presentation. Preserve the actual local associations for on-demand lookup by task ID and functional name. Routine supersession notices stay out of card text; internal revision history remains intact for all source classes.

## Evidence and recording boundaries

- Track only actual additions/changes in this task. A requirement that was never implemented belongs in user decisions, not the implementation result.
- DECISION changes scope, core user flow, data/recovery/sharing, privacy/permissions, real cost or a consequential technical constraint. State a meaningful alternative difference. Unrecoverable deletion and unsolicited monthly statistics are decisions.
- ORDINARY_CHANGE includes corner radius, spacing, variable renames and behavior-preserving refactors. Group these under the functional block's collapsed “其他调整”; do not invent motives or major decisions for them.
- USER_SPECIFIED requires a matching observed explicit requirement/confirmation or a verified citation to applicable project documentation. Project requirements retain authority but use PROJECT_DOCUMENT provenance, not current-chat personal confirmation. An AI proposal accepted by the user retains proposal_origin=AI. Delegation does not approve the selected implementation.
- AI_SUPPLEMENTED requires actual development evidence of an AI choice. Not finding a user message is insufficient. UNKNOWN is a valid, visible gray category.
- A contemporaneous reason is a reason actually recorded during development, with its captured time. Missing reasons say “开发时未记录理由”; retrospective analysis is labeled as such.
- Record a short reason when making an important AI tradeoff, including the relevant constraint and meaningful cost where applicable. Recording a selection's AI origin and recording its reason are separate obligations. Missing-reason warnings are quality reminders after saving, not permission checks; preserve truthful MISSING/RETROSPECTIVE states and do not manufacture reasons for old records.
- Code-inferred consequences say “根据实现推断”. RUNTIME_VERIFIED requires an actual recorded run, not a file link or a model assertion.
- Do not merge choices with different sources, consequences or risk; keep all source and hunk references on legitimate merges. High-impact choices cannot be cut by a card limit.
- Coverage is a minimum diff check, not semantic completeness. Unavailable baseline, excluded files, stale code and unexplained hunks remain visible limitations.
- All source interpretations are made by the agent. Literal path, version and quote validation does not establish intent or effectiveness.
