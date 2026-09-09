# Operations runbook — how to run things here, and the traps that have already cost time

**This document replaces §7 of the mega handoff and the operational sections of the session
handoffs.** Where those disagreed, the newer test result was taken; each resolution is in
`.planning/2026-09-06-cache-store-and-record-consolidation/findings.md` §1.

**Every item here is a trap that has already been paid for. Do not rediscover them.**

---

## 1. The container, and the mount

The platform runs in the `bravo-server` OrbStack container. The repository's `BRAVO/` subtree is
bind-mounted at `/usr/src/BRAVO`.

**`/usr/src/BRAVO` IS a live mount, so copying files in through the bridge is unnecessary — write
on the host and run.** `mount` reports `mac on /usr/src/BRAVO type virtiofs (rw,relatime)`, and a
file written on the host is visible in the container immediately, for `modules/` as well as
`_agent_bridge/`.

**Only repository-ROOT files are genuinely absent** — this document, the mega handoff, the session
handoffs, `Client/` — because the mount is the subtree and not the root. **That is the whole of
what the original observation proved.**

**An earlier claim that it is not a live mount was wrong, and it propagated into a session
handoff, into project memory and into the messages of commits `b700717` and `7ab2d1b` before being
disproven by direct test. Two pushed commit messages still carry the wrong claim and cannot be
edited.**

**Running code in the container:**

```
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout N --wait M "<cmd>"
python3 BRAVO/_agent_bridge/bridge_client.py --status        # heartbeat
```

- The container runs **Python 3.12.3, rpy2 3.5.15, pymer4 0.8.2, pandas 2.2.3, sklearn 1.5.2**.
- **The bridge takes effect on container CREATE, not restart.**
- **The watcher stalls periodically** — the heartbeat age climbs and jobs time out. The fix is an
  OrbStack container restart, which this sandbox cannot do. **Ask the PI.**

---

## 2. Running the tests

**There are two suites and they run in different places. Neither count may be quoted without a
run behind it.**

**In the container — the authoritative runner:**

```
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 900 --wait 900 \
  "python3 _agent_bridge/run_tests.py"
```

**On the host, environment `bravo_app`**, whose interpreter is
`~/.claude-science/conda/envs/bravo_app/bin/python` (Python 3.11 with pytest). The `python` on the
path (pyenv 3.12) has no pytest and fails with `No module named pytest`:

```
cd BRAVO/modules && PYTHONPATH=. ~/.claude-science/conda/envs/bravo_app/bin/python -B -m pytest \
  ClosedLoopDeployment/tests StimOptimizer/tests CacheStore/tests DecodeCommon/tests -q -W ignore
```

**Read the pass-and-fail line from the run. Do not carry a number from any document, including
this one — that is why no count appears here.**

Three constraints on testing in the container:

1. **There is no pytest in the container.** `run_tests.py` is the only runner and **it runs the
   whole suite** — a targeted selection is impossible there. To exercise one new file specifically,
   run it on the host if it is free of Django, or accept the whole-suite count as the evidence.
2. **`pytest.approx` and `pytest.raises` are unavailable** in `modules/Biomarkers/tests/`. Use
   plain absolute-difference comparisons there.
3. **Running the biomarker tests outside the container shows harness-only failures** — three tests
   need Django's application registry, and model-dependent files cannot run in the local runner at
   all. **Those are not regressions.** Pure-function checks can run on the host by importing
   `analytics.py` free of Django in `bravo_app`.

**Local decode on the host needs a dummy encryption key**, set **before** importing the helper
module:

```python
os.environ["DATASERVER_ENCRYPTION"] = Fernet.generate_key().decode()
```

---

## 3. Making a backend change actually take effect

**The auto-reload is unreliable and has silently served stale code for about thirteen hours.**
Workers sat on unchanged modules across many edits while the host and container files were
byte-identical. **Passing the test suite proves nothing about what the web workers are executing.**

**After any backend change:**

1. Send an explicit reload — `kill -HUP 1` inside the container.
2. **Then verify the worker start times are newer than the newest edited file** before believing
   anything is live.

The server is started with **four workers, not five.** A process listing shows five lines because
the first is the master. **Read the parent process identifiers before counting.**

---

## 4. Making a frontend change actually take effect

**The repository commits the compiled bundle and the web server serves the mounted build. A
frontend source edit that is committed without a rebuild produces a component that exists in the
source and in no served bundle — and such a component can neither render nor report a failure.**

**This has already happened**: a panel was committed without a rebuild, the build manifest was
stamped 41 minutes before the source was written, and the report was "the matrices don't display"
with no error anywhere to find. **It is the leading suspect for the evidence triangle not
displaying now.**

**The build:**

```
cd Client && export npm_config_cache=/tmp/npmcache && GENERATE_SOURCEMAP=false \
  NODE_OPTIONS=--openssl-legacy-provider CI=false npx --no-install react-scripts build
```

**Then prove the change reached a served chunk.** Search the built chunks for **string literals the
panel owns**, not component names — a production build renames components. The closed-loop panels
are code-split into chunk 431; the timeline is chunk 768.

**Commit the rebuilt chunks in the same commit as the source edit**, or the served bundle drifts
from the source.

**One hard drawing constraint in the closed-loop panels.** They draw **once** and mutate by
restyling a specific trace index. **Never rebuild a figure on interaction.** Following the Python
figure-rebuild pattern verbatim reintroduces a bug in which every figure flashed back to its
loading state on any interaction.

**Then look at the page, and sign in with the demo account rather than registering a new one.**
The principal investigator keeps a standing login on this local instance for exactly this —
**ask him for it; the address is `demo@bravo.local` and the password is deliberately not written
into this repository**, because this file is committed and pushed and `CLAUDE.md` §2 principle 3
forbids credentials in the tree. It is also recorded in the agent's own local memory store, which
is gitignored.

