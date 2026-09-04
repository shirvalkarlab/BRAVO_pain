/**
 * Renders every rebuilt panel against the REAL /api/queryClosedLoopDeployment response for RCS08 and
 * asserts the behaviour that a patient's safety depends on.
 *
 * WHY A FIXTURE OF THE REAL RESPONSE RATHER THAN A HAND-WRITTEN ONE. The panels read about ninety
 * distinct payload fields between them, and a hand-written fixture only ever contains the fields
 * whoever wrote it remembered. The saved response is the response the server actually sent on
 * 2026-09-04, so a field that moves, is renamed, or stops being emitted shows up here as a failing
 * assertion or a thrown render rather than as an empty region on a clinician's screen.
 *
 * THE ASSERTIONS THAT MATTER MOST are the withholding ones. For this payload
 * `verdict_detail.device_eligible` is false, so no parameter value may appear anywhere until a
 * reader explicitly opens the planning view, and the read-back checkboxes must be disabled even
 * then. Those are the two properties that stop a number reaching a programmer during a visit, and
 * they are asserted against the live values rather than trusted to code review.
 */
// Imported here rather than through a `src/setupTests.js`, because this repository has no such file
// and adding one would change the test configuration for every suite in the application.
import "@testing-library/jest-dom";
import { render as rtlRender, screen, fireEvent } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import PAL from "./palette";
import DeviceRuleLedger from "./DeviceRuleLedger";
import EvidenceTrianglePanel from "./EvidenceTrianglePanel";
import PrescriptionPanel from "./PrescriptionPanel";
import DutyCyclePanel from "./DutyCyclePanel";
import WhatWouldChangeThis from "./WhatWouldChangeThis";
import payload from "./__fixtures__/rcs08_deployment_payload.json";

/**
 * The Material Dashboard primitives these panels are built from read two things out of React
 * context: the MUI theme (MDBox's styled root destructures `theme.functions`) and the platform
 * controller (MDTypography and MDButton read `darkMode` off it). Rendering a panel without both
 * throws inside the component library rather than in the panel, so every render in this file goes
 * through the same wrapper as the real application.
 */
// `initialStates` is the reducer's whole initial value in this application — the provider supplies
// no default — so it has to be passed or every MDTypography destructures `darkMode` off undefined.
// Only the key these panels reach is set.
const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>
      {ui}
    </PlatformContextProvider>
  </ThemeProvider>
);

function render(ui) {
  const utils = rtlRender(wrap(ui));
  // The rerender that Testing Library hands back replaces the WHOLE tree, so calling it with a bare
  // panel would drop the two providers and fail inside the component library. Re-wrapping keeps a
  // rerender equivalent to a prop change on a mounted page.
  return { ...utils, rerender: (next) => utils.rerender(wrap(next)) };
}

const report = { data: payload, loading: false, err: null };
const empty = { data: null, loading: false, err: null };

describe("the saved payload is the state these panels were built for", () => {
  it("still carries the shape the assertions below depend on", () => {
    expect(payload.available).toBe(true);
    expect(payload.verdict).toBe("blocked");
    expect(payload.verdict_detail.device_eligible).toBe(false);
    expect(payload.verdict_detail.all_edges_resolved).toBe(true);
    expect(payload.coherence.coherent).toBe(false);
    expect(payload.prescriptions.modes.dual.fields).toHaveLength(16);
    expect(payload.prescriptions.modes.single.fields).toHaveLength(14);
    expect(payload.prescriptions.modes.single_inverse.fields).toHaveLength(0);
  });
});

