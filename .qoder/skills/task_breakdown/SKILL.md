---
name: task_breakdown
description: Decompose a multi-step goal into an ordered, owner-assigned list of subtasks. Used by the Planner Agent.
---

# task_breakdown

## Purpose

Take a user goal and produce a plan: an ordered list of subtasks, each with an owner agent, dependencies, and a clear definition of done.

## Inputs

- `goal` (string, required) — what the user wants to achieve.
- `context` (string, optional) — any constraints, prior state, or relevant history.
- `horizon` (enum, optional) — `quick` (≤ 3 steps), `normal` (≤ 10), `phased` (multi-session). Default `normal`.

## Outputs

- `plan`: list of subtasks, each with:
  - `step` (int)
  - `name` (string)
  - `owner` (agent slug)
  - `goal` (what success looks like)
  - `depends_on` (list of step numbers)
  - `decision_point` (bool)
- `decision_points` (list of step numbers).
- `risks` (list of strings).
- `estimated_total` (human-readable range).

## Steps

1. Read the goal; identify ambiguities and surface them as clarification questions *before* planning.
2. Identify decision points — moments where the user must choose before the plan proceeds.
3. Identify dependencies between subtasks.
4. Identify which subtasks can run in parallel.
5. Assign each subtask to the right specialist agent.
6. Write the plan in the shape above; cap step count at the `horizon` limit.

## Failure modes

- Goal is too vague → ask a clarifying question; do not plan around a guess.
- Goal requires a capability the runtime doesn't have → surface this and suggest the user do that step themselves.
- Plan is over the `horizon` cap → suggest splitting into phases; plan only the first phase.
- Dependencies form a cycle → restructure; surface the constraint to the user.
