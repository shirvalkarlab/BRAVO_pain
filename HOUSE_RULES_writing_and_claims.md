# House rules: how to write, and what may be claimed

From the PI directly, over several sessions, each after a piece of writing failed to communicate.
They have caught an invented calibration constant, a units error and a mislabelled brain side.
Read before writing any reply, report, commit message or document. Compacted 2026-09-19 with his
permission to paraphrase; the original wording is at `docs/archive/2026-09-19/`.

## 1. No jargon: use the plain replacement, never the term with a gloss bolted on

He could not follow a summary built from bare technical nouns and invented hyphenated compounds.
If a term is unavoidable, put a descriptive adjective before it and state the literal quantity.
Short sentences, colloquial English, and define anything technical on first use **in every
response**. Flagged as unintelligible when bare: arm, era, screen, separation, floor, capture,
record, direction, and every hyphenated compound ("step-median unit", "tile-level scoring",
"five-era window", "capture separation floor", "two-arm capture test").

## 2. Replacement table

| Do not write | Write |
|---|---|
| separation, standardised separation | the gap between the two measured power levels, in units of their own scatter |
| capture, two-point capture, arm | the device's two measurements: band power at a low current and at a high one |
| floor | minimum required value |
| era | the time block used for grouping, and say which: calendar month or clinic visit |
| screen | the step that checks every candidate band and reports which are usable |
| record, full record | all the data we have |
| direction | whether power rises or falls as current increases |
| slope | change in power per milliamp |
| span, ladder | the range of currents tested within one visit |
| tile | a 3-second chunk of recording |
| cell | one combination of sensing contact, brain side and rate; on a grid, one band at one length of signal |
| cluster, cluster mass | a run of neighbouring bands all showing the effect; its summed statistic |
| family-wise p | p corrected for having tested many bands |
| resolution floor | the smallest p the number of shuffles can produce |
| permutation, null | shuffling the data to see what happens by chance |
| era-blocked, adjusted | after statistically removing differences between time blocks |
| cluster-robust | standard errors allowing for repeated measurements within one group |
| anti-conservative | produces p-values that are too small |
| constant, literal | a fixed number written into the code |
| gate | a check that can refuse |
| deployable | allowed to drive closed-loop stimulation |
| frozen configuration | the rate and pulse width locked in before closed loop starts |
| shape (of a variable) | what kind of thing it is, as opposed to what is in it |
| fan-out, fan-out guard | one job starting more jobs; the check that stops that |
| no-op (reporting success) | it did nothing (and said it had worked) |
| launcher / detached | the code that starts the background job / the job outlives the page |
| already_current | the answer was already saved and did not need building |
| served / fresh | came from the saved copy / worked out from scratch |
| bookkeeping fields | values that only record when and how long something ran |
| the store, cache store / kind / entry / key | the saved answers on disk / the type of saved answer / one saved answer / the label it is filed under, built from everything that could change it |
| marker file | a small file recording that a job started, so two do not start at once |
| the request path / prefetch | while somebody is waiting for the page / fetching before it is asked for |
| container suite, host suite | the two sets of tests, and say which machine each runs on |
| equality proof | a check that every number came out the same as before |
| contact, R 0⁻3⁺ | the pair of electrode contacts the signal was recorded from, named in full |
| compute (noun) | work, or computing time |
| spectrum, spectral (bare) | **never**: name the quantity: the device's own FFT snapshot; the PSD computed from the voltage trace; PSD-derived LSB; time-domain-derived LSB; a direct LSB recording |

Two habits: say the number and its meaning in one breath ("reading the saved answer took 2.9 s;
working it out again took 10.4"), and when a function, file or setting must be named, say what it
does first and put the name in brackets after, for when he wants to find the code.

## 3. Two reserved words

1. **"Threshold"** is a device setting in a closed-loop configuration, the value at which the
   stimulator switches. Never a statistical cut-off, a minimum, or an analysis criterion.
2. **Never "the floor" for an effect size.** Say "the minimum effect size we require".

## 4. A claim and its result go in the same response

Never announce that something stands out, is decisive, is off, or has been found, and then defer
the substance to a pending tool call. State the information, with the numbers, in that sentence or
the next, before any further tool call. His correction on this was emphatic and is not repeated here.

## 5. Prose to avoid (it reads as if two AIs wrote it)

Colon-then-imperative pairs; two-word declarative fragments as topic sentences; personified
abstractions as subjects ("the second innovation decides"); escalating tricolons; antithesis or
chiasmus for closure; formulaic pivots ("the implications go beyond pain"); "the X they have always
lacked"; participial flourishes appended to a clause; "what I did and did not do"; "I will tell
you plainly". Write plain English in the register of scientific writing: define the term, say what
it does, say why it matters here; bullets and numbered lists, bold for what is urgent.

## 6. Eight things never to claim (from `METHODS_measurement_and_findings.md` §7)

1. That a band does not respond to stimulation, from a narrow range of tested currents: say only
   that no movement was detectable across the currents tested, state the smallest detectable
   movement and the number and range of currents, and give effect size with its interval.
2. That a result is established on one visit day.
3. Anything about one side from a figure that pools both stimulators' currents.
4. A test-suite count without a traceable run.
5. That an area under a curve is above chance by comparing it to zero; the reference is 0.5.
6. "Fold" in two senses; write "median fold error" in full (a multiplicative factor, at least 1.0).
7. That the composed conversion constant was measured; say composed, and from what.
8. A test whose name asserts something untrue is worse than no test; split, never relabel.

## 7. Commit identity

Prasad Shirvalkar, `prasad.shirvalkar@ucsf.edu`, on every commit from 2026-09-07, passed inline
with `git -c user.name=... -c user.email=...` because the sandbox cannot write git config. Earlier
commits keep their machine identity; nothing pushed is rewritten.
