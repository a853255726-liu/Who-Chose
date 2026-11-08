---
name: review-plan
description: Review an existing plan for a WhoChose task and clarify only important unresolved product choices before implementation.
---

Read [shared criteria](../references/decision-criteria.md) and the actual plan. Query `get_task_context` and `get_user_decisions`; relevant_history is an explicit opt-in scope when an earlier decision matters.

Treat user-confirmed design as a boundary. Find only unresolved choices that affect scope, user operations, data, privacy, permissions, real cost or important constraints. Ask the prerequisite question first, using the host's normal question UI when available. Resolve low-impact engineering details yourself; do not turn this into a mandatory approval flow.

An AI-authored plan is a versioned project source, not a user confirmation record. Do not bulk-save all its proposals as user decisions. After a clear user response, use the capture-decisions record contract with the original Hook message reference, retaining AI as the initial proposer when applicable. A broad delegation is not acceptance of every concrete solution.

If the plan conflicts with confirmed design or the host cannot implement an interface, disclose the specific conflict and compatibility option. Do not silently change the product. Do not use old pilot cards, approval/rollback UI or a second LLM reviewer.
