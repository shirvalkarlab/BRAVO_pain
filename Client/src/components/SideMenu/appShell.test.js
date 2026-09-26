/**
 * The app shell (SPEC.md section 7, WP2, 2026-09-26): the sidebar, the top bar, cards, buttons,
 * tabs and tooltips follow the minimalist tokens. These tests read the style objects themselves,
 * so they check the values, not the look of a screenshot.
 */
import { createTheme } from "@mui/material/styles";

import { T, TYPE, SHADOW, contrastRatio, MIN_TEXT_PX } from "assets/theme/base/tokens";
import card from "assets/theme/components/card";
import buttonRoot from "assets/theme/components/button/root";
import contained from "assets/theme/components/button/contained";
import outlined from "assets/theme/components/button/outlined";
import buttonText from "assets/theme/components/button/text";
import tab from "assets/theme/components/tabs/tab";
import tooltip from "assets/theme/components/tooltip";
import sidenav from "assets/theme/components/sidenav";
import theme from "assets/theme";
import fs from "fs";
import path from "path";
import { dictionary } from "assets/translation";

import {
  collapseItem,
  collapseText,
  collapseIconBox,
} from "components/SideMenu/styles/sidenavCollapse";
import { navbar } from "components/Navbars/DashboardNavbar/styles";

const pxOf = (rem) => parseFloat(String(rem)) * 16;

describe("cards and bars carry no shadow", () => {
  test("a card is white with a 1 px rule border and no shadow", () => {
    const root = card.styleOverrides.root;
    expect(root.backgroundColor).toBe(T.surface);
    expect(root.border).toBe(`1px solid ${T.rule}`);
    expect(root.boxShadow).toBe(SHADOW.none);
  });

  test("the sidebar is white, flush and unshadowed", () => {
    const paper = sidenav.styleOverrides.paper;
    expect(paper.backgroundColor).toBe(T.surface);
    expect(paper.boxShadow).toBe(SHADOW.none);
    expect(paper.borderRadius).toBe(0);
  });

  test("the top bar has no shadow and no blur", () => {
    const style = navbar(theme, { transparentNavbar: false, absolute: false });
    expect(style.boxShadow).toBe(SHADOW.none);
    expect(style.backdropFilter).toBe("none");
    expect(style.backgroundColor).toBe(T.page);
  });
});

describe("buttons", () => {
  test("sentence case, weight 600, no letter-spacing", () => {
    expect(buttonRoot.textTransform).toBe("none");
    expect(buttonRoot.fontWeight).toBe(600);
    expect(buttonRoot.letterSpacing).toBe(0);
    expect(pxOf(buttonRoot.fontSize)).toBe(TYPE.body.fontSize);
  });

  test("the primary button is accent with white text, 36 px tall", () => {
    expect(contained.primary.backgroundColor).toBe(T.accent);
    expect(contained.primary.color).toBe(T.onFill);
    expect(pxOf(contained.base.minHeight)).toBe(36);
    expect(contrastRatio(contained.primary.color, contained.primary.backgroundColor)).toBeGreaterThanOrEqual(4.5);
  });

  test("secondary buttons are white with a 1 px caption-grey border", () => {
    expect(outlined.base.backgroundColor).toBe(T.surface);
    expect(outlined.base.borderColor).toBe(T.ink3);
    expect(contained.secondary.border).toBe(`1px solid ${T.ink3}`);
  });

  test("every button text colour is at least 4.5:1 on its fill", () => {
    const pairs = [
      [contained.base.color, contained.base.backgroundColor],
      [contained.secondary.color, contained.secondary.backgroundColor],
      [outlined.base.color, outlined.base.backgroundColor],
      [outlined.primary.color, outlined.primary.backgroundColor],
      [outlined.secondary.color, outlined.secondary.backgroundColor],
      [buttonText.base.color, T.surface],
      [buttonText.primary.color, T.surface],
      [buttonText.secondary.color, T.surface],
    ];
    pairs.forEach(([fg, bg]) => expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(4.5));
  });

  test("no button size draws text under the minimum", () => {
    [contained, outlined, buttonText].forEach((variant) => {
      ["small", "large"].forEach((size) => {
        expect(pxOf(variant[size].fontSize)).toBeGreaterThanOrEqual(MIN_TEXT_PX);
      });
    });
  });
});

