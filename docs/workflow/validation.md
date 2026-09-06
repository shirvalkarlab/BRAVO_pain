# Aditya contributor validation

The supported end surface is the Aditya Docker appliance on loopback, opened in
Chrome. Default BRAVO report structure is preserved; approved REDCap, Oura and
neural inputs must agree across native reports and imported research analyses.
Unsupported features show a disabled control and reason. Research outputs do
not authorize or program a neurostimulator.

This guide applies the universal `rigorous-project-workflow` acceptance contract
to the existing repository. It does not claim the inherited code already meets
that contract. Use **passed**, **failed**, **unverified**, and **not applicable**
separately for code, scientific validity, browser usability and deployment.

## One local gate

From the checkout root, with Docker Desktop running:

```bash
scripts/bravo-validate prepare
scripts/bravo-validate check
```

The frontend test image uses Node 22 and npm 10, with `npm ci` from the existing
lockfile; no host Node installation is required for this gate. `prepare` builds a
local backend test image from
the same `server-deps` stage as the application, adding pinned pytest 8.3.5,
pytest-cov 6.0.0 and coverage.py 7.6.12. Backend execution has no network, service
ports, deployment environment, secrets or appliance-volume mounts. It uses an
in-memory SQLite database and disposable filesystem. A backend `.env` is refused.
Preparation needs network access to install declared dependencies;
tests do not fetch source participant data. Synthetic policy/model fixtures and the
separate, explicit private calibration acceptance checks are documented in
[portable fixtures](portable-fixtures.md). Private calibration skips in this
portable run do not count as private scientific acceptance.

The existing Python deployment deliberately remains Docker plus its requirements
file. The scientific stack embeds distro R, `rpy2`, `lme4`, `lmerTest`, and
`emmeans`; moving it to a host `uv` environment without verifying that ABI and
model compatibility would introduce a second environment. A future `uv` migration
must reproduce the container's numerical/model tests before replacing this
workflow. The frontend lockfile is used by `npm ci`; do not run `install:clean`
for acceptance because it deletes the lock. Docker base tags, apt packages and
some Python requirements are not yet an immutable full lock: clean rebuild
reproducibility is **unverified**, even when a cached local build works.

The entry point runs tooling regressions, backend tests, frontend tests, true
branch coverage and the production Docker build sequentially. A failed test or
coverage gate stops acceptance. It never starts or replaces the live app.
Individual commands are available to diagnose a failed stage:

```bash
scripts/bravo-validate backend
scripts/bravo-validate frontend
scripts/bravo-validate coverage
scripts/bravo-validate build
scripts/bravo-validate live
```

`live` runs the appliance readiness/identity check only. It does not establish
successful browser interaction. The candidate tag is
`bravo-local:validation-candidate`; no tag or port in this guide starts Prasad's
separate deployment. Do not mount private data into the portable test runner.

## Coverage scope and legacy adoption

The executable scope is in
[`scripts/validation/contract.json`](../../scripts/validation/contract.json).
The report collector includes all Python under `BRAVO/modules`, `BRAVO/Server`
and `BRAVO/BRAVO`, and all JS/JSX under `Client/src`, including files not imported
by tests. Tests and database migrations are excluded from the *production
baseline*; migration correctness needs its own prior-schema integration check.

The current strict scope includes canonical input selection, participant/QC
policy, feature availability, analysis jobs, sync/cache preparation, the research
API, the newly authored closed-loop adapter and frontend data-selection/request
helpers. Every discovered critical module and their aggregate must reach **95%
true branch coverage**. New source files appear in the full-tree baseline automatically;
new consequential integration modules must be added to the critical contract.
Missing reports, missing source entries, inconsistent instrumentation, failed
tests, source changes during/after collection and weakened thresholds fail the
gate. A module with zero branches is reported as N/A, not 100%.

