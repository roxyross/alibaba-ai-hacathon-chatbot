---
name: calendar_read
description: Read events from the user's calendar. Read-only — never write, modify, or delete. Used by user-facing agents when the user asks about their schedule.
---

# calendar_read

## Purpose

Fetch the user's calendar events in a date range.

## Inputs

- `start` (ISO-8601 timestamp, required) — start of the range.
- `end` (ISO-8601 timestamp, required) — end of the range.
- `calendar_ids` (list of string, optional) — restrict to specific calendars. Default: all calendars the user has connected.
- `max_results` (int, optional, default 50) — safety cap.

## Outputs

- `events`: list of `{id, title, start, end, all_day, location, attendees, notes, calendar_id}`.
- `total`: count of events returned.

## Steps

1. Validate `start` < `end`, both in the past or future, and the range is not larger than 1 year.
2. Fetch from the user's connected calendar provider (Google, Outlook, iCloud, etc.).
3. Apply `calendar_ids` filter if provided.
4. Sort by `start` ascending.
5. Cap at `max_results` and warn if truncated.

## Failure modes

- No connected calendar → surface to the user; ask them to connect one.
- Provider auth expired → surface a re-auth prompt; do not retry forever.
- Empty range → return empty list; not an error.
- Time-zone ambiguity → default to the user's profile time-zone; surface the assumption in the output.
