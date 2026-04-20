# TASK-000: Project Bootstrap — Discovery Dialogue and First Task

## 1. Metadata
- Task ID: TASK-000
- Created: (fill on first run)
- Assigned to: PM
- Mode: strict
- Status: TODO

## 2. Context
This is the very first task of every project in the C.E.H. ecosystem. PM executes it before any other work. It replaces hidden discovery logic with a visible, data-driven checklist, so that no project starts without a clear goal, constraints, and a first actionable task on the board.

If you (PM) are reading this file and its status is TODO or IN_PROGRESS — you MUST complete it before creating any other task. Do NOT skip.

## 3. Objective
Run the discovery dialogue with the user, fill `memory/PROJECT_STATE.md`, create `TASK-001.md` for the first real unit of work, and mark this bootstrap task DONE with full evidence.

## 4. Scope
- In scope:
  - Discovery dialogue with the user (3 core questions minimum)
  - Initializing `memory/PROJECT_STATE.md` with metadata, context, constraints, current phase
  - Updating `memory/TASK_BOARD.md` with TASK-000 moving to DONE and TASK-001 appearing in TODO
  - Creating `memory/TASKS/TASK-001.md` with full 13-section structure and an explicit DoD
- Out of scope:
  - Executing TASK-001 itself (that is a separate delegation cycle)
  - Modifying agent prompts or `SYSTEM_REGISTRY.md`

## 5. Constraints
- PM does NOT execute code, research, ideation, debugging, or writing — only orchestrates and files.
- Discovery dialogue is a legitimate PM activity (it is NOT execution).
- All files written in English by default; chat mirrors the user's language.

## 6. Options Considered
N/A — bootstrap flow is fixed.

## 7. Decision and Rationale
Bootstrap as a data-driven task (rather than hidden logic in the PM prompt) makes the first-run behavior transparent, editable by the user, and auditable.

## 8. Plan / Execution Steps

**Step 1 — Greeting and discovery dialogue (PM ↔ User):**
Ask the user at minimum:
1. What is the end goal of this project?
2. Are there constraints (time, technology, dependencies, budget)?
3. What is already done, or what must not be touched?

Adapt follow-up questions as needed. Do NOT move forward until you have clear answers or an explicit `INSUFFICIENT_DATA` acknowledgement from the user.

**Step 2 — Initialize `memory/PROJECT_STATE.md`:**
Fill: `project_name`, `date`, `phase: discovery` (or `planning` if already scoped), `Current Context`, `Active Decisions`, `Constraints`, `Current Phase Summary`.

**Step 3 — Create `memory/TASKS/TASK-001.md`:**
Use the 13-section structure. Write an explicit DoD with 3–7 verifiable criteria. Classify mode (`light` or `strict`) per `memory/EXECUTION_MODE_POLICY.md`. Identify the correct worker (see role reminder below).

**Step 4 — Update `memory/TASK_BOARD.md`:**
- Move TASK-000 from TODO/IN_PROGRESS to DONE (with evidence line).
- Add TASK-001 to TODO with the assigned worker.

**Step 5 — Report back to the user:**
Use the PM response contract (ROLE: PM_AGENT + 5 numbered lines). Announce TASK-001 is ready and state which worker should be invoked next.

## 9. Risks
- PM might skip the dialogue and invent a project scope — HARD FAIL, return INSUFFICIENT_DATA.
- PM might create TASK-001 without an explicit DoD — HARD FAIL, do not delegate.
- PM might execute the first unit of work itself — violates the no-execution rule.

## 10. Dependencies
- `memory/PROJECT_STATE.md` must exist (template provided).
- `memory/TASK_BOARD.md` must exist (template provided).
- `memory/EXECUTION_MODE_POLICY.md` and `memory/EVIDENCE_STANDARD.md` must be readable.

## 11. Success Criteria (DoD)
- [ ] Discovery dialogue completed — user answered the 3 core questions (or explicitly marked a question as unknown).
- [ ] `memory/PROJECT_STATE.md` filled: metadata, context, constraints, current phase summary.
- [ ] `memory/TASKS/TASK-001.md` created with all 13 sections and an explicit DoD (3–7 items).
- [ ] `memory/TASK_BOARD.md` updated: TASK-000 in DONE with evidence, TASK-001 in TODO with assigned worker.
- [ ] Evidence Bundle written into section 13 of this file (scope, execution, outcome, residual risk).

## 12. Open Questions
(none — this task is fully specified)

## 13. Change Log
<!-- DATE | DoD Item X | Description | Evidence -->

---

## Role Reminder — Who Does What

Before creating TASK-001, remind yourself of the workforce. Pick the correct agent for the first unit of work:

| Agent | When to delegate |
|---|---|
| **Code** | Implementation, coding, refactoring, running tests, verifying code-level changes. Also handles bugs (reproduce → trace → diagnose → fix → verify) and runs a mandatory self-audit before handing off to Reviewer. |
| **Scaut** | Web/source research, fact-checking, collecting citations, comparing options based on evidence. |
| **Ask** | Ideation, generating and scoring options (Impact·Confidence / Effort+Risk), recommending a decision. |
| **Reviewer** | Pre-merge audit of Code's diff — 10-point grep-verified checklist (secrets, CORS, bare except, sync-in-async, dead code, logged secrets, injection, validation, unbounded collections, test quality). Produces REVIEW_REPORT with P0/P1/P2 findings. Never modifies code. |
| **Writer** | Documentation, READMEs, landing pages, sales copy, changelogs, reports. |
| **Healer** | Creating or auditing agents in the ecosystem itself (advanced — rarely needed for product work). |

If the first task needs more than one role, split it into multiple tasks. One task = one worker.

---

## Before You Delegate — The PM Mantra

> I plan. I file. I verify.  
> I do not execute.  
> No DONE without evidence.  
> Workers touch only their allowed sections.  
> Status lives in `memory/TASK_BOARD.md`.

Every project you bootstrap is one more team shipping with discipline. Make the first task count — a clean TASK-001 sets the tone for everything that follows. Be precise, be kind to the workers, and keep the memory honest.

Now go. Greet the user, run the dialogue, and put the first real task on the board.
