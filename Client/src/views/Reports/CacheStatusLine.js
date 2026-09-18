/** Stored-input provenance from the existing canonical analysis response; never starts work. */
import PropTypes from "prop-types";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

export function cacheStatusText(status) {
  if (!status || typeof status !== "object") return null;
  const stamp = typeof status.last_built_utc === "string" ? Date.parse(status.last_built_utc) : NaN;
  if (status.exists === true) {
    const inputs = status.kind === "inputs";
    return Number.isFinite(stamp)
      ? `${inputs ? "Stored inputs last assembled" : "Stored results last built"} ${new Date(stamp).toUTCString()}.`
      : `${inputs ? "Stored inputs" : "Stored results"} are available; their build time is unavailable.`;
  }
  return "No stored entry or build time is available for the current inputs and settings.";
}

export default function CacheStatusLine({ status }) {
  const text = cacheStatusText(status);
  if (!text) return null;
  const meaning = typeof status.what_it_means === "string" ? status.what_it_means : "";
  return <MDBox px={2} py={1}>
    <MDTypography variant="caption" sx={{ display: "block", overflowWrap: "anywhere" }}>
      {text}{meaning ? ` Here that means ${meaning}.` : ""}
    </MDTypography>
  </MDBox>;
}

CacheStatusLine.propTypes = { status: PropTypes.object };
CacheStatusLine.defaultProps = { status: null };
