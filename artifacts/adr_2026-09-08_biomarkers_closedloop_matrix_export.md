# ADR — exporting the whole calibrated grid to Closed-Loop Deployment, not one committed band

**Written 2026-09-08 for the Biomarkers heat-map redesign. Not yet approved.**

## Context

Closed-Loop Deployment answers one question at a time today: given exactly one candidate band a
user has already chosen, may it be programmed onto the implanted device, and at what switching
value. The candidate always arrives as a single object in the request; every function on that page
reads only the first entry of the array it is given, confirmed by reading the code directly.

The PI wants Closed-Loop Deployment to instead receive the calibrated grid's entire result — every
frequency point crossed with every length of signal, for every sensing contact pair — so a user can
browse and pick any point there, pre-computed rather than recomputed on the spot, to see how that
choice would change Closed-Loop's own settings.

This project already has a working pattern for exactly this shape of problem: one module writing a
result, a second module reading it, with a chain recording what the result was built from so a
reader can be refused if what it is about to read was itself shaped by its own earlier choices
(decision 31). That pattern already carries a comparable table — the amplitude-effect-by-band
result — from Closed-Loop Deployment to Stim Optimizer today.

## Decision

**Extend the calibrated grid's existing stored entry so it carries the full grid, and let Closed-Loop
Deployment read it as a named consumer, the same way Stim Optimizer already reads Closed-Loop
Deployment's own stored table.** The grid's response is already kept in the shared store today, with
its own key and its own provenance chain built from the underlying recordings and the pain-report
snapshot it was computed from; nothing here is a new storage mechanism, this is the existing entry
carrying more of what it already computes and being read by one more module.

**Reading it from Closed-Loop Deployment does not trip the self-derived-product refusal**, and this
is not assumed — it follows from how the two modules relate. Stim Optimizer's own choices decide
which stimulation settings get explored, which decides which recordings come to exist, which is why
it must be stopped from reading a verdict built from recordings its own policy chose. Closed-Loop
Deployment does not choose what gets recorded; a clinician does, by hand, after reading its report.
Nothing Closed-Loop Deployment produces feeds back into which recordings exist for the calibrated
grid to be built from, so its chain never contains Closed-Loop Deployment's own name, and the
refusal that exists for exactly this reason has nothing to catch.

## What Closed-Loop Deployment needs to change to use this

Today, evaluating one candidate band on that page can cost up to half a minute, most of it in the
full three-source comparison and the receiver-operating curve — both genuinely slow, and both
already computed and cached per band today, just never for more than one band per request. Letting
a user browse all 22×10 points per contact pair would make that cost per click, which is not
acceptable for browsing.

**Two fast facts should be pre-computed once per point and stored alongside the grid**: whether the
device's own rules forbid that configuration outright, and whether the band's relationship to pain
holds up across different stimulation settings rather than being an artefact of one setting. Both
are already computed per band on that page today; computing them for every point in the grid once,
rather than for one candidate on demand, is the same calculation running more times, not a new one.
The slower checks — the full three-source comparison, the receiver-operating curve, the exact
switching value — stay exactly as expensive as they are today and run live only for whichever point
a user actually opens, the same way they do now for the one candidate that arrives today.

## Consequences

- A new field carries the full grid inside the calibrated result's existing stored entry, with the
  same provenance chain the entry already has, extended to note that Closed-Loop Deployment is now
  a registered reader.
- Closed-Loop Deployment's page gains a compact version of the grid-with-selection interaction
  proposed for the Biomarkers page itself, so choosing a point there does not require leaving the
  page or re-entering settings by hand.
- The two fast, pre-computed columns above must themselves be proven live on RCS08 before shipping —
  computing them for 22 points instead of one, and confirming the values agree with what the page
  already reports for a single candidate today, field for field.
- No existing stored value changes; this adds fields to what is already stored and computed, and
  adds a new authorized reader to an existing provenance chain.

## Open questions requiring the PI's explicit sign-off before implementation

Whether Closed-Loop Deployment's compact grid should show the family-wise-corrected label from the
companion ADR (`adr_2026-09-08_biomarkers_sweep_family_wise_correction.md`) alongside the two new
fast columns, and whether a point that fails the device's own rules should still be selectable for
inspection (informational) or should be visually suppressed on that page specifically, since that
page's whole purpose is deployability rather than exploration. Per CLAUDE.md §10 rule 8, this ADR
being written is not authorization to build it.
