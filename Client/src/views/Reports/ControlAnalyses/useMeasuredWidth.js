/**
 * The real pixel width of a figure's container, so an SVG figure is drawn at that width rather
 * than scaled through a viewBox (SPEC.md section 3: 12 px text must stay 12 px on screen).
 *
 * Returns [ref, width]. The width never falls below SVG_MIN_WIDTH_PX; a narrower card scrolls the
 * figure sideways instead of shrinking it. Where nothing can be measured (a test environment, or
 * before the first layout) the fallback width is used.
 */
import { useLayoutEffect, useRef, useState } from "react";

import { SVG_MIN_WIDTH_PX } from "views/Reports/figureStyle";

export const FALLBACK_WIDTH_PX = 640;

export default function useMeasuredWidth(fallback = FALLBACK_WIDTH_PX) {
  const ref = useRef(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const read = () => {
      const w = Math.floor(el.getBoundingClientRect().width || el.clientWidth || 0);
      if (w > 0) setWidth(Math.max(SVG_MIN_WIDTH_PX, w));
    };
    read();
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}