describe("navigation items", () => {
  const th = createTheme(theme);

  test("the active item is accent on its tint, weight 600, with a left bar", () => {
    const item = collapseItem(th, { active: true });
    expect(item.color).toBe(T.accent);
    expect(item.background).toBe(T.accentTint);
    expect(item.borderLeft).toContain(T.accent);
    expect(collapseText(th, { active: true })["& span"].fontWeight).toBe(600);
    expect(contrastRatio(T.accent, T.accentTint)).toBeGreaterThanOrEqual(4.5);
  });

  test("an inactive item is body ink on white, 14 px", () => {
    const text = collapseText(th, { active: false })["& span"];
    expect(text.color).toBe(T.ink2);
    expect(pxOf(text.fontSize)).toBe(TYPE.body.fontSize);
    expect(collapseItem(th, { active: false }).background).toBe("transparent");
    expect(collapseIconBox(th, { active: false }).color).toBe(T.ink3);
  });
});

describe("tabs and tooltips", () => {
  test("the selected tab is accent and 600; tab text is sentence case", () => {
    const root = tab.styleOverrides.root;
    expect(root.textTransform).toBe("none");
    expect(root["&.Mui-selected"].color).toContain(T.accent);
    expect(root["&.Mui-selected"].fontWeight).toBe(600);
  });

  test("a tooltip is ink on white at 12 px, fully opaque, with the overlay shadow", () => {
    const tip = tooltip.styleOverrides.tooltip;
    expect(tip.backgroundColor).toBe(T.surface);
    expect(tip.color).toBe(T.ink);
    expect(tip.opacity).toBe(1);
    expect(tip.boxShadow).toBe(SHADOW.overlay);
    expect(pxOf(tip.fontSize)).toBe(TYPE.caption.fontSize);
  });
});

describe("navigation labels (SPEC.md section 6)", () => {
  // routes.js pulls in every page (Plotly among them), which cannot load under jest, so its
  // source is read as text: the name each page key is listed under.
  const src = fs.readFileSync(path.join(__dirname, "..", "..", "routes.js"), "utf8");
  const entry = (key) => {
    const at = src.indexOf(`key: "${key}"`);
    expect(at).toBeGreaterThan(-1);
    return src.slice(at, src.indexOf("}", at));
  };

  test("the three pain pages are named by the question each answers", () => {
    expect(entry("biomarkers")).toContain('name: "Which brain signal tracks pain"');
    expect(entry("stimOptimizer")).toContain('name: "Which current to try next"');
    expect(entry("closedLoopSim")).toContain('name: "Closed-loop settings to program"');
    ["Biomarker Exploration", "Open-Loop Stim Optimizer", "Closed-Loop Deployment"].forEach((old) => {
      expect(src).not.toContain(`name: "${old}"`);
    });
  });

  test("the group is 'Choosing stimulation settings', its key unchanged", () => {
    const group = src.slice(src.indexOf('"CustomizedAnalysis": {'));
    expect(group.slice(0, 200)).toContain('name: "Choosing stimulation settings"');
    expect(src).not.toContain('name: "Customized Analysis"');
  });

  test("the pages' routes and keys are unchanged", () => {
    expect(entry("biomarkers")).toContain('route: "/reports/biomarkers/:participant_uid"');
    expect(entry("stimOptimizer")).toContain('route: "/reports/stim-optimizer/:participant_uid"');
    expect(entry("closedLoopSim")).toContain('route: "/reports/closed-loop/:participant_uid"');
  });

  test("the breadcrumb reads the page's name, not its address", () => {
    expect(dictionary.Breadcrumbs.biomarkers.en).toBe("Which brain signal tracks pain");
    expect(dictionary.Breadcrumbs["stim-optimizer"].en).toBe("Which current to try next");
    expect(dictionary.Breadcrumbs["closed-loop"].en).toBe("Closed-loop settings to program");
  });
});
