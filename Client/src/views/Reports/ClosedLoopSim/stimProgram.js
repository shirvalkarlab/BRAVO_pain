/**
 * The stimulation program on the Closed-Loop page (decision 467): its shape, its checks and what
 * travels to the server. The server's twin is `ClosedLoopDeployment/stim_program.py`; the problem
 * sentences are word for word the same (pinned by `stimProgram.test.js`).
 *
 * Contacts are numbered 0-3 on both sides, as the device writes them; the right lead's 8-11 is a
 * label (`shownContact`). A contact is -1 (negative), +1 (positive) or absent (off).
 */

export const SIDES = ["Left", "Right"];
export const LEVELS = [
  { level: 3, ids: ["3"] },
  { level: 2, ids: ["2a", "2b", "2c"] },
  { level: 1, ids: ["1a", "1b", "1c"] },
  { level: 0, ids: ["0"] },
];
const OFFSET = { Left: 0, Right: 8 };
const RING_WORDS = { ZERO: 0, ONE: 1, TWO: 2, THREE: 3 };

/** "2a" on the right lead reads "10a"; the case is "Case". */
export function shownContact(side, id) {
  if (id === "case") return "Case";
  return `${Number(id[0]) + (OFFSET[side] || 0)}${id.slice(1)}`;
}

export const ringOf = (id) => (/^\d/.test(String(id)) ? Number(String(id)[0]) : null);

/** Off -> negative -> positive -> off. */
export const nextSign = (v) => (v === -1 ? 1 : v === 1 ? 0 : -1);

/** Set one contact's sign, dropping it when off. */
export function withContact(sideProgram, id, sign) {
  const contacts = { ...((sideProgram && sideProgram.contacts) || {}) };
  if (sign === -1 || sign === 1) contacts[id] = sign; else delete contacts[id];
  return { ...(sideProgram || {}), contacts };
}

/** The sensing pair of a band's channel: "ZERO_THREE_LEFT" -> { side: "Left", pair: [0, 3] }. */
export function sensingPair(channel) {
  const words = String(channel || "").toUpperCase().split("_");
  const rings = words.filter((w) => w in RING_WORDS).map((w) => RING_WORDS[w]);
  const side = words.includes("LEFT") ? "Left" : words.includes("RIGHT") ? "Right" : null;
  if (rings.length !== 2 || !side) return null;
  return { side, pair: [Math.min(...rings), Math.max(...rings)] };
}

/** The program as the programmer writes it: "C+ 2a- 2b- 2c-" (positives first). */
export function contactsText(side, contacts) {
  const order = (a, b) => ((ringOf(a) ?? -1) - (ringOf(b) ?? -1)) || a.localeCompare(b);
  const ids = Object.keys(contacts || {});
  const name = (id) => (id === "case" ? "C" : shownContact(side, id));
  const pos = ids.filter((k) => contacts[k] === 1).sort(order).map((k) => `${name(k)}+`);
  const neg = ids.filter((k) => contacts[k] === -1).sort(order).map((k) => `${name(k)}−`);
  return [...pos, ...neg].join(" ");
}

/** The one sensing pair the device allows for these stimulating rings (`sensing_rule.flanking_pair`):
 *  [1, 3] for 2, [0, 2] for 1, [0, 3] for 1 and 2; null for 0 or 3 alone or a gap. */
export function flankingPair(rings) {
  const r = [...new Set(rings)].sort((a, b) => a - b);
  if (!r.length || r[r.length - 1] - r[0] !== r.length - 1) return null;
  const lo = r[0] - 1;
  const hi = r[r.length - 1] + 1;
  return lo >= 0 && hi <= 3 ? [lo, hi] : null;
}

/** What stops this side being programmed; [] when nothing does. The server's sentences. */
export function blockingProblems(sideProgram, pair, side = "Left") {
  const s = sideProgram || {};
  const c = s.contacts || {};
  const vals = Object.values(c);
  const out = [];
  if (!vals.includes(-1)) out.push("No negative contact: no stimulation on this side");
  if (!vals.includes(1)) out.push("No positive contact: make the case or a contact positive");
  if (pair) {
    // D52 (decision 217): the device senses only on the two contacts immediately flanking the
    // negative contacts, so the pair must be exactly that flanking pair.
    const [lo, hi] = pair;
    const rings = [...new Set(Object.keys(c).filter((k) => c[k] === -1).map(ringOf).filter((r) => r != null))];
    const fp = flankingPair(rings);
    if (rings.length && !(fp && fp[0] === lo && fp[1] === hi)) {
      const off = OFFSET[side] || 0;
      const need = [];
      for (let r = lo + 1; r < hi; r += 1) need.push(r + off);
      out.push(need.length
        ? `Sensing on ${lo + off}-${hi + off} needs stimulation on ${need.join(" and ")}: the device cannot sense`
        : `No stimulating contact lets the device sense on ${lo + off}-${hi + off}`);
    }
  }
  const num = (v) => (v == null || v === "" || !Number.isFinite(Number(v)) ? null : Number(v));
  const amp = num(s.amp_mA);
  const lo = num(s.lower_limit_mA);
  const hi = num(s.upper_limit_mA);
  if (lo != null && hi != null && lo > hi) out.push("Lowest current is above the highest");
  else if (amp != null && lo != null && hi != null && !(lo <= amp && amp <= hi)) {
    out.push("Amp is outside the lowest and highest current");
  }
  return out;
}

/** The program from /api/queryStimProgram's answer; null when the answer has none. */
export function fromServer(resp) {
  if (!resp || !resp.available) return null;
  const out = { rate_hz: resp.rate_hz };
  SIDES.forEach((side) => {
    const s = resp[side];
    if (!s) return;
    out[side] = {
      contacts: { ...(s.contacts || {}) }, amp_mA: s.amp_mA, pw_us: s.pw_us,
      lower_limit_mA: s.lower_limit_mA, upper_limit_mA: s.upper_limit_mA, target: s.target || null,
    };
  });
  return out;
}

const PROGRAM_KEYS = ["contacts", "amp_mA", "pw_us", "lower_limit_mA", "upper_limit_mA"];

/** What travels in the report request: numbers and contacts only (no target name). */
export function requestProgram(program) {
  if (!program) return null;
  const out = { rate_hz: program.rate_hz == null ? null : Number(program.rate_hz) };
  SIDES.forEach((side) => {
    const s = program[side];
    if (!s) return;
    out[side] = {};
    PROGRAM_KEYS.forEach((k) => {
      if (k === "contacts") {
        const c = s.contacts || {};   // sorted, so an edit that comes back to the same program compares equal
        out[side].contacts = Object.fromEntries(Object.keys(c).sort().map((id) => [id, c[id]]));
      }
      else out[side][k] = s[k] == null || s[k] === "" ? null : Number(s[k]);
    });
  });
  return out;
}

/** Whether the program differs from the device's (only an edited program is sent). */
export function isEdited(program, inherited) {
  if (!program) return false;
  if (!inherited) return true;
  return JSON.stringify(requestProgram(program)) !== JSON.stringify(requestProgram(inherited));
}