describe("the prescription panel withholds every value while the device refuses", () => {
  it("prints no parameter value and offers a planning view instead", () => {
    render(<PrescriptionPanel report={report} mode={null} onMode={() => {}} />);

    expect(screen.getByText(/16 PARAMETER VALUES WITHHELD/)).toBeInTheDocument();
    // The two transition durations are the largest transcription hazard in the table, so they are
    // the values checked for absence. Neither the raw milliseconds nor the minutes-and-seconds
    // gloss may be on screen while the values are withheld.
    expect(screen.queryByText(/150\u2009000/)).not.toBeInTheDocument();
    expect(screen.queryByText(/2 min 30 s/)).not.toBeInTheDocument();
    expect(screen.queryByText(/4096/)).not.toBeInTheDocument();
    // No read-back checkbox exists at all while the table is withheld.
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  it("watermarks the planning view and leaves every read-back box disabled", () => {
    render(<PrescriptionPanel report={report} mode={null} onMode={() => {}} />);
    fireEvent.click(screen.getByText(/Open a read-only planning view/));

    expect(screen.getByText(/PLANNING ONLY/)).toBeInTheDocument();
    expect(screen.getByText(/NOT AUTHORISED TO PROGRAM/)).toBeInTheDocument();

    const boxes = screen.getAllByRole("checkbox");
    expect(boxes).toHaveLength(16);
    expect(boxes.filter((b) => !b.disabled)).toHaveLength(0);
  });

  it("renders the minutes-and-seconds gloss beneath the value once the planning view is open", () => {
    render(<PrescriptionPanel report={report} mode={null} onMode={() => {}} />);
    fireEvent.click(screen.getByText(/Open a read-only planning view/));

    // Both durations arrive as milliseconds and the programmer displays minutes and seconds, so the
    // gloss is the safeguard against a two-order-of-magnitude entry error.
    expect(screen.getByText("enter as 2 min 30 s")).toBeInTheDocument();
    expect(screen.getByText("enter as 5 min 00 s")).toBeInTheDocument();
    // Testing Library normalises the DOM text before comparing but does NOT normalise the string
    // passed to the matcher, and this value is rendered with a thin space as its thousands
    // separator, so the query has to use the ordinary space that normalisation produces. The thin
    // space is deliberate in the component: a comma is a decimal separator in much of the world and
    // could be transcribed as one.
    expect(screen.getByText("150 000")).toBeInTheDocument();
  });

  it("leaves the Paused amplitude value blank, because that row's value is null on purpose", () => {
    render(<PrescriptionPanel report={report} mode={null} onMode={() => {}} />);
    fireEvent.click(screen.getByText(/Open a read-only planning view/));

    expect(screen.getByText("Paused amplitude")).toBeInTheDocument();
    expect(screen.getByText("to be chosen")).toBeInTheDocument();
    // The device fact sheet carries 2.5 mA for this participant's paused amplitude. It must not be
    // offered as a suggestion in a value column, because any number there gets typed.
    expect(screen.queryByText("2.50")).not.toBeInTheDocument();
  });

  it("carries the coupling banner with both fields, both values and the arithmetic", () => {
    render(<PrescriptionPanel report={report} mode={null} onMode={() => {}} />);
    fireEvent.click(screen.getByText(/Open a read-only planning view/));

    expect(screen.getByText(/Upper onset duration = 2000 ms/)).toBeInTheDocument();
    expect(screen.getByText(/Averaging duration = 4096 ms/)).toBeInTheDocument();
    expect(screen.getByText(/ceil\(2000 \/ 4096\) = 1 controller step/)).toBeInTheDocument();
    expect(screen.getByText(/NOT ESTABLISHED BY ANY SUPPLIED DOCUMENT/)).toBeInTheDocument();
  });

  it("re-renders a different field set per mode rather than swapping numbers", () => {
    const { rerender } = render(
      <PrescriptionPanel report={report} mode="dual" onMode={() => {}} />,
    );
    fireEvent.click(screen.getByText(/Open a read-only planning view/));
    expect(screen.getByText(/Dual Threshold: 16 fields/)).toBeInTheDocument();
    expect(screen.getByText("Upper onset duration")).toBeInTheDocument();

    rerender(<PrescriptionPanel report={report} mode="single" onMode={() => {}} />);
    // The planning view closes on a mode change, so its fourteen new values are withheld again
    // until the reader opens it deliberately for this mode.
    expect(screen.getByText(/14 PARAMETER VALUES WITHHELD/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Open a read-only planning view/));
    expect(screen.getByText(/Single Threshold: 14 fields/)).toBeInTheDocument();
    // The upper onset is a Dual Threshold field; in Single Threshold it must appear struck through
    // under the not-applicable heading rather than as a live row, and never simply be omitted.
    expect(screen.getByText(/NOT APPLICABLE IN SINGLE THRESHOLD/)).toBeInTheDocument();
    expect(screen.getByText("Upper onset duration (ms)")).toBeInTheDocument();
  });

  it("presents Single Threshold Inverse as unprogrammable rather than as an empty table", () => {
    render(<PrescriptionPanel report={report} mode="single_inverse" onMode={() => {}} />);

    expect(screen.getByText(/NOTHING TO TRANSCRIBE/)).toBeInTheDocument();
    // Matched once and only once: the note is the whole content of this branch, and rendering it
    // again lower down the card would read as two separate findings about the mode.
    expect(screen.getAllByText(/cannot drive therapy \(D18\)/)).toHaveLength(1);
    expect(screen.queryByText(/PARAMETER VALUES WITHHELD/)).not.toBeInTheDocument();
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  it("keeps the module's recommendation visible while a non-recommended mode is selected", () => {
    render(<PrescriptionPanel report={report} mode="single" onMode={() => {}} />);

    expect(screen.getByText(/THE MODULE RECOMMENDS DUAL THRESHOLD/)).toBeInTheDocument();
    expect(screen.getByText(/chronic pain varies over hours to days/)).toBeInTheDocument();
    expect(screen.getByText(/which is not the recommended mode/)).toBeInTheDocument();
  });
});

describe("the evidence panel separates the two coherence questions", () => {
  it("says the edges agree with each other AND do not match the control law", () => {
    render(<EvidenceTrianglePanel report={report} />);

    expect(screen.getByText(/Composing the amplitude-to-power and power-to-pain edges reproduces/))
      .toBeInTheDocument();
    expect(screen.getByText(/E1 and E2 have the opposite sign to the one the selected control law/))
      .toBeInTheDocument();
    expect(screen.getByText(/they are in conflict with what the device would do with them/))
      .toBeInTheDocument();
  });

  it("lights the NOT COHERENT cell and still draws the NOT ESTABLISHED cell", () => {
    render(<EvidenceTrianglePanel report={report} />);
    expect(screen.getByText("NOT COHERENT")).toBeInTheDocument();
    expect(screen.getByText("NOT ESTABLISHED")).toBeInTheDocument();
    expect(screen.getByText("COHERENT")).toBeInTheDocument();
  });

  it("prints each edge's own estimator sentence and no cluster-count asterisk", () => {
    const { container } = render(<EvidenceTrianglePanel report={report} />);
    expect(screen.getAllByText(/cluster-robust/).length).toBeGreaterThanOrEqual(3);
    expect(container.textContent).not.toMatch(/resolved\*/);
  });
});

describe("the duty cycle panel never reports a fraction of the day", () => {
  it("labels the fractions as fractions of the samples on record and shows the coverage", () => {
    const { container } = render(<DutyCyclePanel report={report} mode="dual" />);

    expect(container.textContent).toMatch(/fractions of the samples on record, not of the day/);
    expect(container.textContent).toMatch(/coverage of 0\.0124%/);
    // The one phrase that must never appear while fractions_are_of_observed_samples is true.
    expect(container.textContent).not.toMatch(/% of the day/);
    expect(container.textContent).not.toMatch(/percent of the day/);
  });

  it("says the amplitude question is unanswerable at this cadence rather than showing zeros", () => {
    const { container } = render(<DutyCyclePanel report={report} mode="dual" />);

    expect(screen.getByText(/Not answerable at this sampling cadence/)).toBeInTheDocument();
    expect(container.textContent).toMatch(/samples arrive every 230 s/);
    expect(container.textContent).toMatch(/transition up takes 150 s/);
  });

  it("carries every caveat the module attached, and the onset finding with its arithmetic", () => {
    const { container } = render(<DutyCyclePanel report={report} mode="dual" />);

    expect(screen.getByText(/ALL 5 CAVEATS THE MODULE ATTACHED/)).toBeInTheDocument();
    expect(screen.getByText(/THE ONSET DURATION IS INOPERATIVE/)).toBeInTheDocument();
    expect(container.textContent).toMatch(/upper onset spans 1 controller step/);
  });

  it("reports no duty cycle for the mode that cannot drive therapy", () => {
    const { container } = render(<DutyCyclePanel report={report} mode="single_inverse" />);
    expect(container.textContent)
      .toMatch(/No duty cycle is computed for Single Threshold Inverse/);
  });
});

describe("the rule ledger keeps the nine outcome kinds apart", () => {
  it("renders all four advisory kinds and pins the recorded values", () => {
    render(<DeviceRuleLedger report={report} />);

    expect(screen.getByText(/VIOLATED \u00B7 1/)).toBeInTheDocument();
    expect(screen.getByText(/CANNOT BE EVALUATED \u00B7 4/)).toBeInTheDocument();
    expect(screen.getByText(/DEFERRED TO ANOTHER RULE \u00B7 1/)).toBeInTheDocument();
    expect(screen.getByText(/ADVISORY SHORTFALLS \u00B7 2/)).toBeInTheDocument();
    // Both pinned values must be visible: the previous filter discarded them, and one of them
    // records the programming mode in force, which is what makes the workflow reachable at all.
    expect(screen.getByText(/PINNED VALUES \u00B7 2/)).toBeInTheDocument();
    expect(screen.getByText(/ADVISORY, COULD NOT BE DETERMINED \u00B7 9/)).toBeInTheDocument();
    expect(screen.getByText(/ADVISORY, NO MACHINE CHECK EXISTS \u00B7 13/)).toBeInTheDocument();
  });

  it("names a different actor for the clinician's rules and the data-wiring rules", () => {
    render(<DeviceRuleLedger report={report} />);

    // D31 is the only one of the four a clinician can clear where they are standing; D29, D30 and
    // D32 are unevaluable because their inputs were never routed into the module.
    expect(screen.getAllByText("CLINICIAN, AT THE A610")).toHaveLength(1);
    expect(screen.getAllByText("ANALYSIS — THE INPUTS ARE NOT WIRED UP")).toHaveLength(3);
  });
});

describe("the what-would-change band ranks the outstanding work and names its owner", () => {
  it("puts the violated rule first and separates device work from analysis work", () => {
    const { container } = render(<WhatWouldChangeThis report={report} />);

    expect(container.textContent).toMatch(/D19 is violated/);
    expect(container.textContent).toMatch(/1 of them can be resolved at the programmer/);
    expect(container.textContent).toMatch(/3 cannot be resolved there at all/);
    // The coherence row must name band selection rather than more measurement, because on this
    // payload the three edges agree with each other.
    expect(container.textContent)
      .toMatch(/BAND SELECTION — NOT MORE MEASUREMENT/);
  });
});

describe("every panel survives an absent report rather than throwing", () => {
  it("renders a withholding or not-evaluated state for each one", () => {
    [DeviceRuleLedger, EvidenceTrianglePanel, DutyCyclePanel, WhatWouldChangeThis]
      .forEach((Panel) => {
        const { container, unmount } = render(<Panel report={empty} />);
        expect(container.textContent.length).toBeGreaterThan(0);
        unmount();
      });
    const { container } = render(
      <PrescriptionPanel report={empty} mode={null} onMode={() => {}} />,
    );
    expect(container.textContent).toMatch(/No parameter table has been computed/);
  });
});

describe("the palette keeps its semantic roles distinct", () => {
  it("never pairs the pass role against a red fail role by hue alone", () => {
    // The decision axis is bluish-green against vermillion rather than green against red, which is
    // what lets a reader with deuteranopia separate a violated rule from a satisfied one.
    expect(PAL.pass).toBe("#009E73");
    expect(PAL.fail).toBe("#D55E00");
    expect(PAL.deferred).toBe("#CC79A7");
  });
});
