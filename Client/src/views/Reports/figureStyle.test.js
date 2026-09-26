/**
 * The figure defaults every Plotly and SVG figure on the three pain pages starts from
 * (SPEC.md section 3): all text 12 px, the zoom toolbar off, no legend box, no gridlines.
 */
import {
  PLOTLY_LAYOUT, PLOTLY_CONFIG, SVG_TEXT, FONT_FAMILY, REF_LINE, CEILING_LINE, directLabel,
  plotlyLayout,
} from "views/Reports/figureStyle";
import { T, contrastRatio } from "assets/theme/base/tokens";

describe("figure defaults", () => {
  test("every default text size is 12 px", () => {
    expect(PLOTLY_LAYOUT.font.size).toBe(12);
    expect(PLOTLY_LAYOUT.hoverlabel.font.size).toBe(12);
    ["xaxis", "yaxis"].forEach((ax) => {
      expect(PLOTLY_LAYOUT[ax].tickfont.size).toBe(12);
      expect(PLOTLY_LAYOUT[ax].title.font.size).toBe(12);
    });
    expect(SVG_TEXT.fontSize).toBe(12);
    expect(directLabel(1, 2, "today").font.size).toBe(12);
  });

  test("the zoom toolbar and the logo are off", () => {
    expect(PLOTLY_CONFIG.displayModeBar).toBe(false);
    expect(PLOTLY_CONFIG.displaylogo).toBe(false);
  });

  test("no legend box and no gridlines", () => {
    expect(PLOTLY_LAYOUT.showlegend).toBe(false);
    expect(PLOTLY_LAYOUT.xaxis.showgrid).toBe(false);
    expect(PLOTLY_LAYOUT.yaxis.showgrid).toBe(false);
  });

  test("one typeface, and figure text inks are at least 4.5:1 on white", () => {
    expect(FONT_FAMILY).toMatch(/IBM Plex Sans/);
    [PLOTLY_LAYOUT.font.color, PLOTLY_LAYOUT.xaxis.tickfont.color, SVG_TEXT.fill]
      .forEach((c) => expect(contrastRatio(c, T.surface)).toBeGreaterThanOrEqual(4.5));
  });

  test("reference lines are grey and the safe ceiling line is red", () => {
    expect(REF_LINE.color).toBe(T.graphic);
    expect(CEILING_LINE.color).toBe(T.refused);
  });

  test("a figure's own settings merge over the defaults without losing them", () => {
    const l = plotlyLayout({ xaxis: { title: { text: "Current (mA)" } }, yaxis2: { overlaying: "y" } });
    expect(l.xaxis.title.text).toBe("Current (mA)");
    expect(l.xaxis.title.font.size).toBe(12);
    expect(l.xaxis.tickfont.size).toBe(12);
    expect(l.yaxis2.tickfont.size).toBe(12);
    expect(l.yaxis2.overlaying).toBe("y");
    expect(PLOTLY_LAYOUT.xaxis.title.text).toBeUndefined();
  });
});
