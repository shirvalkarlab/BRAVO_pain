/**
 * One line under a page's recompute control saying when the stored results this page reads were
 * last built, or that there are none yet. Track C step 4.
 *
 * The date comes from the server's own stamp inside the stored entry (`cache_status` in every
 * module's payload), never from a file timestamp, and the sentence beside it says what the date
 * means for THIS page, because "last built" means different things on the three pages: the
 * band-power tiles on the biomarker page, the assembled recordings and settings on the
 * closed-loop page, the whole stored response on the optimizer page. A page with no stored entry
 * says so in words rather than showing nothing, so a page computed from the recordings just now
 * and a page served from a file built weeks ago are distinguishable at a glance.
 */
import PropTypes from "prop-types";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

function whenText(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function CacheStatusLine({ status }) {
  if (!status) return null;
  const when = whenText(status.last_built_utc);
  const head = status.exists && when
    ? `Stored results last built ${when}.`
    : "No stored results under the current key yet: this page was computed from the recordings for this request.";
  return (
    <MDBox px={2} pt={0.5} pb={1}>
      <MDTypography variant="caption" sx={{ display: "block", fontSize: 11.5, color: "#4A4A4A" }}>
        {head} {status.what_it_means ? `Here that means ${status.what_it_means}.` : ""}
        {status.note && !(status.exists && when) ? ` (${status.note})` : ""}
      </MDTypography>
    </MDBox>
  );
}

CacheStatusLine.propTypes = {
  status: PropTypes.shape({
    exists: PropTypes.bool,
    last_built_utc: PropTypes.string,
    what_it_means: PropTypes.string,
    note: PropTypes.string,
  }),
};

CacheStatusLine.defaultProps = { status: null };
