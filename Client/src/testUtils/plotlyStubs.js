/**
 * Stand-ins for the plotting libraries, for `jest.mock` factories (2026-10-05, when the page tests
 * were consolidated). A factory may not use names from the test file, so it requires these:
 *
 *   jest.mock("plotly.js-dist", () => require("testUtils/plotlyStubs").plotlyNoop());
 *   jest.mock("graphing-utility/Plotly", () => require("testUtils/plotlyStubs").renderManagerStub());
 *
 * Not a test file: jest collects only `*.test.js`.
 */

/** plotly.js-dist doing nothing: every drawing call returns at once. */
export const plotlyNoop = () => {
  const noop = () => {};
  return { react: () => Promise.resolve(), purge: noop, restyle: noop, relayout: noop, newPlot: noop };
};

/** The platform's PlotlyRenderManager doing nothing. */
export const renderManagerStub = () => ({
  PlotlyRenderManager: class {
    constructor() { this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setLayoutProps() {} setXlabel() {} setYlabel() {}
    addHeatmap() {} addScatter() {} addShape() {} addAnnotation() {} setTitle() {} purge() {}
  },
});

/**
 * plotly.js-dist that marks each drawn element as a drawn Plotly graph (the class and a measured
 * layout), for whole-page tests that wait on drawn figures. Plain functions, not jest.fn: the test
 * setup resets every jest.fn's behaviour before each test.
 */
export const plotlyMarking = () => {
  const mark = (gd) => {
    if (gd && gd.classList) { gd.classList.add("js-plotly-plot"); gd._fullLayout = { width: 700, height: 300 }; }
    return Promise.resolve(gd);
  };
  return {
    react: mark, newPlot: mark, purge: () => {}, restyle: () => Promise.resolve(),
    relayout: () => Promise.resolve(), toImage: () => Promise.resolve("data:image/png;base64,AAAA"),
  };
};
