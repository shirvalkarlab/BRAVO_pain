# Drafts for the PI — device questions, research-ethics checklist, credential rotation

> Lane 0 of `artifacts/research_2026-09-25_options/11_REVISED_PLAN.md`, items 0.2 and 0.3.
> Everything below is a DRAFT. Nothing has been sent, filed, rotated or deleted. The PI edits and
> sends (or does not) each part separately.
> Prepared 2026-09-25. No BRAVO source file was changed to write this document.

---

## Part A — Draft letter to Medtronic clinical support (item 0.3)

**Purpose.** This project's stimulator is a Percept RC neurostimulator with BrainSense sensing
(the implanted device that both stimulates and records brain signal). Three answers from Medtronic,
in writing, would change what the next research visit can safely and validly do. This project's own
reference document, `DEVICE_percept_rc.md`, states what it currently believes about each question,
where that belief comes from, and where an outside description disagrees. The letter should ask
Medtronic to confirm or correct each belief in writing, quoting their own source.

### Draft text

> To: Medtronic clinical support / DBS clinical specialist team
> From: Prasad Shirvalkar, MD PhD, UCSF
> Re: Three programming questions on a Percept RC neurostimulator with BrainSense sensing, for a
> research protocol (not for altering a patient's clinical care)
>
> We are running a research protocol that reads a Percept RC's sensed brain-signal power and its
> programmed settings, and we need three points confirmed in writing before the next study visit.
> None of this changes how the patient is treated; it decides what we are allowed to measure and
> how we describe the study to our research-ethics board.
>
> **Question 1. Does "Single Threshold Inverse" mode change the current the device delivers, or is
> it sensing-only?**
> Our reference document currently states: "Single Threshold Inverse — Drives stimulation? no —
> sensing only," citing a white paper's Table 1 ("Threshold Mode Default Settings"). Your own
> published "Scientific compendium: BrainSense Adaptive Deep Brain Stimulation," in its Limitations
> section, states that BrainSense aDBS (the automatic-adjustment feature) "is limited to two modes
> or algorithms (i.e., Single Threshold and Dual Threshold)" and does not describe a third,
> stimulation-driving inverse mode at all. Separately, patent filings assigned to Medtronic describe
> a general "single threshold inverse" algorithm that DOES decrease stimulation when the signal is
> below a set point (and, by the mirrored logic, presumably increases it above that point) — which
> would contradict "sensing only" if that is the mode programmed on the tablet's therapy screen.
> **Please confirm, in writing, for the Percept RC's currently marketed firmware: when the tablet's
> therapy screen shows "Single Threshold Inverse," does the device ever change the delivered
> current in that mode, or does it only record the sensed signal with the current held fixed?**
> If the answer is "it changes the current," our software's list of modes it treats as compatible
> with passive research recording (`COMPATIBLE_THRESHOLD_MODES` in this project's code) is wrong and
> needs a second look before any further use of that mode.
>
> **Question 2. Does changing the stimulation rate alone (with amplitude and pulse width held the
> same) cause a momentary dip or interruption in the delivered current?**
> Our reference document describes, and we have measured, a brief ramp (median about 2 seconds) when
> the delivered current is changed, and a 2-second sensing blank around a Dual Threshold amplitude
> change. It does not state whether a rate-only change (for example 55 Hz to 60 Hz, current and pulse
> width unchanged) causes the device to ramp the current down and back up, or changes it in any way
> we should account for when we compare brain signal recorded just before and just after the change.
> We could not find this stated in any published Medtronic document. **Please confirm whether a
> rate-only change on the Percept RC produces any momentary change in delivered current, and if so,
> its size and duration.**
> If the answer is "yes, it dips," a planned comparison of brain signal at 55 Hz against 60 Hz needs
> a longer discard period after each rate change than we currently use, and the discard period needs
> to be set from Medtronic's own number rather than assumed.
>
> **Question 3. Can the patient's own home controller (patient programmer / "My Percept" app)
> trigger anything beyond the standard 10-minute-averaged chronic power log?**
> We already receive, in this patient's device export, 30-second full-spectrum snapshots that begin
> 30 seconds after the patient presses an event button at home — this much is already in our data
> and matches your own published description of the patient-triggered event marker. What we have not
> confirmed is whether the home controller can be configured, or requested from Medtronic, to
> trigger anything richer than that — for example an on-demand recording of the raw brain-signal
> voltage trace (250 samples per second) of the kind that today we can only obtain during an
> in-clinic session with the clinician tablet. **Please confirm whether any home-triggered recording
> beyond the 30-second event snapshot and the 10-minute chronic average is possible with this
> patient's current hardware and software, and if so, how it is configured.**
> If the answer is "no, the home controller cannot do more than this," our planned multi-day home
> sequence must be designed around 30-second snapshots and the 10-minute chronic log only, which
> narrows what it can show about how quickly a change in stimulation setting affects the brain
> signal.
>
> For reference, the device is a Percept RC neurostimulator (model number to be filled in from the
> patient's implant record) with BrainSense technology, used under [protocol number / IRB number to
> be filled in]. We are glad to arrange a call if that is easier than a written answer.

### What was found searching the web, and what stays open

- **Question 1 — a real, citable conflict, not yet resolved by anything public.** Medtronic's own
  "Scientific compendium: BrainSense Adaptive Deep Brain Stimulation" (a Medtronic-published PDF;
  no date printed on the document itself, but it cites papers through 2024, so it is recent)
  states plainly, in its Limitations section: "BrainSense aDBS is limited to two modes or
  algorithms (i.e., Single Threshold and Dual Threshold)," and its "Introduction to aDBS Modes"
  page (p. 11) describes only those two, with no third mode at all
  [Medtronic Scientific compendium, BrainSense Adaptive DBS](https://www.medtronic.com/content/dam/medtronic-wide/public/western-europe/products/neurological/deep-brain-stimulation/adbs-scientific-compendium.pdf).
  That is consistent with, but does not directly confirm, this project's "sensing only" belief.
  Separately, general web summaries of Medtronic patent filings (not clinical or marketing
  documents) describe a "single threshold inverse" algorithm that lowers stimulation when the
  signal is below a set point, which reads as an active, stimulation-changing mode, not a
  sensing-only one — see the patent family under "Brain stimulation and sensing"
  [USPTO filing 12144637](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12144637),
  [USPTO filing 11571576](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11571576).
  Patent language commonly describes capabilities more broadly than what ships in a given firmware
  version, so this is a lead, not an answer — which is exactly why the letter asks Medtronic
  directly rather than the project resolving it from public sources.
- **Question 2 — nothing Percept-specific found.** General patent language about implantable
  stimulators describes ramp schedules tied to pulse frequency and amplitude ramps from zero, but
  nothing found names the Percept RC specifically or states whether a rate-only change (amplitude
  and pulse width unchanged) causes a current dip. This question needs Medtronic's direct answer;
  no published source closes it.
- **Question 3 — partly already answered by this project's own data, not by a public Medtronic
  document.** General Medtronic patient-facing material confirms the patient programmer's event
  marker captures a 30-second brain-signal snapshot after a button press, matching what this
  project already has in the record. No public source was found stating whether the home
  controller can request anything richer (for example an on-demand raw-trace recording) — that
  half of the question is still open and needs Medtronic's direct answer.

---

## Part B — Research-ethics coverage checklist (item 0.2)

**Purpose.** Two planned pieces of the next research visit go beyond what a standard clinical
titration visit does: turning stimulation off for a timed block while recording, and an open-label
sequence over several days at home where the patient's own setting is changed and then returned.
Both may need research-ethics board (the committee that approves human-subjects research; often
called an IRB) coverage beyond what today's approved protocol allows. This checklist is generic
guidance for confirming that coverage — it names the two planned pieces but no site-specific policy,
committee name, or protocol number, since those belong in the PI's own filing, not this document.

### Checklist

1. **Locate the currently approved protocol and consent form and read what they permit today.**
   - Does the approved protocol describe research recording during clinical titration only, or
     does it already describe a stimulation-off research block and a multi-day home sequence?
   - Does the approved consent form mention that stimulation may be turned off for research
     purposes, even briefly, and that the patient may go home with a setting different from the one
     their clinician would otherwise have chosen?
   - If either planned piece is not described in the current protocol or consent form, an
     amendment is needed before that piece can run — not merely the PI's own sign-off.

2. **Classify the risk level of each planned piece, in writing, before scheduling it.**
   - A timed stimulation-off block: is it minimal risk (no more than the patient's day-to-day
     experience when their device is off for other clinical reasons, such as a low battery or a
     programming visit) or does the board consider it more than minimal risk for this patient given
     their history? This determination is the board's to make, not the research team's.
   - An open-label multi-day home sequence at a setting other than the one otherwise programmed:
     does it require a data safety monitoring plan (a defined way of checking in on the patient and
     stopping early if something goes wrong), and if so, has one been written down?
   - State plainly, in the request to the board, who decides to stop the sequence early and how
     the patient reaches the study team if something feels wrong at home.

3. **Confirm the device-use classification.**
   - Is turning stimulation off, or programming a setting purely for research purposes rather than
     clinical benefit, still within the device's approved (on-label) use for this patient's
     condition, or does it count as an off-label or investigational use that needs its own
     regulatory pathway (for example, an Investigational Device Exemption) separate from the
     research-ethics approval?
   - If the answer is uncertain, this is a question for the device's regulatory contact
     (Medtronic, Part A above) and the institution's research-compliance office jointly, not a
     research-ethics-board question alone.

4. **Confirm informed consent covers what will actually happen.**
   - Does the consent language the patient already signed describe, in terms they would
     understand, that their stimulation will be turned off for a period, and for roughly how long?
   - Does it describe that they may go home for several days on a stimulation setting chosen for
     research rather than for their own symptom control, and that this is described honestly as
     "open-label" (the patient and the team both know what setting is in use) rather than
     "blinded" if that is in fact the case?
   - If any of this is missing, a consent amendment — with the patient re-consenting — is needed
     before the sequence runs, not only a verbal explanation on the day.

5. **Confirm continuing-review and reporting obligations are current.**
   - Is the protocol's continuing review (the board's periodic re-approval) current as of the
     planned visit date?
   - Does the board's adverse-event reporting plan already cover what would count as a reportable
     event during a stimulation-off block or a home sequence (for example, a specific pain or
     side-effect severity threshold), or does that need to be added by amendment?

6. **Confirm scheduling reflects the approval timeline, not the reverse.**
   - If an amendment is needed for either piece, the visit that depends on it should be scheduled
     after the amendment is approved, not before, even if that means the visit slips by weeks or
     months. The research-ethics board's approval is the gate; a clinician's or PI's own comfort
     with the plan is not a substitute for it.

7. **Keep a one-line record of the outcome for each piece**, e.g. "stimulation-off block: covered
   under existing protocol, no amendment needed, confirmed [date]" or "home sequence: amendment
   submitted [date], pending." This is the fact the rest of the research plan (Lane C in the
   revised plan) needs before it can put a date on either piece.

---

## Part C — Generic steps: rotating REDCap API tokens and removing a tracked credentials file from git

**Purpose.** These are generic steps, usable in any project. No project name, host name, token
value, or file path from this or any other specific repository appears below; fill in the specific
names when actually carrying this out.

### C1. Rotate REDCap API tokens

An API token is a code that lets a program read and write data in one REDCap project, tied to one
person's account and that project only. Rotating a token means invalidating the old one and issuing
a new one, without needing to delete or recreate the REDCap project itself.

1. Log in to REDCap and open the project the token belongs to.
2. Open that project's "API" page from the left-hand project menu (this requires the "API Export"
   and/or "API Import/Export" user right on the project; if you do not have it, ask the project's
   REDCap administrator to grant it or to rotate the token on your behalf).
