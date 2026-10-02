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
 *
 * Styled from the shared tokens (SPEC 2026-09-26, WP7): 12 px caption, the `ink3` grey (6.48:1 on
 * white), no side padding of its own, since every page now shows it inside a fold or the ⋯ menu.
 * The words are unchanged.
 */
import PropTypes from "prop-types";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import { T, TYPE } from "assets/theme/base/tokens";

function whenText(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function CacheStatusLine({ status, loading }) {
  // While the page loads, the fold holding this line said nothing (page review 2026-10-02, 4.7).
  if (!status && loading) {
    return (
      <MDBox pt={0.5} pb={1}>
        <MDTypography variant="caption" sx={{ ...TYPE.body, display: "block", color: T.ink3 }}>
          Reading stored results…
        </MDTypography>
      </MDBox>
    );
  }
  if (!status) return null;
  const when = whenText(status.last_built_utc);
  const head = status.exists && when
    ? `Stored results last built ${when}.`
    : "No stored results under the current key yet: this page was computed from the recordings for this request.";
  return (
    <MDBox pt={0.5} pb={1}>
      <MDTypography variant="caption" sx={{ ...TYPE.body, display: "block", color: T.ink3 }}>
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
  loading: PropTypes.bool,
};

CacheStatusLine.defaultProps = { status: null, loading: false };
