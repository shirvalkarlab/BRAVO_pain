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
