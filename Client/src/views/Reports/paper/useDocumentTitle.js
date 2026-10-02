/**
 * Set the browser tab's title while a page is shown, and put the previous title back when it
 * goes (TASTE_AUDIT.md C7, 2026-09-26). A page calls it with its own question, so a reader with
 * several tabs open, or a screen reader announcing the tab, hears what the page answers:
 *
 *   useDocumentTitle("Brain signal vs. pain");
 *   // tab: "Brain signal vs. pain - UF/UCSF BRAVO"
 *
 * `PageHead` calls it with its title when the title is plain text, so a page built on
 * `PageHead` gets this without calling it. An empty title leaves the tab's title alone.
 */
import { useEffect } from "react";

export const APP_TITLE = "UF/UCSF BRAVO";

export function documentTitleFor(title) {
  const t = typeof title === "string" ? title.trim() : "";
  return t ? `${t} - ${APP_TITLE}` : null;
}

export default function useDocumentTitle(title) {
  const full = documentTitleFor(title);
  useEffect(() => {
    if (!full || typeof document === "undefined") return undefined;
    const previous = document.title;
    document.title = full;
    return () => {
      document.title = previous;
    };
  }, [full]);
}
