---
name: memory_summarize_prune
description: Apply the Memory Curator's decisions — summarize clusters, soft-delete low-value entries, hard-delete expired soft-deletes. Internal skill, used only by the Memory Curator Agent; not exposed to user-routable agents.
internal: true
---

# memory_summarize_prune

## Purpose

Apply the Memory Curator Agent's batch decisions in a single transactional pass.

## Inputs

- `operations` (list of object, required) — the batch of operations to apply. Each is one of:
  - `{op: summarize, cluster_id, summary_content, source_entry_ids}`
  - `{op: soft_delete, entry_id, reason}`
  - `{op: hard_delete, entry_id}`
  - `{op: restore, entry_id}` (for soft-deleted entries within the grace window)

## Outputs

- `applied`: list of `{op, entry_id, ok}`.
- `errors`: list of `{op, entry_id, reason}`.
- `run_id`: a unique ID for this pass.

## Steps

1. Validate the operations against the pruning policy (no hard-delete within the soft-delete grace period; no modify of `importance: forever` entries).
2. Apply in a single transaction. On any error, roll back the whole batch.
3. Write a `run_id` to the memory store's audit log.
4. Return.

## Failure modes

- A `summarize` references an entry that was hard-deleted in a prior pass → fail the whole batch; the Memory Curator should re-cluster.
- A `hard_delete` targets an entry that hasn't been soft-deleted yet → reject; soft-delete first, then hard-delete in a later run.
- Storage layer error mid-batch → roll back; surface to the Memory Curator; do not half-apply.
- Audit log write fails → roll back; the operation is not applied without an audit trail.

## Notes

- This skill is `internal: true`. The Coordinator does not invoke it in response to user messages. It runs only from the Memory Curator Agent's scheduled pass.
- The pruning policy itself (thresholds, grace windows, `forever` exemptions) is configured in the runtime, not in this skill.
