/**
 * The "Last computed" line under the matching controls (decision 438). Its counts add up every
 * contact pair, each matched on its own, so one rating counts once per pair it matched; the line
 * says so. The text above each scatter and violin is that pair's own.
 */
export default function lastComputedLine(stats) {
  if (!stats) return null;
  const nPairs = Object.keys(stats.per_channel || {}).length;
  const head = nPairs > 1
    ? `Last computed, summed over ${nPairs} contact pairs (a rating counts once per pair): `
    : `Last computed, for ${nPairs} contact pair: `;
  return `${head}${stats.n_pro_td || 0} ratings matched to TD, ${stats.n_pro_psd || 0} to a PSD`
    + `${stats.n_pro_unmatched != null ? `, ${stats.n_pro_unmatched} with nothing in the window` : ""}`
    + `${stats.n_td_used != null ? ` (${stats.n_td_used} 3 s TD pieces and ${stats.n_psd_used || 0} PSDs used).` : "."}`;
}