3. If a token already exists, use the "Regenerate token" action. This immediately invalidates the
   old token — any script or service still using it will start failing right away — and issues a
   new one in its place. This does not require deleting the token first, and does not affect the
   project's data.
4. Copy the new token immediately; REDCap does not display it again after you navigate away.
5. Update every place the old token was stored (a secrets manager, an environment variable, a
   configuration file kept outside version control) with the new token. Do this for every token
   being rotated before testing, so nothing is left half-updated.
6. Test each script or integration that uses the token against a harmless, read-only call first
   (for example, exporting the project's field names) before relying on it for anything else.
7. Repeat for every token that needs rotating. If several tokens belong to different people on the
   same project, each person rotates their own; one person cannot regenerate another's token without
   administrator access.
8. Record the date each token was rotated somewhere the team can see it (a shared log, not the
   token's own value), so a future audit can tell how old the live tokens are without needing to
   see them.
9. As ongoing practice, rotate tokens on a fixed schedule (for example, every few months) even
   with no known exposure, and immediately, unscheduled, the moment any token is suspected to have
   been seen by anyone who should not have it — including a token that was ever committed to a git
   repository, whether or not that repository is private.

### C2. Remove a tracked credentials file from a git repository, and replace it with a template

This assumes the credentials in the tracked file have already been rotated (C1), or are being
rotated as part of this same process — a file removed from git history is not "safe" if the old
values inside it still work somewhere.

1. **Rotate first, remove second.** Treat every credential that was ever committed as compromised,
   whether or not the repository is private and whether or not anyone is known to have seen it.
   Removing the file from history does not undo any use the old credentials may already have had.
2. **Stop tracking the file going forward**, without deleting it from disk yet:
   `git rm --cached path/to/credentials-file`, then add that exact path to `.gitignore` so it is
   never accidentally re-added.
3. **Write a template file** that has the same shape (the same field names) as the real file but
   with placeholder values instead of real ones (for example `API_TOKEN=REPLACE_ME`), and commit
   the template under a clearly different name (for example, the real file's name with `.example`
   or `.template` appended). This is what a new clone of the repository needs to get started; the
   real, filled-in file stays local to each machine and is never committed again.
4. **Decide whether the credentials need to be removed from the repository's history, not only
   from its current state.** Untracking the file (step 2) stops NEW commits from carrying it, but
   old commits that already contain it still have it, and anyone with a clone of the repository, or
   access to it before it was made private, already has those old commits.
   - If the repository has always been private and every person who has ever cloned it is known
     and trusted, and the credentials are already rotated, rewriting history may not be necessary —
     rotation alone makes the old values harmless.
   - If the repository was ever public, or its access list is not fully known, or policy requires
     it regardless, the credentials should be removed from history using a tool built for this
     (`git filter-repo` is the tool current git documentation recommends; older guides mention
     `git filter-branch` or the BFG Repo-Cleaner, both superseded by `filter-repo` for this purpose).
5. **If rewriting history:** every person with a clone of the repository must be told before it
   happens, because a rewritten history means their existing clone no longer matches the remote —
   each of them will need to re-clone, or reset their local branch to the new history, rather than
   pushing or pulling normally. Rewriting history on a shared branch without warning collaborators
   is the most common way this step causes damage.
6. **After the rewrite (if done), force-push the cleaned history** to the remote, then confirm with
   each collaborator that they have re-synced. Old copies of the repository (forks, cached views on
   a hosting provider, anyone's un-updated local clone) may still carry the old history until they
   are cleaned or discarded too — history rewriting inside one repository does not reach copies
   outside it.
7. **Turn on automated secret scanning going forward** if the hosting provider offers it (for
   example, push protection that blocks a commit containing a recognizable credential pattern
   before it is ever pushed), so a future credentials file cannot be committed by accident. A
   pre-commit check that scans for likely secret patterns before a commit is made is a second,
   local layer of the same idea.
8. **Confirm the template is actually enough to get started**: have someone who does not already
   have the real credentials try cloning fresh and following only the template and its
   instructions, to confirm nothing undocumented was needed.

---

## Draft decision row (for the orchestrator's digest, plain English, every number beside its claim)

Lane 0 drafts written, none sent or executed: (a) a letter to Medtronic asking three precise
questions — whether Single Threshold Inverse changes delivered current, whether a rate-only change
dips the current, and whether the home controller can trigger more than the existing 30-second event
snapshot and 10-minute chronic log — citing this project's own device document and a genuine,
unresolved conflict between it (sensing only) and a public Medtronic compendium (describes only two
active modes, not three) plus general patent language (describes a mode that does change
stimulation); (b) a seven-point research-ethics checklist for the planned stimulation-off block and
open-label home sequence, covering protocol scope, risk classification, device-use classification,
informed consent, continuing review, scheduling order and a one-line outcome record; (c) generic,
project-name-free steps for rotating REDCap API tokens (regenerate invalidates the old token
immediately; no project deletion needed) and removing a tracked credentials file from git while
keeping a placeholder template, with rotation always before any history rewrite and collaborator
notice before any force-push. No BRAVO source file was read for values shown to a patient or
clinician, and no BRAVO source file was edited. File written:
`artifacts/drafts_2026-09-25_lane0_device_ethics_tokens.md`.
