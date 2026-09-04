/**
 * Formatting and payload-reading helpers shared by every panel on the Closed-Loop Deployment page.
 *
 * Everything here is a pure function of the /api/queryClosedLoopDeployment payload. It lives in one
 * file for a specific reason: several of these rules exist to prevent a transcription error, and a
 * transcription rule that is re-implemented per panel will eventually be implemented two different
 * ways. The milliamp rule in particular (always two decimal places, leading and trailing zeros
 * forced) only works as a safeguard if every milliamp on the page obeys it, because its whole
 * purpose is that a reader can see at a glance that 1.40 and 14.00 are different lengths.
 */

const isNum = (v) => v != null && Number.isFinite(Number(v));

/**
 * Milliamps, always to two decimal places with the leading and trailing zeros forced.
 *
 * The forcing is the point. A clinician typing an amplitude into the A610 is entering a number into
 * a field whose own resolution is fine enough that a dropped digit is a programmable value: rule
 * D31 in this payload records the general Percept envelope as 0 to 25.5 mA in 0.1 mA steps or 0 to
 * 12.5 mA in 0.05 mA steps, citing A610-MD p. 119. A value printed as "1.4" therefore invites the
 * reading "14" on a hurried glance in a way that "1.40" does not, and 1.05 and 1.5 are both
 * enterable values that differ by one character when the trailing zero is dropped.
 * Two decimals also make every milliamp in a column exactly as wide as every other, so the
 * decimal points line up and a missing digit is visible as a ragged edge rather than having to be
 * noticed arithmetically.
 */
export function fmtMilliamps(v) {
  if (!isNum(v)) return null;
  return Number(v).toFixed(2);
}

/**
 * Milliseconds as an integer, with a thin space as the thousands separator.
 *
 * A thin space rather than a comma or a full space because the value is going to be read off this
 * page and typed somewhere else: a comma is a decimal separator in much of the world and could be
 * transcribed as one, whereas a thin space groups the digits without adding a character that has
 * any numeric meaning. No fractional part, because none of the device's duration fields is
 * documented as accepting one.
 */
export function fmtMilliseconds(v) {
  if (!isNum(v)) return null;
  return Math.round(Number(v)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, "\u2009");
}

/** Frequencies to one decimal place, which is the resolution the adaptive band is specified at. */
export function fmtHz(v) {
  return isNum(v) ? Number(v).toFixed(1) : null;
}

/**
 * Band-power thresholds to four decimal places.
 *
 * The module states explicitly that it does not round these values, because no Medtronic document
 * publishes a resolution grid for the LFP threshold fields, so there is no grid to round to. Four
 * decimal places is therefore a DISPLAY choice and not a claim about what the device accepts; the
 * prescription panel says so in one sentence beneath the table rather than repeating it per row.
 */
export function fmtPower(v) {
  return isNum(v) ? Number(v).toFixed(4) : null;
}

/** A p-value, in exponential form once it is small enough that decimal places stop being useful. */
export function fmtP(p) {
  if (!isNum(p)) return "not reported";
  const n = Number(p);
  return n < 0.001 ? n.toExponential(1) : n.toFixed(4);
}

/** A general-purpose number for readouts that carry no device-transcription risk. */
export function fmtNum(v, d = 3) {
  return isNum(v) ? Number(v).toFixed(d) : "not reported";
}

/**
 * A proportion rendered as a percentage. Callers on the duty-cycle panel must supply their own
 * wording for WHAT the percentage is a fraction of; this function deliberately returns only the
 * number and the per-cent sign, because the one error the duty panel exists to prevent is a
 * fraction of the recorded samples being read as a fraction of the day.
 */
export function fmtPct(v, d = 1) {
  return isNum(v) ? `${(Number(v) * 100).toFixed(d)}%` : "not reported";
}

/**
 * Choose the right formatter for a prescription row from the units the backend supplied.
 *
 * Dispatching on the payload's own `units` string rather than on the parameter name means a field
 * renamed upstream keeps its formatting, and a new field arrives formatted correctly without this
 * file being edited. Returns `null` for a value that is absent, so a caller can distinguish
 * "absent on purpose" from "formatted to an empty string".
 */
export function fmtFieldValue(field) {
  if (!field) return null;
  const v = field.value;
  if (v == null) return null;
  if (typeof v === "string") return v;
  const u = String(field.units || "").toLowerCase();
  if (u === "ma") return fmtMilliamps(v);
  if (u === "ms") return fmtMilliseconds(v);
  if (u === "hz") return fmtHz(v);
  if (u.indexOf("lfp") >= 0 || u === "lsb") return fmtPower(v);
  return isNum(v) ? String(Number(v)) : String(v);
}

