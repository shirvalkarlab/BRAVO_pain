/**
 * PAL.MODEBAR is the Plotly config every ROC curve, per-state refit, statistical-power figure,
 * simulation panel, three-source response and band-time sweep figure draws through. The
 * minimalist redesign of 2026-09-26 pointed it at `figureStyle.PLOTLY_CONFIG` (the toolbar off),
 * which took the save-as-PNG, zoom and pan toolbar off every one of those figures with no way for
 * a reviewer to get a figure out of the browser for the deployment record. The PI put it back the
 * same day (decisions 320-322 corrected): PAL.MODEBAR is the restored toolbar again.
 */
import PAL from "./palette";
import { PLOTLY_CONFIG_WITH_TOOLBAR } from "views/Reports/figureStyle";

describe("PAL.MODEBAR", () => {
  // the PI, 2026-09-26: toolbar restored so reviewers can save figures for the deployment record
  it("is the restored toolbar, not the off default", () => {
    expect(PAL.MODEBAR.displayModeBar).not.toBe(false);
    expect(PAL.MODEBAR).toBe(PLOTLY_CONFIG_WITH_TOOLBAR);
  });

  it("still turns the logo off and offers a PNG export", () => {
    expect(PAL.MODEBAR.displaylogo).toBe(false);
    expect(PAL.MODEBAR.toImageButtonOptions.format).toBe("png");
  });
});
