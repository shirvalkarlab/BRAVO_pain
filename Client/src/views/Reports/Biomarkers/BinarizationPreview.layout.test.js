import { render, screen, within } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { PlatformContextProvider } from "context";
import theme from "assets/theme";
import BinarizationPreview from "./BinarizationPreview";

jest.mock("plotly.js-dist", () => ({ react: jest.fn(), purge: jest.fn() }));

function Preview(props) { return <ThemeProvider theme={theme}><PlatformContextProvider initialStates={{darkMode:false}}><BinarizationPreview {...props} /></PlatformContextProvider></ThemeProvider>; }

function classCard(name) {
  return screen.getByRole("group", { name: "Binarization class counts" }).querySelectorAll(".MuiBox-root")[name === "Low" ? 0 : 1];
}

test("daily class summaries preserve day counts and unequal raw-report counts", () => {
  render(<Preview strategy="median" metricLabel="Pain" metricKey="pain" points={[
    {t:"2026-01-01T08:00:00",v:1}, {t:"2026-01-01T12:00:00",v:3},
    {t:"2026-01-02T08:00:00",v:2}, {t:"2026-01-03T08:00:00",v:8},
    {t:"2026-01-04T08:00:00",v:10},
  ]} />);
  expect(within(classCard("Low")).getByText("2 days")).toBeTruthy();
  expect(within(classCard("Low")).getByText("3 samples")).toBeTruthy();
  expect(within(classCard("High")).getByText("2 days")).toBeTruthy();
  expect(within(classCard("High")).getByText("2 samples")).toBeTruthy();
});

test("matched summaries distinguish unique pain ratings from matched neural samples", () => {
  render(<Preview strategy="median" metricLabel="Pain" metricKey="pain" points={[]} matchTolerance={30}
    scanModel={{matchedValues:[1,1,9], cuts:{kind:"one-cut",cut:5}, samples:[
      {bin:"low",proIdx:7}, {bin:"low",proIdx:7}, {bin:"high",proIdx:8},
    ], counts:{match_direction:"pro_first",n_low:2,n_high:1,n_matched:3,n_sessions:3,
      by_source:{low:{td:2},high:{event:1}},
    }}} />);
  expect(within(classCard("Low")).getByText("1 pain rating")).toBeTruthy();
  expect(within(classCard("Low")).getByText(/2 PSDs.*2 TD/)).toBeTruthy();
  expect(within(classCard("High")).getByText("1 pain rating")).toBeTruthy();
  expect(within(classCard("High")).getByText(/1 PSD.*1 event/)).toBeTruthy();
});

test('zero-match, unavailable index and missing pain inputs have distinct scientific explanations',()=>{
  const props={strategy:'median',points:[],metricKey:'pain',matchTolerance:15,setMatchTolerance:()=>{},scanModel:{matchable:true,matchedValues:[],counts:{n_sessions:7}}};
  const view=render(<Preview {...props}/>);
  expect(screen.getByText(/None of the 7 available/)).toBeTruthy();expect(screen.queryByText(/index for this participant has not been loaded/)).toBeNull();
  view.rerender(<Preview {...props} scanModel={{matchable:false,unmatchableReason:'no_pain_series',matchedValues:[]}}/>);
  expect(screen.getByText(/No pain reports are available for the selected metric/)).toBeTruthy();
  view.rerender(<Preview {...props} scanModel={{matchable:false,unmatchableReason:'no_scan_index',matchedValues:[]}}/>);
  expect(screen.getByText(/index for this participant has not been loaded/)).toBeTruthy();
  view.rerender(<Preview {...props} loading/>);expect(screen.getByText(/Loading neural-sample availability/)).toBeTruthy();
});


test("caption follows the selected score and distinguishes score-bearing from eligible reports", () => {
  const props = {strategy:"median",points:[{t:"2026-01-01T08:00:00",v:0}],totalReports:5};
  const view = render(<Preview {...props} metricLabel="Left Leg VAS" metricKey="left_leg_vas" />);
  expect(screen.getByText("1 Left Leg VAS reports across 1 days · 5 eligible dated reports in the record")).toBeTruthy();
  view.rerender(<Preview {...props} metricLabel="Back VAS" metricKey="back_vas" />);
  expect(screen.getByText(/1 Back VAS reports across/)).toBeTruthy();
  expect(screen.queryByText(/1 Left Leg VAS reports across/)).toBeNull();
});

test.each([null, 0, NaN, "5"])("caption omits an unavailable record count (%s)", (totalReports) => {
  render(<Preview strategy="median" metricKey="pain" totalReports={totalReports}
    points={[{t:"2026-01-01T08:00:00",v:4}]} />);
  expect(screen.getByText("1 pain reports across 1 days")).toBeTruthy();
  expect(screen.queryByText(/eligible dated reports in the record/)).toBeNull();
});

test.each(["pro_first", "nearest"])("matched caption retains the %s counting unit and names the score", (direction) => {
  render(<Preview strategy="median" metricLabel="Left Leg VAS" points={[]} matchTolerance={60} totalReports={9}
    scanModel={{matchedValues:[1,1,9],cuts:{kind:"one-cut",cut:5},samples:[
      {bin:"low",proIdx:7},{bin:"low",proIdx:7},{bin:"high",proIdx:8}],
      counts:{match_direction:direction,n_low:2,n_high:1,n_matched:3,n_sessions:4,
        survey_usage:{n_pro_used:2,n_pro_total:5,pct_pro_used:40}}}} />);
  expect(screen.getByText(direction === "pro_first"
    ? "2 of 5 Left Leg VAS reports paired with neural data at ±60 min (40%) · 9 eligible dated reports in the record"
    : "3 of 4 neural samples paired with a Left Leg VAS report at ±60 min · 9 eligible dated reports in the record")).toBeTruthy();
});
