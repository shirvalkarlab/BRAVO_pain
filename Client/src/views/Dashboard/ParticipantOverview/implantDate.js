// A zero source timestamp is a missing implant date, not an implant in 1970.
// Keep the platform's existing date decoding for genuine recorded timestamps.
export function recordedImplantDate(timestamp, decodeTimestamp) {
  if (typeof timestamp !== "number" || !Number.isFinite(timestamp) || timestamp <= 0) return null;
  const date = new Date(decodeTimestamp(timestamp * 1000));
  return Number.isFinite(date.getTime()) ? date : null;
}
