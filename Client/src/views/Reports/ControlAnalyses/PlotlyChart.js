/**
 * One Plotly figure of the saved checks, drawn from a `{ data, layout }` spec (`plotSpecs.js`).
 *
 * WHEN IT DRAWS. The checks sit in a closed fold that stays mounted, and a Plotly graph first drawn
 * inside a hidden container measures itself at zero pixels wide. So nothing is drawn until the
 * enclosing fold has been opened once (`SectionRevealedContext`, which is true outside any fold);
 * after that the figure redraws in place when its spec changes. If the container still measures zero
 * when it is drawn (the fold was shut again before the figure arrived), a width observer redraws it
 * to its real width the moment it is shown.
 *
 * WHEN IT IS DESTROYED. Only when the component unmounts: an effect cleanup that purged on every
 * redraw would tear the graph down each time its spec changed, and a constant `uirevision` in every
 * spec keeps a reader's zoom through an in-place redraw.
 */
import React, { useContext, useEffect, useRef } from "react";
import PropTypes from "prop-types";
import Plotly from "plotly.js-dist";

import { PLOTLY_CONFIG, plotlyLayout } from "views/Reports/figureStyle";
import { SectionRevealedContext } from "views/Reports/paper/Section";

export default function PlotlyChart({ spec, height, label }) {
  const revealed = useContext(SectionRevealedContext);
  const ref = useRef(null);
  const drawn = useRef(null);      // the element a draw was started on, for the purge

  useEffect(() => {
    const el = ref.current;
    if (!revealed || !el || !spec) return;
    const layout = plotlyLayout({ ...spec.layout, height, autosize: true });
    // `drawn` is raised as the draw starts, so an unmount before it finishes still purges.
    drawn.current = el;
    Promise.resolve(Plotly.react(el, spec.data, layout, { ...PLOTLY_CONFIG, doubleClick: false }))
      .catch(() => {});
  }, [revealed, spec, height]);

  // Redraw at the real width the first time a hidden figure is shown.
  useEffect(() => {
    const el = ref.current;
    if (!revealed || !el || typeof ResizeObserver === "undefined") return undefined;
    let last = 0;
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth;
      if (w > 0 && last === 0 && drawn.current && Plotly.Plots && Plotly.Plots.resize) Plotly.Plots.resize(el);
      last = w;
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [revealed]);

  // Purge on unmount only.
  // (React has already cleared `ref` by then, so the element is the one remembered at draw time.)
  useEffect(() => () => {
    const el = drawn.current;
    if (el && Plotly.purge) { try { Plotly.purge(el); } catch (e) { /* already gone */ } }
  }, []);

  return (
    <div ref={ref} role="img" aria-label={label} data-testid="plotly-chart"
      style={{ width: "100%", minHeight: height }} />
  );
}

PlotlyChart.propTypes = {
  spec: PropTypes.shape({ data: PropTypes.array, layout: PropTypes.object }),
  height: PropTypes.number.isRequired,
  label: PropTypes.string.isRequired,
};
PlotlyChart.defaultProps = { spec: null };
