/**
 * The stability card names the contact pair as the rest of the page does (the PI, 2026-11-18,
 * from the rendered page: "15.5 Hz centre, 5.0 Hz wide, on ZERO_THREE_LEFT", the device's internal
 * code, where every other panel says "L 0⁻3⁺"). Its pain-score line stays: it is the score this
 * report read, which can differ from the page head's (painScore.test.js).
 */
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "assets/theme";
import { PlatformContextProvider } from "context";
import BandStabilityPanel from "./BandStabilityPanel";

jest.mock("plotly.js-dist", () => ({ react: jest.fn(), purge: jest.fn(), newPlot: jest.fn() }));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const text = (ui) => rtlRender(
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>,
).container.textContent;

const S = { answer: "behaves differently", test_ran: true, band_center_hz: 15.5, band_width_hz: 5,
  electrode: "ZERO_THREE_LEFT", odds_ratio_per_state: {} };

test("the contact pair is said as the page says it, not by the device's internal code", () => {
  const t = text(<BandStabilityPanel stability={S} painScore={{ key: "left_leg_vas", label: "Left Leg VAS" }}
    contactLabel={() => "L 0⁻3⁺"} />);
  expect(t).toMatch("15.5 Hz centre, 5.0 Hz wide, on L 0⁻3⁺");
  expect(t).not.toMatch("ZERO_THREE_LEFT");
  expect(t).toMatch("Pain score: Left Leg VAS.");
});

test("with no label function it still names the pair", () => {
  expect(text(<BandStabilityPanel stability={S} />)).toMatch("on ZERO_THREE_LEFT");
});
