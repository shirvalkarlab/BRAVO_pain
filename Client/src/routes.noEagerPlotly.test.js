// The route table must not pull the experimental pages in eagerly. `views/Experimental/plugins`
// require()s every experimental page, and those import the Plotly helper, so a top-level import of
// it from routes.js puts all of Plotly (about 3.5 MB) into the main bundle that every page, the
// login page included, downloads and parses first (2026-10-01: main.*.js was 6.4 MB). The one real
// reader of `experimentalRoutes`, ParticipantOverview, is already lazy and keeps its own import.
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "routes.js"), "utf8");

test("routes.js does not import the experimental plugins eagerly", () => {
  const eager = src
    .split("\n")
    .filter((line) => /^\s*import\b/.test(line) && line.includes("views/Experimental/plugins"));
  expect(eager).toEqual([]);
});

// App.js imported the offline clinical report eagerly, and its CircadianDataDistribution figure
// imports Plotly, so Plotly stayed in the main bundle after the routes.js import went. The two survey
// pages carry the survey libraries; none of the three is the page a user lands on.
const app = fs.readFileSync(path.join(__dirname, "App.js"), "utf8");

test.each(["views/Offline_ClinicalReport", "views/Survey/Editor", "views/Survey/Viewer"])(
  "App.js loads %s lazily, not at start-up",
  (mod) => {
    const eager = app.split("\n").filter((l) => /^\s*import\b/.test(l) && l.includes(`"${mod}"`));
    expect(eager).toEqual([]);
    expect(app).toContain(`lazy(() => import("${mod}"))`);
  }
);

test("ParticipantOverview, the reader of the experimental routes, stays lazy", () => {
  expect(src).toMatch(/const ParticipantOverview = lazy\(\(\) => import\('views\/Dashboard\/ParticipantOverview'\)\);/);
});
