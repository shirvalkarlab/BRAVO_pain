/** Backend epoch seconds are authoritative; legacy naive timestamps represent UTC. */
export function pointTimeMs(point) {
  if (point && point.t_epoch != null && Number.isFinite(Number(point.t_epoch))) {
    return Number(point.t_epoch) * 1000;
  }
  const value = point && point.t;
  if (typeof value !== "string" || !value.trim()) return NaN;
  const iso = value.trim().replace(" ", "T");
  return Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`);
}

export function inActiveStage(ms, stages, active) {
  if (!Number.isFinite(ms)) return false;
  const owning = (stages || []).find((s) =>
    ms >= pointTimeMs({ t: s.start }) && ms < pointTimeMs({ t: s.end }));
  return !owning || !active || active.includes(owning.key);
}