/**
 * Read one bound of a confidence interval, distinguishing an ABSENT bound from a finite one.
 *
 * "The upper limit could be arbitrarily large" and "we failed to compute an upper limit" call for
 * different responses from a reader, and the previous version of this page rendered both as an
 * em-dash. Anything non-finite is reported here as unbounded, and the panels are required to print
 * the literal word rather than a dash or a bar clipped at the edge of an axis.
 */
export function ciBound(ci, i) {
  const raw = ci && ci.length > i ? ci[i] : null;
  return isNum(raw) ? { value: Number(raw), unbounded: false }
    : { value: null, unbounded: true };
}

/**
 * Extract the three edge signs from the coherence patterns.
 *
 * The backend serialises `expected_pattern` and `observed_pattern` as the repr of a Python
 * dictionary — for example `{'E1': -1, 'E2': 1, 'E3': -1, 'why': '...'}` — rather than as JSON, so
 * they cannot be parsed with JSON.parse: the keys and the nested prose are single-quoted, and the
 * `why` entry contains apostrophes of its own. Reading only the three signs with a narrow
 * expression is robust to all of that, and it fails to a null sign rather than throwing if the
 * serialisation changes shape again.
 *
 * UPDATE 2026-09-04: the backend now sends these as real JSON objects — the dataclass
 * fields were changed from `str` to `dict` and the stringifying `str(exp)` call removed —
 * so the object branch below is the live path. The repr-parsing branch is kept because a
 * cached response predating that change still parses rather than silently yielding three
 * absent signs, and its tests are kept for the same reason.
 */
export function parseSignPattern(raw) {
  const out = { E1: null, E2: null, E3: null };
  if (raw == null) return out;
  const s = typeof raw === "object" ? JSON.stringify(raw) : String(raw);
  ["E1", "E2", "E3"].forEach((k) => {
    const m = s.match(new RegExp(`["']?${k}["']?\\s*:\\s*(-?\\d+)`));
    if (m) out[k] = Number(m[1]);
  });
  return out;
}

/** "rises with" / "falls with" / "no established direction", for a sign spelled out in words. */
export function signPhrase(sign) {
  if (sign == null || Number(sign) === 0) return "no established direction";
  return Number(sign) > 0 ? "rises together" : "moves in opposite directions";
}

/** The bare sign as a word, used where the sentence supplies its own verb. */
export function signWord(sign) {
  if (sign == null || Number(sign) === 0) return "unsigned";
  return Number(sign) > 0 ? "positive" : "negative";
}

/**
 * Who has to act on a rule that could not be evaluated, keyed on the payload's own `kind`.
 *
 * This table replaces one hardcoded sentence that told the reader every unevaluable rule was a
 * value they had to read off the programmer. That was true of exactly one of RCS08's four
 * unevaluable rules. For the other three the module was never handed the fields the rule reads,
 * which is a defect in how the analysis is wired up and cannot be fixed at a programming visit, so
 * telling a clinician to go and read something off the device sends them to look for a value that
 * is not there.
 */
export const UNEVALUABLE = {
  value_not_read_off_programmer: {
    actor: "clinician, at the A610",
    copy: "the value exists only on the programmer and has not been read, so the rule cannot be "
        + "evaluated and it blocks",
  },
  input_not_supplied: {
    actor: "analysis — the inputs are not wired up",
    copy: "the input this rule reads was never routed into the module, so the rule cannot be "
        + "evaluated and it blocks. This cannot be resolved at the programmer",
  },
  predicate_error: {
    actor: "developer — defect in the rule table",
    copy: "this rule's check raised an error, which is a defect in the rule table rather than a "
        + "property of the configuration. It still blocks",
  },
  failed: {
    actor: "measurement — a property of the recording",
    copy: "the rule was evaluated against this configuration and the configuration violates it",
  },
};

/** Fall back to naming the kind rather than guessing an actor for a kind we have not seen. */
export function unevaluableFor(kind) {
  return UNEVALUABLE[kind] || {
    actor: `unclassified (kind: ${kind || "absent"})`,
    copy: "this rule reached the unevaluable bucket with a kind this interface does not recognise, "
        + "so no actor can be named for it",
  };
}

/** Human labels for the three threshold modes, used wherever a mode is named to a reader. */
export const MODE_LABEL = {
  dual: "Dual Threshold",
  single: "Single Threshold",
  single_inverse: "Single Threshold Inverse",
};

export const MODE_ORDER = ["dual", "single", "single_inverse"];
