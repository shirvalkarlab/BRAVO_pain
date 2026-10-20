/**
 * "Skip to content": the first element in the top bar (TASTE_AUDIT.md C7, 2026-09-26). It is
 * off screen until a keyboard reaches it, then shows at the top left; pressing it moves focus to
 * the page's main region (`#main-content`, DashboardLayout), past the menu and the top bar.
 * Focus is moved in code rather than by following "#main-content" as an address, so the router
 * never sees a changed URL.
 */
import MDBox from "components/MDBox";
import { T, TYPE, SPACE, RADIUS, WEIGHT, FOCUS_RING } from "assets/theme/base/tokens";
import { MAIN_CONTENT_ID } from "layouts/DatabaseLayout/DashboardLayout";

export { MAIN_CONTENT_ID };
export const SKIP_LINK_TEXT = "Skip to content";

export function focusMainContent(event) {
  const main = typeof document !== "undefined" ? document.getElementById(MAIN_CONTENT_ID) : null;
  if (!main) return;
  if (event) event.preventDefault();
  main.focus();
  if (typeof main.scrollIntoView === "function") main.scrollIntoView({ block: "start" });
}

export default function SkipToContent() {
  return (
    <MDBox
      component="a"
      href={`#${MAIN_CONTENT_ID}`}
      onClick={focusMainContent}
      data-skip-link="true"
      sx={{
        position: "absolute",
        left: SPACE.sm,
        top: SPACE.xs,
        zIndex: 2000,
        transform: "translateY(-200%)",
        background: T.surface,
        color: T.accent,
        border: `1px solid ${T.accent}`,
        borderRadius: `${RADIUS.sm}px`,
        padding: `${SPACE.xs}px ${SPACE.sm}px`,
        ...TYPE.body,
        fontWeight: WEIGHT.strong,
        textDecoration: "none",
        "&:focus, &:focus-visible": { transform: "none", ...FOCUS_RING },
      }}
    >
      {SKIP_LINK_TEXT}
    </MDBox>
  );
}
