export const timelineViews = [
  {value: "combined", label: "Combined"},
  {value: "oura", label: "Oura only"},
  {value: "redcap", label: "REDCap only"},
  {value: "neural", label: "Neural only"},
];

export function channelsForView(timelines, view) {
  const channels = new Set();
  for (const series of timelines) {
    for (const channel of series.ChannelNames) {
      const source = channel.startsWith("[OURA] ") ? "oura"
        : channel.startsWith("[REDCap] ") ? "redcap"
        : series.SourceType === "neural" ? "neural" : "other";
      if (view === "combined" || source === view) channels.add(channel);
    }
  }
  return [...channels];
}

export function defaultViewChannels(timelines, view) {
  if (view === "combined") {
    return ["oura", "redcap", "neural"].flatMap(source => defaultViewChannels(timelines, source).slice(0, 1));
  }
  const options = channelsForView(timelines, view);
  const preferred = view === "oura"
    ? ["[OURA] DailyActivity Steps", "[OURA] Sleep TotalSleepDuration", "[OURA] Sleep AverageHRV"].filter(name => options.includes(name))
    : view === "neural" ? options.filter(name => name.endsWith(" LFP")).slice(0, 2)
    : options.filter(name => name.includes("Daily PRO") && / - (NRS \(0-10\)|VAS Pain Intensity \(0-100\)|Standard MPQ \(0-45\))$/.test(name));
  return preferred.length ? preferred : options.slice(0, 3);
}
