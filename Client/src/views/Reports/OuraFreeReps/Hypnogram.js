// Adapted from meltforce/FreeReps Hypnogram.tsx and stageColors.ts (MIT).
// Copyright 2025–2026 meltforce. License: docs/third-party/FreeReps-LICENSE.txt.
// BRAVO: explicit session boundaries, exact widths, masked gaps, Oura Light label.
import { STAGES, COLORS, stageBlocks } from "./data";

export function localTime(time) {
  return new Date(time * 1000).toLocaleString("en-US", {
    timeZone: "America/Los_Angeles", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short",
  });
}

export default function Hypnogram({sleep}) {
  const blocks = stageBlocks(sleep.stages, sleep.start, sleep.end);
  return <div>
    <div style={{display: "flex", minHeight: 176}}>
      <div style={{width: 58, flex: "none"}}>{STAGES.map(stage =>
        <div key={stage} style={{height: 44, display: "flex", alignItems: "center", fontSize: 12}}>{stage}</div>)}</div>
      <div role="img" aria-label="Sleep stages through the night" style={{position: "relative", flex: 1, height: 176}}>
        {STAGES.map((stage, i) => <div key={stage} style={{position: "absolute", left: 0, right: 0, top: (i + 1) * 44 - 1, height: 1, background: "#e2e8eb"}} />)}
        {blocks.map((block, i) => <div key={i} title={`${block.stage}: ${localTime(block.start)} – ${localTime(block.end)}`}
          style={{position: "absolute", left: `${block.left}%`, width: `${block.width}%`, top: block.lane * 44 + 9, height: 26, background: COLORS[block.stage]}} />)}
      </div>
    </div>
    <div style={{display: "flex", justifyContent: "space-between", marginLeft: 58, fontSize: 12, marginTop: 8}}>
      <span>{localTime(sleep.start)}</span><span>{localTime(sleep.end)}</span>
    </div>
    {!blocks.length && <p>No eligible stage samples for this session.</p>}
    <p style={{fontSize: 12, marginTop: 12}}>Five-minute Oura stages. Gaps represent missing or excluded samples.</p>
  </div>;
}
