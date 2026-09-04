---
name: schedule_job
description: Create, modify, list, or cancel a scheduled job in the runtime's scheduler. Used by the Automation Agent.
---

# schedule_job

## Purpose

Manage scheduled jobs (one-shots at a future time, or recurring on a cron).

## Inputs

- `op` (enum, required) — `create`, `update`, `list`, `cancel`, `pause`, `resume`.
- For `create` / `update`:
  - `name` (string, required)
  - `schedule` (string, required) — cron expression or ISO-8601 timestamp for one-shots.
  - `timezone` (string, required) — IANA name, e.g. `America/Los_Angeles`.
  - `action` (object, required) — `{agent_slug, skill_slug, inputs}`.
  - `confirm_on_fire` (bool, optional, default false) — if the action includes a sensitive skill, the runtime will re-confirm each time the job fires.
- For `cancel` / `pause` / `resume`: `job_id` (string, required).
- For `list`: optional `tag` filter.

## Outputs

- For `create` / `update`: `job_id` and the persisted job definition.
- For `list`: list of matching jobs.
- For `cancel` / `pause` / `resume`: `{ok: bool, job_id}`.

## Steps

1. Validate the `op`.
2. For `create`:
   - Validate the cron expression or timestamp.
   - Validate the time-zone.
   - Validate the action references a real agent and skill.
   - If the action includes a sensitive skill, require `confirm_on_fire: true`.
   - Persist the job.
3. For `update` / `cancel` / `pause` / `resume`: load by ID, apply the change.
4. Return.

## Failure modes

- Invalid cron → return a clear error with the parse location.
- Unknown time-zone → reject; do not guess.
- Action references a non-existent agent or skill → reject.
- `confirm_on_fire` is false but the action includes a sensitive skill → reject; the runtime will not allow this.
- Job would fire more often than the runtime's minimum interval (default: once per minute) → reject.
