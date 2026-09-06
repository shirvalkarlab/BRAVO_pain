# BRAVO weekly review and nightly evidence

Current user contract, September 5, 2026. The expanded completion checklist is
`completion-2026-09-05.md`; this workflow supplements `automatic-updates.md` and
`biweekly-slides.md` without authorizing speculative scientific changes.

## Schedule and recipient

- Nightly maintenance: 03:00–07:00 America/Los_Angeles, maximum four hours,
  GPT-6 Astra / High. A late start or earlier deadline shortens the budget.
- Monday weekly review: 09:00 America/Los_Angeles, a fresh standalone local task
  in the BRAVO_platform project, automation `bravo-weekly-review`.
- All automated Slack delivery goes only to Aditya's existing self-DM
  `D076Z8T5EUX` (user `U077G9W0TL4`). The four-person conversation is a read-only
  evidence source; never automatically send there or forward to its members.
- The weekly Slack message says it is time for review and links to the actual
  fresh task using `codex://threads/<task-id>`. This installed desktop app's
  bundled code contains that link form. Obtain the ID from `CODEX_THREAD_ID`
  or verified app task metadata; never invent it or use a public share link.
  The cron-created project task itself is the requested conversation.

## Monday agenda

1. Ask Aditya to manually review the past seven days in REDCap; show the actual
   Pacific date range. Do not perform or mark that human review complete for him.
2. Ask him to reconfirm newly detected/automatically added stimulation visits,
   showing each date and concise source evidence. Include uncertain candidates
   separately. If none were found, ask whether any visit was missed.
3. Recheck the prior week's pending integration questions against current code,
   source records, local documentation and Aditya's previous answers. Remove
   answered or obsolete items. For each remaining question provide a concrete
   recommendation, why, evidence links, and the portion of work kept on hold.

The review is read-only preparation and a self-DM; it does not start another
maintenance run, sync, analysis, deployment or scientific-data edit.

## Nightly visit detection

Drive root: RCS08 Stage 2 folder
`1ytHC376Qn_p0sL2C-oH4u0Yit4DyqkKN`, including Clinic Testing
`10uYVdcj_NGtepeiDF2qHn2bb-fwHqQcv` and relevant descendants. Discover current
files in that folder instead of assuming a frozen file list. Current reference
surfaces include Stage 2 Master Sheet `1WQCmxfAKzcM88Hq8l7cS2Z6Upmvx9q-9ZGCkQwnXs8I`,
HomeStimTimeline `1-b8K3_eDTooPgmFGCfw4i-Ow9WYu1L0T6EsOLrVWT9k`, and Stim Test Log
`1xvPsUlwhTpSNTcdoepsQyQIAs1qA9q4YNCdVefVq02Q`.

Slack evidence: `C0BJQJWSJBD`, requiring a completed in-clinic visit summary
authored by Aditya `U077G9W0TL4`. Both substantive Drive content and that Slack
summary must agree on the visit and represented date before automatic addition
to `secrets/rcs08_processing/rcs08_stim_testing_dates.csv`. Merely modified files,
planned visits, home changes, routine uploads or another author's message are
insufficient. Search enough overlapping history to catch delayed uploads and
summaries; use the last successful scan checkpoint and retain unresolved cases.

When both sources agree, preserve existing reviewed rows, schema and local
edits; back up the prior calendar, stage a minimal dated addition, validate it,
then publish locally. Refresh local visit-sheet copies from Drive only as
needed, with revision/hash comparison. Do not modify shared Drive originals.
Use supported cache invalidation and export paths after a calendar change.
Mark the visit as awaiting Monday reconfirmation. Missing or conflicting
evidence leaves the affected calendar unchanged and creates a review question.

## Durable records

Keep private machine-readable ledgers under ignored `output/weekly-reviews/`:

- `visits.json`: stable visit key/date, first/last check, Drive IDs/revisions/
  cell or slide references, Slack author/permalink, agreement status, local
  before/after hashes, whether added, Monday confirmation and corrections.
- `questions.json`: stable question ID, first seen/last rechecked, upstream
  commit/affected behavior, uncertainty, attempted evidence checks, recommendation,
  rationale, held scope, source links, status, user answer and resolution.
- One dated review/delivery record: task ID/link, agenda source window and ledger
  revision, Slack message ID/link, send completion. Inspect records and Slack
  history before retrying; do not duplicate a dated review message.

Fixel development is reviewed/integrated before Prasad, retaining independent
48-hour observed-head eligibility. Resolve questions independently when evidence
permits. Without explicit guidance, preserve validated behavior and hold the
uncertain portion, rather than making a broad speculative integration. Do not
discard unrelated validated work or revisit decisions already made by Aditya.

## Freshness reminders and slide delivery

Check represented REDCap, Percept JSON/PDF and Oura times during every nightly
review. Send an alert every night that any stream is more than 48 hours old or
unavailable, even if unchanged since yesterday. Deduplicate only retries within
the same Pacific nightly date. Stop stale-data reminders once all are fresh.
Show all source datetimes; use the later valid Percept session for its combined
age, disclose missing/partial sources, and never substitute upload/fetch time.

Monday/Friday slide drafts remain multimodal first, biomarker second, newest
pair after the instruction slide. Both published slides and their PNG exports
must include large bold red text: “Reminder for Aditya to ask Prasad about stim plan and Donna for any RCS08 medication updates.” No additional Slack bot is needed; the connected
Slack tool's self-DM send was tested successfully and confirmed by Aditya.

Scheduling and delivery configuration are verified; the first future scheduled
run remains an operational check, not a completed run claimed in advance.