Python counts use `covered_branches / num_branches`; JavaScript counts use
Istanbul's branch hit arrays and matching locations. Combined statement/branch
percentages are not accepted. `reports/validation/branch-summary.json` reports
the full legacy baseline and every below-threshold critical module. Do not trim
scope, bless snapshots, or delete tests to turn it green. When changing critical
logic outside the declared scope, add that module to the contract before using
the gate to claim acceptance.

For new helpers inside large reused files, the contract declares exact critical
function names and a specific legacy exception for the remaining file. Each
function and the combined critical scope still require 95% true branches.
Coverage.py's actual per-function branch counts are used for Python. For
JavaScript, the gate requires one exact named Istanbul function and counts all
branch outcomes within its declaration/body range, including nested callbacks;
it never substitutes function-call counts. Missing functions fail the gate.
These scoped checks make no whole-file 95% claim. The complete legacy file stays
in the measured baseline, with its source revision, residual risk, alternative
evidence, owner and revisit condition recorded in the contract/report.

Unchanged imported Prasad algorithms are reused upstream code, with their source
revision recorded by the adapters; they remain in the measured legacy baseline.
They are not newly authored first-party logic, nor automatically validated by
passing adapter tests. Substantive new changes to those algorithms must be added
to critical scope and independently checked numerically.

The remaining inherited source tree is a declared legacy adoption gap, **not a
95%-compliant product**. Its risk is unexercised legacy behavior; alternative
evidence is focused regressions and representative real API/browser journeys.
The Aditya maintainer owns this gap. Revisit the affected module whenever it is
substantially changed, and before a shared release. Missing critical coverage
has no blanket legacy waiver.

Some existing tests compile production function bodies or mock ORM/external
boundaries. They establish bounded logic behavior; even recorded branches from
such tests do not prove that the installed module imports, authenticates, queries
the database, dispatches a worker or returns a usable response. Real component
and private-data acceptance below remain required. Skipped external-model or
source-fixture tests are **unverified**, not successful model validation.

## Requirement-to-evidence map

| Required behavior | Portable evidence | Required real integration or review |
| --- | --- | --- |
| Combined/Oura/REDCap/neural selection and independent events | `timelineViews`, annotation and survey-overlay Jest tests | Chrome selections preserve values; Oura-only starts with events off; overlays toggle independently without refetch |
| Approved REDCap times, exclusions, missing values and metric definitions | `test_analysis_data`, `test_rcs08_sync`, survey/PainScores tests | Compare approved stored survey identities, times and each value with native timeline and research API; separate historical forms |
| Oura staff-testing exclusions and preserved gaps | `test_oura_qc`, policy-association tests | Reconcile retained/excluded counts and times with the review workbook; raw source hashes unchanged |
| Neural source eligibility, implant boundary and alignment | policy, input-consistency and research-loader tests | Verify raw JSON identifiers, excluded sources, decoded record times and single application of alignment through returned analysis inputs |
| No inaccessible or empty-data features | feature availability Python/Jest tests | Test empty, unreadable and present sources via real participant API; inspect disabled controls/reasons in Chrome |
| Research authorization and shared canonical input manifests | `test_prasad_api_inputs`, research package tests | Real authenticated and denied API requests, tenant isolation, schema errors, polling/result manifests, canonical source-to-output reconciliation |
| Sync/job deduplication, restart and persistence | sync/jobs tests and request-hook tests | Multiple tabs/readers; navigation away/back; worker restart; retained result and changed-input invalidation |
| Prasad analyses are qualified research outputs | package numerical and adapter tests | Verify source revision, current canonical input fingerprint, actual outputs and data-dependent unavailable states; independent scientific review where required |
| Fast common pages and bounded heavy requests | cache/input invalidation and job tests | Measure cold/warm page/API times, 20 concurrent readers and repeated restarts; record exceptions to the under-10-second aim |
| Correct delivered Aditya appliance | production image build and model loading tests | Match branch/source/image identity; `bravo-appliance check`; actual Chrome URL/title and critical journeys after replacement |

