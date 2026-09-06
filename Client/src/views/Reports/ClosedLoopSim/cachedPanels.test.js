import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import ConversionModelPanel from "./ConversionModelPanel";
import DeploymentRocPanel from "./DeploymentRocPanel";
import EraRefitPanel from "./EraRefitPanel";
import LsbPowerPanel from "./LsbPowerPanel";
import PsdLsbPanel from "./PsdLsbPanel";

const mockUseCached = jest.fn();
const mockRecompute = jest.fn();
const mockQuery = jest.fn(); mockQuery.cancel = jest.fn();
jest.mock("database/useCachedResult", () => ({ useCachedResult: (options) => mockUseCached(options) }));
jest.mock("../Biomarkers/queryAnalysis", () => ({ useAnalysisQuery: () => mockQuery }));
jest.mock("views/Reports/moduleCacheKeys", () => ({ CL: { roc: "roc", era: "era", lsbPower: "lsb", psdLsb: "psd", conversionModel: "model" } }));
jest.mock("plotly.js-dist", () => ({ purge: jest.fn(), react: jest.fn() }));
jest.mock("@mui/material", () => ({ Card: ({ children }) => <div>{children}</div>,
  Grid: ({ children }) => <div>{children}</div>,
  ToggleButton: ({ children, onClick }) => <button onClick={onClick}>{children}</button>,
  ToggleButtonGroup: ({ children, onChange }) => <div>{require("react").Children.map(children,
    (child) => require("react").cloneElement(child, { onClick: () => onChange(null, child.props.value) }))}</div>, Slider: () => null }));
jest.mock("components/MDBox", () => ({ children }) => <div>{children}</div>);
jest.mock("components/MDTypography", () => ({ children }) => <div>{children}</div>);
jest.mock("components/MDButton", () => ({ children, disabled, onClick }) => <button disabled={disabled} onClick={onClick}>{children}</button>);

beforeEach(() => {
  mockQuery.mockReset(); mockRecompute.mockReset(); mockUseCached.mockReset();
  mockUseCached.mockReturnValue({ data: null, hasCached: false, loading: false, stale: false, recompute: mockRecompute });
});
test.each([ConversionModelPanel, DeploymentRocPanel, EraRefitPanel, LsbPowerPanel, PsdLsbPanel])(
  "%p mounts without analysis and exposes an explicit run control", (Panel) => {
    render(<Panel participantUid="synthetic" inputIdentity={{ fingerprint: "approved" }}
      bandCandidate={{ contact: "ONE_THREE_LEFT", center_freq_hz: 20, bandwidth_hz: 5 }}
      requestParams={{ MatchDirection: "prior" }} cutpoint={{ threshold: 3 }} />);
    expect(mockUseCached.mock.calls[0][0]).toMatchObject({ autoFetch: false, enabled: true,
      uid: "synthetic", identity: { fingerprint: "approved" } });
    expect(mockQuery).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Run this analysis" }));
    expect(mockRecompute).toHaveBeenCalledTimes(1);
  },
);

const band = { contact: "ONE_THREE_LEFT", center_freq_hz: 20, bandwidth_hz: 5 };
const rocData = { available: true, roc: { available: true, auc: 0.8,
  fpr: [0, 0.2, 1], tpr: [0, 0.8, 1], thr: [null, 3, 0], prevalence: 0.5 } };
const lsbData = { available: true, threshold_lsb: { available: true, upper_lsb: 42, estimated: false } };
const cacheState = (data, stale = false) => ({ data, stale, hasCached: true, loading: false, recompute: mockRecompute });

test("ROC retains its display but immediately clears downstream cutpoints for a changed band", () => {
  jest.useFakeTimers();
  const callback = jest.fn();
  mockUseCached.mockReturnValue(cacheState(rocData));
  const { rerender } = render(<DeploymentRocPanel participantUid="synthetic" bandCandidate={band} onCutpoint={callback} />);
  act(() => jest.advanceTimersByTime(250));
  expect(callback).toHaveBeenLastCalledWith(expect.objectContaining({ threshold: 3, matchDir: "prior" }));
  mockUseCached.mockReturnValue(cacheState(rocData, true));
  rerender(<DeploymentRocPanel participantUid="synthetic" bandCandidate={{ ...band, center_freq_hz: 30 }} onCutpoint={callback} />);
  expect(callback).toHaveBeenLastCalledWith(null);
  callback.mockClear();
  act(() => jest.advanceTimersByTime(500));
  expect(callback).not.toHaveBeenCalled();
  jest.useRealTimers();
});

test("changing ROC matching cancels a pending threshold and uses the current direction", () => {
  jest.useFakeTimers();
  const callback = jest.fn();
  mockUseCached.mockImplementation(({ settings }) => cacheState(rocData, settings.MatchDirection !== "prior"));
  render(<DeploymentRocPanel participantUid="synthetic" bandCandidate={band}
    requestParams={{ MatchDirection: "prior" }} onCutpoint={callback} />);
  fireEvent.click(screen.getByRole("button", { name: /Concurrent/i }));
  expect(mockUseCached.mock.calls.at(-1)[0].settings.MatchDirection).toBe("pro_first");
  expect(callback).toHaveBeenLastCalledWith(null);
  callback.mockClear();
  act(() => jest.advanceTimersByTime(500));
  expect(callback).not.toHaveBeenCalled();
  jest.useRealTimers();
});

test.each(["cutpoint", "band", "disabled"])("LSB clears downstream thresholds after %s changes while old data remains", (change) => {
  const callback = jest.fn();
  mockUseCached.mockReturnValue(cacheState(lsbData));
  const props = { participantUid: "synthetic", bandCandidate: band, cutpoint: { threshold: 3, matchDir: "prior" },
    requestParams: { Cutpoint: 99, MatchDirection: "pro_first" }, onLsbThreshold: callback };
  const { rerender } = render(<LsbPowerPanel {...props} />);
  expect(callback).toHaveBeenLastCalledWith({ upperLsb: 42, estimated: false });
  expect(mockUseCached.mock.calls.at(-1)[0].settings).toMatchObject({ Cutpoint: 3, MatchDirection: "prior" });
  mockUseCached.mockReturnValue(cacheState(lsbData, change !== "disabled"));
  const next = change === "cutpoint" ? { cutpoint: { threshold: 4, matchDir: "prior" } }
    : change === "band" ? { bandCandidate: { ...band, center_freq_hz: 30 } } : { cutpoint: null };
  rerender(<LsbPowerPanel {...props} {...next} />);
  expect(callback).toHaveBeenLastCalledWith(null);
});
