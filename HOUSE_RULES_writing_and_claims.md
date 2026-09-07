# House rules: how to write, and what may be claimed

**These rules came from the principal investigator directly, over several sessions, and until now
they existed only in one tool's stored memory.** They are written here because a tool that cannot
read that memory would otherwise lose them, and they are the rules that have caught an invented
calibration constant, a units error, and a mislabelled brain side.

**They are not stylistic garnish.** Each one was stated after a specific piece of writing failed to
communicate, and several were stated emphatically. Read them before writing any reply, report,
commit message or document.

---

## 1. The top-priority rule: avoid jargon entirely

**Use the plain-language replacement instead of the jargon term. Do not use the jargon term with an
explanation bolted on.**

He could not understand a summary written for him and named the cause: bare technical nouns and
invented hyphenated compounds that only made sense to their author. **If a technical term is
genuinely unavoidable, put a descriptive adjective before it and state the literal quantity being
computed.**

**Named as unintelligible when used bare:** arm, era, screen, separation, floor, capture, record,
direction — **and especially every hyphenated compound.** Specific phrases he flagged: "step-median
unit", "tile-level scoring", "standardised separation", "five-era window", "capture separation
floor", "full-record separation", "two-arm capture test".

Also: short sentences, colloquial English, and **define anything technical on first use in every
response**, not once per project.

## 2. The replacement table

**Measurement words.**

| Do not write | Write |
|---|---|
| separation, standardised separation | the gap between the two measured power levels, in units of their own scatter |
| capture, two-point capture, arm | the device's two measurements: brain signal power at a low stimulation current and at a high one |
| floor | minimum required value |
| era | the time block used for grouping — **and say which**: calendar month, or clinic visit |
| screen | the step that checks every candidate frequency band and reports which are usable |
| record, full record | all the data we have |
| direction | whether signal power rises or falls as stimulation current increases |
| slope | change in signal power per milliamp of current |
| span, ladder | the range of currents tested, lowest to highest, within one visit |
| tile | a 3-second chunk of recording |
| capture span | the number, and the range, of stimulation currents we tested |

**Statistics and system words.**

| Do not write | Write |
|---|---|
| cell | one combination of sensing contact, brain side and stimulation rate |
| cluster, cluster mass | a run of neighbouring frequency bands that all show the effect; its mass is their summed test statistic |
| family-wise p | p-value corrected for having tested many frequency bands |
| resolution floor | the smallest p-value the number of shuffles can produce |
| permutation, null | shuffling the data to see what happens by chance |
| era-blocked, adjusted | after statistically removing differences between time blocks |
| cluster-robust | standard errors allowing for repeated measurements within one group |
| anti-conservative | produces p-values that are too small |
| constant, literal | a fixed number written into the code |
| gate | a check that can refuse |
| deployable | allowed to drive closed-loop stimulation |
| frozen configuration | the stimulation rate and pulse width locked in before closed loop starts |

## 3. Two words with hard rules of their own

1. **"Threshold" is reserved for a device setting in a closed-loop configuration** — the value
   programmed into the stimulator at which it switches. **Never** use it for a statistical
   cut-off, a minimum required value, or an analysis criterion.
2. **Never say "the floor" for an effect size.** The quantity is an effect size. Say "the minimum
   effect size we require", or just "the effect size".

## 4. A claim and its result go in the same response

**Only make a comment or claim about a result if the same response also contains the result.**

This explicitly covers anticipatory phrasing. If you write any phrase asserting that you have
information or understanding — "two things stand out", "this is decisive", "something is off", "I
found it", "that resolves it", "worth stopping on" — **you must state the actual information, with
the numbers, in that sentence or the next one, before running any further tool call.** Never write
the announcement and then defer to a pending computation.

His words: *"you did that thing again, where u say something anticipatory, and then fail to
concisely say what the fuck it is. never do that."*

## 5. Prose constructions to avoid

He described a draft using these as reading *"as if two Claude and two AI wrote it"*:

1. colon-then-imperative-pair — "My innovation is a route around it: find the signal, then use it"
2. two- or three-word declarative fragments as topic sentences — "The discovery came first."
3. personified abstractions as sentence subjects — "The second innovation decides where to stimulate"
4. escalating tricolons — "real, decodable, and different in every person"
5. antithesis or chiasmus for closure — "my transition from doing the work to leading it"
6. formulaic pivot sentences — "The implications go beyond pain."
7. rhetorical closure of the form "the X they have always lacked"
8. participial flourishes appended to a clause — "opening the technology to symptoms it has never treated"

Also avoid: "what I did and did not do", "I will tell you plainly".

**Positively:** plain English, full explanatory sentences, the register of scientific writing.
Define the term, say what it does, say why it matters here. Bullet and numbered lists, with bold
for what is urgent.

## 6. Eight things that must never be claimed

Reproduced from `METHODS_measurement_and_findings.md` §7 because they are the scientific half of
these rules.

1. **Never conclude a band does not respond to stimulation from a narrow range of tested
   currents.** Testing currents that sit close together and seeing little movement supports only
   *"no movement was detectable across the currents we tested"*. **State the smallest movement the
   design could have detected, and the number and range of currents tested.** Where movement is
   small, quantify it with its uncertainty — effect size and confidence interval — rather than
   declaring the band flat.
2. **Never call a result established on one visit day.**
3. **Never present a figure that pools both stimulators' currents as evidence about one side.**
4. **Never quote a test-suite count without a traceable run behind it.**
5. **Never say an area under a curve is above chance by comparing it to zero.** The
   no-discrimination reference is 0.5.
6. **Never mix the two senses of "fold".** Fold error is a multiplicative factor, at least 1.0,
   computable on a single fit. Write "median fold error" in full.
7. **Never describe the composed conversion constant as measured.** Say composed, and name what it
   was composed from.
8. **A test whose name asserts something untrue is worse than no test.** When removing a
   calculation, split the test rather than relabelling its assertion.

## 7. One open question, asked three times and still unanswered

**Commit identity.** The project's session rules ask for commits under the principal investigator's
name and email. They have been made as a machine identity instead, on the reasoning that
attributing machine-written commits to a named researcher in the permanent record of a research
repository is his decision and not the agent's. Nothing already pushed has been rewritten.
**Ask once, then follow the answer consistently.**

Note also that the git configuration file is not writable in the sandbox this work was done in, so
identity has to be passed inline on each commit:

```
git -c user.name="..." -c user.email="..." commit -m "..."
```
