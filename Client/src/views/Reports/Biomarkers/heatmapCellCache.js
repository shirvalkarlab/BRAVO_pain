/**
 * The scatter and violin data for a clicked heat-map square, kept for the whole browser session.
 *
 * WHY MODULE SCOPE. These used to sit in a `useRef` map inside the grid component. A ref lives and
 * dies with its component, and the component also emptied it whenever the shown grid object
 * changed, so a clicked square was fetched again after a switch to another pain score and back,
 * and after leaving the page and returning (the PI, 2026-10-02). Here the squares outlive the
 * component, like the grids themselves in `database/resultCache`.
 *
 * WHAT A SQUARE IS FILED UNDER: participant, pain score, the settings the shown grid was computed
 * under, and the square (channel, band centre, length of signal), joined by "|" (`cellKey`). No
 * pain rating is in a key or a value beyond what the server returned for that exact request.
 *
 * WHEN THEY ARE DROPPED: when that pain score's grid is rebuilt or dropped (any `invalidated` or
 * `stored` event on its slot), when everything is dropped, or when the server changed. At most
 * `MAX_CELLS` are kept; the least recently used goes first.
 */
import { subscribe } from "database/resultCache";

export const MAX_CELLS = 200;
const CELLS = new Map();          // insertion order = least recently used first

const SLOT_MARK = "/heatmapGrid/";

export function cellKey(uid, metric, shownKey, channel, center, seconds) {
  return [uid, metric, shownKey || "", channel, center, seconds].join("|");
}

export function getCell(key) {
  if (!CELLS.has(key)) return undefined;
  const v = CELLS.get(key);
  CELLS.delete(key); CELLS.set(key, v);           // touch
  return v;
}

export function putCell(key, cell) {
  CELLS.delete(key);
  CELLS.set(key, cell);
  while (CELLS.size > MAX_CELLS) CELLS.delete(CELLS.keys().next().value);
}

export function cellCount() { return CELLS.size; }
export function clearCells() { CELLS.clear(); }

function dropWhere(test) {
  Array.from(CELLS.keys()).forEach((k) => { if (test(k)) CELLS.delete(k); });
}

subscribe((ev) => {
  if (!ev) return;
  if (ev.type === "invalidatedAll" || ev.type === "serverChanged") { CELLS.clear(); return; }
  if ((ev.type === "invalidated" || ev.type === "stored") && typeof ev.module === "string") {
    const at = ev.module.indexOf(SLOT_MARK);
    if (at < 0) return;
    const prefix = `${ev.uid}|${ev.module.slice(at + SLOT_MARK.length)}|`;
    dropWhere((k) => k.startsWith(prefix));
  }
});
