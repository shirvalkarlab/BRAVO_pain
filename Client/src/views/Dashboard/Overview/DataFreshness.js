import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

const rows = [
  ["redcap", "Latest REDCap survey"],
  ["neural_json", "Percept JSON session"],
  ["neural_pdf", "Percept PDF session"],
  ["oura", "Latest Oura measurement"],
];

export function freshnessDate(entry) {
  if (!entry?.available || !["second", "minute"].includes(entry.precision)
      || typeof entry.value !== "string" || !/(Z|[+-]\d{2}:\d{2})$/.test(entry.value)) return null;
  const stamp = Date.parse(entry.value);
  if (!Number.isFinite(stamp) || stamp <= 0 || stamp > Date.now()) return null;
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles", weekday: "short", month: "short", day: "numeric",
    year: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZoneName: "short",
  }).format(new Date(stamp));
}

export default function DataFreshness({data, checking}) {
  return <MDBox component="section" aria-label="RCS08 data freshness" sx={{m: 1, minWidth: 0}}>
    <MDTypography variant="caption" fontWeight="bold" display="block">RCS08 · Latest source times</MDTypography>
    <MDTypography variant="caption" display="block" color="text">Pacific time · Recorded survey, session, and measurement times.</MDTypography>
    <MDBox component="dl" sx={{m: 0, mt: 1}}>
      {rows.map(([key, label]) => {
        const entry = data?.[key];
        const date = freshnessDate(entry);
        const detail = [entry?.reason, entry?.semantics, entry?.source].filter(Boolean).join(" ");
        return <MDBox component="div" key={key} data-freshness={key} sx={{mb: 1, overflowWrap: "anywhere"}}>
          <MDTypography component="dt" variant="caption" fontWeight="medium">{label}</MDTypography>
          <MDTypography component="dd" variant="caption" sx={{m: 0}}>
            {date || (checking && !data ? "Checking…" : "Unavailable")}
            {date && entry.partial ? " · Partial coverage" : ""}
          </MDTypography>
          {!date && entry?.reason ? <MDTypography variant="caption" display="block" color="text">{entry.reason}</MDTypography> : null}
          {detail ? <MDBox component="details" sx={{fontSize: "0.72rem", lineHeight: 1.4, color: "text.secondary"}}>
            <summary style={{cursor: "pointer"}}>Source details</summary>{detail}
          </MDBox> : null}
        </MDBox>;
      })}
    </MDBox>
    {checking && data ? <MDTypography variant="caption" display="block">Rechecking availability; showing the last successful check.</MDTypography> : null}
  </MDBox>;
}