**Registering a fresh account instead has cost three sessions a day's work each, and the reason is
not the login.** A newly registered account carries no `StudyDataRel` row for the live
participant, so RCS08 is invisible to it however correctly it signs in — that was decision 70's
finding after decisions 60, 66 and 67 each blamed the login screen.

---

## 5. Editing source — two files that need care

**`Server/APIs/DataAnalysis.py` and `Server/APIs/urls.py` use carriage-return line endings while
all other source does not.** A line-ending-preserving editor keeps them; a plain Python `open()`
and write strips them and produces an enormous spurious difference. **Use the preserving editor for
those two.**

---

## 6. Git in this sandbox

- **`.git/config` is not writable.** Set the identity per commit through the author and committer
  environment variables rather than configuring it.
- **Commit identity is an open question for the PI.** The session rules ask for commits under his
  name and email; commits have been made under a machine identity instead, because attributing
  machine-written commits to a named researcher in the permanent record of a research repository is
  his decision. **Raised three times, unanswered. Ask, then apply the answer consistently.**
- **Git protection runs in coarse mode here** because the granted paths contain many repositories,
  so `.git` structures are write-denied everywhere writable and `init`/`clone` are blocked.
- **`Operation not permitted` on `.git/config` and on the global ignore file, the keychain warning,
  and the `could not write config file` notice are all harmless.** The commands still return their
  output.
- **No GitHub command-line tool is usable here** — it cannot verify certificates when sandboxed on
  this platform, so every call fails. Use the REST interface with the token from the environment.
  **Self-approval of one's own pull request is blocked**; post the review as an issue comment, then
  merge by the interface.

---

## 7. Figures, artifacts, and the viewer

- **Picture export through the headless browser is broken in this sandbox.** Write a standalone web
  page, use the plotting library that renders locally, or render in the container through the
  bridge. **Never the headless-browser export path.**
- **Saving an artifact deduplicates by filename and will not re-read changed content.** Use a fresh
  filename when the content changes. It resolves workspace-relative paths only, so a repository
  file must be copied in first.
- **The drawing-tool viewer tile does not render in the web client on the PI's machine**, though it
  works in the desktop application and on the vendor's own site. **A successful return from the
  viewer is not evidence he can see anything. Ask which client he is in.**

---

## 8. Numeric and version traps that change results

- **Epoch conversion must be at nanosecond resolution.** Use
  `…to_numpy().astype("datetime64[ns]").astype("int64")/1e9` at every site. A bare `.astype("int64")`
  gives microseconds under the newer pandas default and **mis-assigns the stimulation epochs.**
- **The pain-report timestamp is California local wall-clock time, not universal time.** Always
  convert through `bravo_service._pro_timestamps_utc`. Device start times are already universal.
  **Parsing the report as universal smears every match by seven to eight hours.**
- **Classifier version skew is a correctness risk.** The container has sklearn 1.5.2 while some
  stored classifiers were fitted under 1.6.1. **Loading across that skew can silently mis-predict.**
  Re-validate before trusting one.
- **The Redis client must be constructed with protocol version 2**, because the running Redis
  predates version 6 and rejects the newer handshake. Otherwise every call fails with "unknown
  command HELLO".
- **The container's package installer refuses by default** — pass the flag that overrides the
  externally-managed-environment guard. **Those installs are ephemeral; the durable fix is the
  pinned manifest at `BRAVO/requirements.txt`.**
- **The plotting library was missing from the server for a long time and failed silently**, costing
  the Stim Optimizer page every one of its figures, because the figure builder imports it inside the
  function. **Now pinned.**

---

## 9. Where things are

- **The live participant identifier for RCS08 is `2e3c75c00d7f4f37b53a048d195f11da`.** An older
  identifier is stale after re-ingest.
- **Device exported files** are at the shared-drive grant `…/PNL/RCS008 jsons`.
- **The cached pain-report table** is at `BRAVO/_pro_dump/RCS08_chronic_pro_df.csv`.
- **The REDCap credential file** `secrets/redcap.env` is excluded from version control, as is the
  bridge mailbox.
- **Patient-information note, operational rather than an action item: the Stage-1 device file names
  in the shared-drive grant carry real patient names.** Keep that folder out of the repository.
  RCS08 is the de-identified code, and repository exports are derived spectral features only.

**Documents that are artifacts and not repository files.** The design ledger
`DESIGN_biomarker_pipeline_v2.md` exists **only in the artifact store** — artifact
`f9b3d791-7e95-44bb-bd81-8aebcf9e1b3b`, latest stored version
`c7bf4b85-4867-4e3a-b8de-2ba900d1fd9b`, and a second record `917ae0bd-7f0a-4fd5-af3d-8a00d4446936`
holds a same-sized duplicate, so a search returns two rows. **A session that greps the working tree
for it will find nothing and could wrongly conclude the design record does not exist.** The same
applies to anything the project rules describe as being in artifacts.

---

## 10. Session obligations

From the project's own session rules, and they are not optional:

1. **After any code change, update the session handoff and the mega handoff's recent-work
   section** — and now also this document set, whichever part the change touched.
2. **After any frontend source change, rebuild the bundle** and commit the rebuilt chunks with the
   source.
3. **Before finishing, run both suites through their own runners and report the counts from those
   runs.**
4. **Do not edit the shared result-cache contract files** — `resultCache.js`, `useCachedResult.js`,
   `RecomputeBar.js`. **They are the PI's, and two defects in them are open on him.**
5. **Plan approval is not execution authority.** The PI gives an explicit go-ahead before
   implementation begins. The one exception he authorised himself was the Redis memory bound,
   because it was a live hazard rather than an improvement.