Browser inspection must be text-only. Do not enable screen sharing, capture,
screenshots, capture helpers, or Chrome's AppleScript JavaScript setting. Opening
a tab or receiving HTTP 200 is insufficient. If Chrome blocks inspection, report
that limitation instead of claiming the page works.

Keep real-data audit scripts, results, counts tied to participant identities and
workbooks in ignored `reports/` or `outputs/`; publish only synthetic portable
fixtures and generic behavior checks. Never copy those local evidence directories
into CI artifacts. Keep one local current state record with active handles,
tested source identity and next actions; do not imply work continued while paused.

## GitHub CI and readiness boundary

[BRAVO validation](../../.github/workflows/validation.yml) runs the same `prepare`
and `check` commands from a clean checkout on pushes to `aditya`, pull requests
targeting `aditya`, and manual dispatch. The required job name is **Portable
acceptance**. It uses an ephemeral GitHub-hosted Ubuntu 24.04 runner, a read-only
repository token with credentials removed after checkout, and no deployment
secrets or private source data. Tests retain their network-disabled containers.
The production image is built locally on that runner; nothing is deployed or
published as an image. The pinned official
[checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) and
[upload-artifact v7.0.1](https://github.com/actions/upload-artifact/releases/tag/v7.0.1)
commits were resolved from their release tags when this workflow was authored.

Preparation and acceptance run sequentially with failure propagation; test,
coverage or build failure fails the job. Only explicit portable logs, coverage,
status reports and tested-commit identity are retained for seven days, including
diagnostics after failure. The artifact is evidence, not an independent success
gate. No participant evidence directories, raw data, model assets, secrets or
deployment environment are uploaded. Do not add private fixtures to this gate.

The job is bounded to 120 minutes (50 for preparation, 60 for acceptance).
The standard private-repository Linux runner currently provides
[2 CPUs, 8 GB RAM and 14 GB SSD](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
The scientific Python/R images and frontend production build must fit this
capacity; a timeout, dependency download failure or resource exhaustion is a
failed/unverified run, never grounds to drop tests or silently select a paid
larger runner. Clean hosted execution and immutable dependency reproducibility
remain unverified until evidenced by a run; see the dependency-lock limits above.

After each authorized push, match the final local commit, remote `aditya` commit,
and workflow run `headSha`; inspect the **Portable acceptance** job conclusion.
For pull requests inspect the checkout's recorded `tested_commit`, which normally
identifies GitHub's temporary merge candidate rather than just the PR head.
Revalidate when the candidate or base changes, including a final documentation
commit. Missing, skipped, cancelled, pending or failed checks do not establish
acceptance. In GitHub's effective branch rules, require **Portable acceptance**
from GitHub Actions on `aditya`, require an up-to-date tested candidate and review
under the owner's policy, and inspect bypass permissions. Configuring or changing
those rules needs authorization; the YAML alone does not enforce merging. Private
repository plan/permission limits and unconfigured protection must be reported
explicitly, not described as protection in place.

CI proves the portable gate only. Separate private-data, browser, deployed and
independent scientific/model acceptance remain required. Local-only evidence
must still be labeled local-only. An image built from an uncommitted worktree
needs its source snapshot fingerprint as well as the base commit; the commit
alone does not identify it.

## Upstream updates

The authoritative update policy and schedule are in
[automatic updates](../automatic-updates.md). Keep one maintenance owner and the
Fixel → Prasad → data synchronization → cache preparation order. Both source
branches require independently observed 48-hour quiet periods; explicit immediate
integration requests bypass only the requested delay. The timer never bypasses
source review, conflict handling, this validation gate or deployed verification.

Do not add another updater, data-sync timer or cache timer beside the configured
orchestrator. Keep manual sync requests functional. A failed candidate or deadline
must preserve the working deployment and report incomplete stages honestly.
