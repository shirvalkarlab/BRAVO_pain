/**
 * The fonts, served from this application's own build instead of from Google (TASTE_AUDIT.md
 * C8; the PI's go-ahead of 2026-09-26). The pages no longer depend on a third-party server to
 * draw their text or their navigation icons: without it the icons printed their names ("menu",
 * "close") as text.
 *
 * IBM Plex Sans in the two weights the design uses, 400 and 600 (SPEC.md section 2.4), and the
 * two Material Icons variants the app uses (the round one is the theme's default icon class).
 * The build copies each font file these stylesheets name into its static folder. The icon
 * classes (`.material-icons`, `.material-icons-round`) are defined in `base/globals.js`, since
 * these packages ship only the font faces.
 *
 * Imported once, first, by `src/index.js`.
 */
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/material-icons/400.css";
import "@fontsource/material-icons-round/400.css";

/** The stylesheets above, for the test that checks each resolves and names real font files. */
export const FONT_STYLESHEETS = [
  "@fontsource/ibm-plex-sans/400.css",
  "@fontsource/ibm-plex-sans/600.css",
  "@fontsource/material-icons/400.css",
  "@fontsource/material-icons-round/400.css",
];
