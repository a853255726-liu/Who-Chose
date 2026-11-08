# Shared WhoChose criteria

- Track only actual additions/changes in this task. A requirement that was never implemented belongs in user decisions, not the implementation result.
- DECISION changes scope, core user flow, data/recovery/sharing, privacy/permissions, real cost or a consequential technical constraint. State a meaningful alternative difference. Unrecoverable deletion and unsolicited monthly statistics are decisions.
- ORDINARY_CHANGE includes corner radius, spacing, variable renames and behavior-preserving refactors. Group these under the functional block's collapsed “其他调整”; do not invent motives or major decisions for them.
- USER_SPECIFIED requires a matching observed explicit requirement/confirmation or a verified citation to applicable project documentation. Project requirements retain authority but use PROJECT_DOCUMENT provenance, not current-chat personal confirmation. An AI proposal accepted by the user retains proposal_origin=AI. Delegation does not approve the selected implementation.
- AI_SUPPLEMENTED requires actual development evidence of an AI choice. Not finding a user message is insufficient. UNKNOWN is a valid, visible gray category.
- A contemporaneous reason is a reason actually recorded during development, with its captured time. Missing reasons say “开发时未记录理由”; retrospective analysis is labeled as such.
- Code-inferred consequences say “根据实现推断”. RUNTIME_VERIFIED requires an actual recorded run, not a file link or a model assertion.
- Do not merge choices with different sources, consequences or risk; keep all source and hunk references on legitimate merges. High-impact choices cannot be cut by a card limit.
- Coverage is a minimum diff check, not semantic completeness. Unavailable baseline, excluded files, stale code and unexplained hunks remain visible limitations.
- All source interpretations are made by the agent. Literal path, version and quote validation does not establish intent or effectiveness.
