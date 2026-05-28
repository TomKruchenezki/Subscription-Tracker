---
name: phase-plan
description: Planning skill for architecture phases. Reads CURRENT_STATE.md and NEXT_STEPS.md, diagnoses root cause, lists files likely to change, defines smallest safe scope, lists required tests. Stops before implementation.
---

# Phase Planning Skill

You are acting as a technical architect. Your goal is to produce a complete implementation
plan — diagnosis, scope, test list — WITHOUT writing any code or editing any files.

## Step 1 — Read Current State

1. Read `docs/CURRENT_STATE.md` (phase, test count, known problems, verification commands)
2. Read `docs/NEXT_STEPS.md` (planned phases and prerequisites)
3. Identify which phase is being planned and confirm prerequisites are met

## Step 2 — Diagnose Root Cause

For the problem or feature being addressed:
- State the root cause in ≤ 3 sentences
- Cite the exact file(s) and line(s) where the bug or gap lives
- Describe the observable symptom (what the user sees) vs. the underlying cause

## Step 3 — List Files Likely to Change

Enumerate every file that will need to change. For each:
- File path (relative to project root)
- What changes: new function, modified query, new column, new pattern, etc.
- Whether it needs a new migration (and if so, what the next migration number is)

## Step 4 — Define Smallest Safe Scope

Answer: "What is the minimum set of changes that fixes the root cause and is fully tested?"
- Exclude anything that could be deferred to a later phase
- Flag any dependencies (e.g., "requires migration 006 to exist first")
- Note any schema changes that need product-architect + privacy-reviewer approval

## Step 5 — List Required Tests

For each logical change, list:
- Which test file it belongs in (`tests/unit/`, `tests/privacy/`, etc.)
- The test name and what it asserts
- Whether it is a new test or an update to an existing one
- Whether a privacy test in `tests/privacy/` is needed

## Step 6 — Stop

Do not implement anything. Output the plan summary and wait for approval.
State explicitly: "Plan complete. Awaiting ExitPlanMode approval before any edits."
