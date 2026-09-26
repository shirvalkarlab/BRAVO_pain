/**
 * The real pixel width of a figure's container, so an SVG figure is drawn at that width rather
 * than scaled through a viewBox (SPEC.md section 3: 12 px text stays 12 px on screen). Returns
 * [ref, width]; the width never falls below `min`, and a narrower card scrolls the figure
 * sideways instead of shrinking it. Where nothing can be measured (a test, the first paint) the
 * fallback is used.
 */
import { useLayoutEffect, useRef, useState } from "react";

export default function useMeasuredWidth(fallback = 480, min = 320) {
  const ref = useRef(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const read = () => {
      const w = Math.floor(el.getBoundingClientRect().width || el.clientWidth || 0);
      if (w > 0) setWidth(Math.max(min, w));
    };
    read();
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, [min]);
  return [ref, width];
}
