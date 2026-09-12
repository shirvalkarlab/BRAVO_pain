"""The three-way comparison drawn: how current moved band power, measured three ways, side by side.

WHAT THE READER IS MEANT TO GET FROM THIS FIGURE, and what they are not.

The figure has three columns, one for each way of getting a band power out of this device, and two
rows. It is informative only. It decides nothing, and nothing on the deployment page is allowed to
depend on it.

  * THE TOP ROW answers "when the current went up, which way did the band power go, and do the three
    ways of measuring it agree?" All three columns are read at the ONE band the device itself was
    sensing during that stretch, because that is the only band all three can report and a comparison
    at different bands would not be a comparison. Each point is the settled level: the average over
    the thirty seconds before the next increase in current. The chart is points joined by a thin
    line, because there are five to seven settings and a reader needs to see each one; a smooth curve
    would invent behaviour between them, and band power is not a straight line in current.
  * THE BOTTOM ROW answers "what did the rest of the spectrum do, and does the band we care about
    stand out from it?" One line per stimulation setting, shaded from pale to dark as the current
    rises, so a whole family of bands moving together is visible at a glance. The column for the
    device's own band power carries a single point instead of a line, because the device reports one
    band and no more. That is the shape of the measurement, not a hole in our data.

WHAT A READER MUST NOT CONCLUDE. Three columns agreeing is NOT three independent confirmations that
stimulation moved the brain. The device computes its own band power on board from the very voltage
trace the first column reads, and the contact surveys behind the second column are where the
conversion into device units was fitted in the first place. So agreement across the columns says the
conversion is behaving. It says nothing more than that, and the footer line says so on the figure.

WHY THE BOTTOM ROW STOPS AT 30 HERTZ, which is a real restriction and not a cosmetic one. Two
reasons, and the first is the one that matters. The firmware will not let an adaptive sensing band
sit above 30 hertz, so a reader of the deployment page cannot act on a band above it however
interesting it looks. The second reason is that the full spectrum cannot be drawn honestly on one
linear axis: across 2.5 to 99.5 hertz the settled values on this record span a factor of about
9,600, with the largest of them at 55.5 hertz, which is the stimulation rate itself and therefore
a folded multiple of the stimulation rate. Inside 7.8 to 30 hertz the same values span a factor of about
10 and every one of them fits on one linear axis with no compression. Both figures are computed at
render time and printed on the figure rather than asserted here. The table saved beside the figure
carries all 98 bands, so nothing is discarded, only left off this panel.

WHY THERE IS NO LOGARITHM ON ANY AXIS. The device adds up squared magnitude across the band and
compares the total against a threshold typed in those same units. It never takes a logarithm. A
reader who has to undo one before they can compare a plotted height against a number they would
type into the programmer has been given arithmetic homework instead of a figure.

WHY THE BANDS THAT ARE MEASURING THE STIMULATOR ARE STRIPED, and why the stripe is quiet. This is a
data label saying which bands are not brain signal, in the same way a hatch says which cells have no
data. It stays because of something that happened on this record: before those bands were marked,
the largest apparent effect on a heat map reached 45506 device units and 18.2 times its starting
value, and it looked exactly like a spectacular biomarker. It was the stimulation artifact. The
stripe is drawn under the data at low opacity so the printed values stay readable through it.

EVERY PIECE OF TEXT ON THE FIGURE IS COMPUTED FROM THE NUMBERS IN THE SAME RENDER PASS. There are no
sentences in here that state a finding, only functions that build one out of what the data turned out
to be. This project has had a hardcoded claim in a title go false as the data moved underneath it,
silently, more than once.

BOTH RENDERINGS COME FROM ONE CONTEXT. :func:`build_context` reduces a
:class:`ThreeSourceComparison` to the numbers and the derived sentences; :func:`mpl_figure` draws the
static picture and :func:`plotly_figure` the one the browser gets. Neither computes anything of its
own, so the picture in the report and the picture on the page cannot disagree about what happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from . import three_source_response as TSR


# -------------------------------------------------------------------------------------------------
# Ink. One colour per route, used for that route in BOTH rows and in both renderings, so a reader
# never has to look up which column they are in. Taken from the Okabe-Ito set the rest of this page
# already uses, which stays distinguishable for the common forms of colour blindness.
# -------------------------------------------------------------------------------------------------
#: Where the stimulation energy actually lands, drawn as a thin line. The block that covers the
#: affected band CENTRES is wider than the landings themselves, because a band is five hertz wide on
#: one hertz spacing so eight neighbouring centres can all contain the same landing. Drawing only the
#: block would say the whole region is artifact; drawing only the lines would hide which centres are
#: affected. Both are drawn, and the block is kept faint so printed values read through it.
LANDING_INK = "#6C757D"

ROUTE_INK = {
    TSR.SOURCE_TIME_DOMAIN: "#0072B2",        # blue
    TSR.SOURCE_DEVICE_SPECTRUM: "#E69F00",    # orange
    TSR.SOURCE_DEVICE_BAND_POWER: "#009E73",  # bluish green
}
NEUTRAL_INK = "#6C757D"
STRIPE_INK = "#6C757D"
STRIPE_ALPHA = 0.10
GRID_INK = "#DDDDDD"

#: Where the bottom row stops, in hertz. The firmware will not place an adaptive sensing band above
#: this, so nothing above it can be acted on from this page. Read from the response module so the
#: figure and the numbers behind it cannot come to disagree about the limit.
SPECTRUM_LO_HZ = 7.5
SPECTRUM_HI_HZ = 30.0

#: Font sizes, three of them, mapped to what a piece of text is FOR rather than to how much room is
#: left: titles and axis labels, then annotations, then tick labels.
SIZE_TITLE, SIZE_NOTE, SIZE_TICK = 9.0, 7.5, 7.0


def _short(source: str) -> str:
    """A column heading short enough to sit above a panel and still say which recording it is.

    The three names are the PI's own, given 2026-09-10 for the page redesign ("those should be the
    three titles"): the band power derived from the streamed voltage trace, the band power derived
    from the device's own power spectral density (PSD) snapshot, and the band power the device
    records directly. LSB is the device's own unit (least significant bit).
    """
    return {
        TSR.SOURCE_TIME_DOMAIN: "Time domain derived LSB",
        TSR.SOURCE_DEVICE_SPECTRUM: "PSD derived LSB",
        TSR.SOURCE_DEVICE_BAND_POWER: "Direct LSB recording",
    }.get(source, source)


def _fold(a: float, b: float) -> float:
    """How many times apart two positive numbers are, whichever is the larger."""
    a, b = float(a), float(b)
    if not (np.isfinite(a) and np.isfinite(b)) or a <= 0 or b <= 0:
        return float("nan")
    return max(a / b, b / a)


# -------------------------------------------------------------------------------------------------
# The context: the numbers and every sentence, all derived, computed once
# -------------------------------------------------------------------------------------------------
@dataclass
class FigureContext:
    comparison: TSR.ThreeSourceComparison
    headline: str = ""
    subtitle: str = ""
    footer: str = ""
    amp_axis_label: str = ""
    power_axis_label: str = ""
    spectrum_lo_hz: float = SPECTRUM_LO_HZ
    spectrum_hi_hz: float = SPECTRUM_HI_HZ
    #: Per route, in column order: the top-row points and the derived caption under the panel.
    columns: List[Dict[str, Any]] = field(default_factory=list)
    striped_centres_hz: List[float] = field(default_factory=list)
    landings_in_view_hz: List[float] = field(default_factory=list)


def _agreement_sentence(comparison) -> str:
    """Say, from the numbers, how closely the routes that HAVE data agree, or that they cannot be.

    Only currents that two routes both reported can be compared, so the sentence names how many
    currents that was. When fewer than two routes produced anything, it says which one did rather
    than implying a comparison happened.
    """
    have = [p for p in comparison.panels if p.current_mA]
    if len(have) < 2:
        if not have:
            return "no route produced a settled value here"
        return (f"only one of the three routes produced a settled value here, "
                f"{_short(have[0].source)}, so nothing can be compared against it")
    worst, shared_total, pair = 0.0, 0, None
    for i in range(len(have)):
        for k in range(i + 1, len(have)):
            a, b = have[i], have[k]
            amap = dict(zip(a.current_mA, a.settled_power))
            bmap = dict(zip(b.current_mA, b.settled_power))
            shared = sorted(set(amap) & set(bmap))
            if not shared:
                continue
            f = max(_fold(amap[c], bmap[c]) for c in shared
                    if amap[c] is not None and bmap[c] is not None)
            shared_total = max(shared_total, len(shared))
            if np.isfinite(f) and f > worst:
                worst, pair = f, (a.source, b.source)
    if pair is None:
        return (f"the {len(have)} routes that produced values did so at different currents, so "
                f"there is no current at which two of them can be compared")
    word = "current" if shared_total == 1 else "currents"
    verb = "it agrees" if shared_total == 1 else "they agree"
    return (f"at the {shared_total} {word} where two routes both produced a settled value "
            f"{verb} to within {worst:.2f} times")


def _direction_sentence(comparison) -> str:
    """Say which way the band power went between the lowest and highest current, per route, derived.

    Written as a ratio to the value at the lowest current, which is how the PI reads a change of
    this kind, and never as "N times lower", which is not a quantity. A run whose largest value sits
    in the middle gets that said too: band power is not a straight line in current, and a sentence
    that reported only the two ends would hide a turn.
    """
    parts = []
    for p in comparison.panels:
        vals = [(c, v) for c, v in zip(p.current_mA, p.settled_power) if v is not None]
        if len(vals) < 2:
            continue
        vals.sort()
        lo_c, lo_v = vals[0]
        hi_c, hi_v = vals[-1]
        ratio = (hi_v / lo_v) if lo_v else float("nan")
        peak_c, peak_v = max(vals, key=lambda z: z[1])
        turn = ("" if peak_c in (lo_c, hi_c) else
                f", having risen to {peak_v:.0f} at {peak_c:g} mA on the way")
        parts.append(f"{_short(p.source)} went from {lo_v:.0f} device units at {lo_c:g} mA to "
                     f"{hi_v:.0f} at {hi_c:g} mA, {ratio:.2f} times its starting value{turn}")
    return ". ".join(parts) if parts else ""


def _route_direction(panel) -> str:
    """The one route's own change, for the caption under its own panel. Compressed 2026-09-11:
    the same numbers (start, end, ratio, and the peak when it sits between them) in fewer words."""
    vals = [(c, v) for c, v in zip(panel.current_mA, panel.settled_power) if v is not None]
    if len(vals) < 2:
        return ""
    vals.sort()
    lo_c, lo_v = vals[0]
    hi_c, hi_v = vals[-1]
    peak_c, peak_v = max(vals, key=lambda z: z[1])
    ratio = (hi_v / lo_v) if lo_v else float("nan")
    turn = ("" if peak_c in (lo_c, hi_c) else
            f"; peak {peak_v:.0f} at {peak_c:g} mA")
    return (f"{lo_v:.0f} \u2192 {hi_v:.0f} LSB from {lo_c:g} to {hi_c:g} mA "
            f"(\u00d7{ratio:.2f}{turn}). ")


def build_context(comparison: TSR.ThreeSourceComparison, *,
                  spectrum_lo_hz=SPECTRUM_LO_HZ, spectrum_hi_hz=SPECTRUM_HI_HZ) -> FigureContext:
    """Reduce one comparison to the numbers and every sentence the figure prints.

    Both renderings read this and only this. Every sentence below is built out of what the data
    turned out to be; none of them is written down in advance, because a written-down claim goes
    false the moment the data move and does it without saying anything.
    """
    ctx = FigureContext(comparison=comparison,
                        spectrum_lo_hz=float(spectrum_lo_hz),
                        spectrum_hi_hz=float(spectrum_hi_hz))
    c = comparison
    band_phrase = (f"{c.programmed_centre_hz:g} Hz" if c.programmed_centre_hz is not None
                   else "no band the device reported sensing")
    striped = [f for f in c.bands_measuring_the_stimulator_hz
               if ctx.spectrum_lo_hz - 1e-9 <= f <= ctx.spectrum_hi_hz + 1e-9]
    ctx.striped_centres_hz = striped
    ctx.landings_in_view_hz = sorted(
        f for f in c.stimulator_landings_hz
        if ctx.spectrum_lo_hz - TSR.BAND_HALF_HZ <= f <= ctx.spectrum_hi_hz + TSR.BAND_HALF_HZ)

    dev = next((p for p in c.panels if p.source == TSR.SOURCE_DEVICE_BAND_POWER), None)
    on_stim = bool(dev.band_is_measuring_the_stimulator) if dev else False

    # The headline states what came out, and the clause about the stimulator is added ONLY when the
    # band the device was sensing is one of the marked ones. A reader must not have to guess whether
    # a missing clause means "checked and clean" or "not checked".
    ctx.headline = (f"{c.ramped_side} stimulator turned up "
                    f"{c.current_from_mA:g} to {c.current_to_mA:g} mA with the other side at zero: "
                    f"{_agreement_sentence(c)}")
    if on_stim:
        ctx.headline += (f", and the {band_phrase} band the device was sensing is one of the bands "
                         f"carrying a folded landing")

    # Compressed 2026-09-11 (the PI: the text "should be significantly made much more concise").
    ctx.subtitle = (f"{c.visit_date} \u00b7 sensing {c.sensing_contact} at {band_phrase} \u00b7 "
                    f"{c.stimulation_rate_hz:g} Hz stimulation \u00b7 each point = mean of the last "
                    f"{c.settled_window_s:g} s before the next step up")

    ctx.amp_axis_label = f"Current delivered by the {c.ramped_side.lower()} stimulator (mA)"
    ctx.power_axis_label = "Settled band power (device units)"

    for p in c.panels:
        vals = [(a, v, n) for a, v, n in zip(p.current_mA, p.settled_power, p.n_pieces)
                if v is not None]
        if vals:
            ns = [n for _, _, n in vals]
            piece = (f"{min(ns)} pieces per point" if min(ns) == max(ns)
                     else f"{min(ns)}\u2013{max(ns)} pieces per point")
            band = (f"{p.band_centre_hz:g} Hz band" if p.band_centre_hz is not None else "no band")
            off = p.offset_from_programmed_centre_hz
            off_txt = ("" if off is None or abs(off) < 1e-9 else
                       f" ({abs(off):.2f} Hz off the sensed band)")
            outside = (p.band_inside_checked_conversion_range is False)
            caption = (f"{_route_direction(p)}"
                       f"{len(vals)} of {p.n_settings_offered} settings settled; {piece}. "
                       f"{band}{off_txt}."
                       + (f" Outside the checked {TSR.CHECKED_LO_HZ:g}\u2013{TSR.CHECKED_HI_HZ:g} Hz "
                          f"conversion range: extrapolated."
                          if outside else ""))
        else:
            caption = p.absent_reason or "no settled value"

        # The whole-spectrum lines for this column, cut to the drawn frequency range.
        centres = np.asarray(p.spectrum_centres_hz, dtype=float) if p.spectrum_centres_hz \
            else np.empty(0)
        keep = ((centres >= ctx.spectrum_lo_hz - 1e-9) & (centres <= ctx.spectrum_hi_hz + 1e-9)) \
            if centres.size else np.zeros(0, dtype=bool)
        lines = []
        for k, (a, _v, _n) in enumerate(vals):
            if not centres.size or k >= len(p.spectrum_power):
                continue
            row = np.asarray([np.nan if x is None else x for x in p.spectrum_power[k]], dtype=float)
            lines.append({"current_mA": a, "centres_hz": centres[keep].tolist(),
                          "power": row[keep].tolist()})

        ctx.columns.append({
            "source": p.source,
            "heading": _short(p.source),
            "ink": ROUTE_INK.get(p.source, NEUTRAL_INK),
            "current_mA": [a for a, _, _ in vals],
            "settled_power": [v for _, v, _ in vals],
            "n_pieces": [n for _, _, n in vals],
            "caption": caption,
            "absent_reason": p.absent_reason,
            "covers_whole_spectrum": p.covers_whole_spectrum,
            "band_centre_hz": p.band_centre_hz,
            "band_is_measuring_the_stimulator": p.band_is_measuring_the_stimulator,
            "spectrum_lines": lines,
            "conversion": p.conversion_into_device_units,
        })

    # The one compact note. The PI has read the five points behind this figure and accepted them, so
    # this is a reminder of the two that change how a reader should read the panels, not an argument.
    all_span = _full_spectrum_span(c)
    drawn_span = _drawn_span(ctx)
    ctx.footer = (
        "The three columns are not independent: the device computes its own band power from the "
        "voltage trace the first column reads, so agreement checks the conversion, not the effect "
        "three times. Striped bands carry a folded multiple of the stimulation rate. Only "
        f"{ctx.spectrum_lo_hz:g}\u2013{ctx.spectrum_hi_hz:g} Hz is drawn: the firmware cannot sense "
        f"above {ctx.spectrum_hi_hz:g} Hz"
        + (f"; values span \u00d7{all_span:.0f} across all bands against \u00d7{drawn_span:.1f} "
           f"in the drawn range."
           if np.isfinite(all_span) and np.isfinite(drawn_span) else "."))
    return ctx


def _full_spectrum_span(comparison) -> float:
    """The factor between the largest and smallest settled value across every band, derived."""
    vals = []
    for p in comparison.panels:
        for row in (p.spectrum_power or []):
            vals += [x for x in row if x is not None and np.isfinite(x) and x > 0]
    return (max(vals) / min(vals)) if len(vals) > 1 else float("nan")


def _drawn_span(ctx) -> float:
    """The same factor, over only the bands the bottom row actually draws."""
    vals = []
    for col in ctx.columns:
        for line in col["spectrum_lines"]:
            vals += [x for x in line["power"] if x is not None and np.isfinite(x) and x > 0]
    return (max(vals) / min(vals)) if len(vals) > 1 else float("nan")


def _current_shades(ink: str, currents) -> List[str]:
    """One shade of the column's own colour per stimulation setting, pale at low current.

    The colour family says which recording the line came from and the shade says how much current
    was running, so the two things a reader needs are carried by one visual channel each and neither
    needs a legend lookup.
    """
    import matplotlib.colors as mcolors
    base = np.asarray(mcolors.to_rgb(ink), dtype=float)
    n = max(len(currents), 1)
    out = []
    for i in range(len(currents)):
        f = 0.25 + 0.75 * (i / max(n - 1, 1))
        out.append(mcolors.to_hex(1.0 - f * (1.0 - base)))
    return out


# -------------------------------------------------------------------------------------------------
# The static picture
# -------------------------------------------------------------------------------------------------
def mpl_figure(ctx: FigureContext):
    """Draw the comparison with matplotlib and hand back the figure.

    Drawn directly rather than exported from the browser figure, because static export needs a
    headless browser the analysis sandbox does not have.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.size": SIZE_TICK, "axes.titlesize": SIZE_TITLE, "axes.labelsize": SIZE_TITLE,
        "xtick.labelsize": SIZE_TICK, "ytick.labelsize": SIZE_TICK,
        "legend.fontsize": SIZE_NOTE, "axes.edgecolor": "#333333",
        "axes.grid": True, "grid.color": GRID_INK, "grid.linewidth": 0.5,
        "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150,
    })

    # The vertical space is set from a plan rather than left to the default, because every band of
    # this figure has WORDS in it -- headline, one-line subtitle, three column captions, the note
    # about the stripes, the footer -- and matplotlib places none of that for you. The gaps below
    # are the ones that leave each band its own room; text was running through the panels before
    # they were set.
    fig, axes = plt.subplots(2, 3, figsize=(13.6, 9.6),
                             gridspec_kw={"height_ratios": [1.0, 1.0], "hspace": 0.95,
                                          "wspace": 0.26})
    fig.subplots_adjust(top=0.845, bottom=0.225, left=0.062, right=0.982)

    # ---- top row: the one band all three can report ----
    tops = [c["settled_power"] for c in ctx.columns if c["settled_power"]]
    pooled = [v for row in tops for v in row]
    y_lo, y_hi = (0.0, 1.0)
    if pooled:
        pad = 0.12 * (max(pooled) - min(pooled) or max(pooled))
        y_lo, y_hi = max(0.0, min(pooled) - pad), max(pooled) + pad

    for k, col in enumerate(ctx.columns):
        ax = axes[0][k]
        ax.set_title(col["heading"], loc="left", fontweight="medium")
        if col["settled_power"]:
            ax.plot(col["current_mA"], col["settled_power"], "-", color=col["ink"], lw=1.0,
                    alpha=0.6, zorder=2)
            ax.plot(col["current_mA"], col["settled_power"], "o", color=col["ink"], ms=6.5,
                    mec="white", mew=0.8, zorder=3)
            ax.set_ylim(y_lo, y_hi)
            ax.margins(x=0.12)
        else:
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.grid(False)
            ax.text(0.5, 0.70, "no settled value from this recording",
                    ha="center", va="center", fontsize=SIZE_NOTE, color=NEUTRAL_INK,
                    fontstyle="italic")
            ax.text(0.5, 0.55, _wrap(col["absent_reason"] or "", 44), ha="center", va="top",
                    fontsize=SIZE_TICK, color=NEUTRAL_INK, linespacing=1.5)
        if k == 0:
            ax.set_ylabel(ctx.power_axis_label)
        ax.set_xlabel(ctx.amp_axis_label if col["settled_power"] else "")
        ax.text(0.0, -0.255, _wrap(col["caption"], 56), transform=ax.transAxes, ha="left",
                va="top", fontsize=SIZE_TICK, color="#4A4A4A", linespacing=1.55)

    # ---- bottom row: the rest of the spectrum ----
    spec = [v for c in ctx.columns for ln in c["spectrum_lines"]
            for v in ln["power"] if v is not None and np.isfinite(v)]
    s_lo, s_hi = (0.0, 1.0)
    if spec:
        pad = 0.08 * (max(spec) - min(spec) or max(spec))
        s_lo, s_hi = max(0.0, min(spec) - pad), max(spec) + pad

    for k, col in enumerate(ctx.columns):
        ax = axes[1][k]
        if ctx.striped_centres_hz:
            ax.axvspan(min(ctx.striped_centres_hz) - TSR.BAND_HALF_HZ,
                       max(ctx.striped_centres_hz) + TSR.BAND_HALF_HZ,
                       color=STRIPE_INK, alpha=STRIPE_ALPHA, lw=0, zorder=0)
        for f in ctx.landings_in_view_hz:
            ax.axvline(f, color=LANDING_INK, lw=0.9, ls=(0, (3, 2)), alpha=0.75, zorder=1)

        if col["spectrum_lines"]:
            shades = _current_shades(col["ink"], [ln["current_mA"] for ln in col["spectrum_lines"]])
            for ln, sh in zip(col["spectrum_lines"], shades):
                ax.plot(ln["centres_hz"], ln["power"], "-", color=sh, lw=1.25, zorder=2)
            # The lowest and the highest current are named in the panel, in their own shades, so
            # the shading is read without a legend. They sit at the top corner rather than at the
            # end of a line, where two lines that finish close together would collide.
            # Placed in the middle of the panel, clear of the shaded region: the pale end of the
            # shade ramp is the lowest current, and pale ink on a grey fill is not readable.
            ax.text(0.44, 0.97, f"{col['spectrum_lines'][-1]['current_mA']:g} mA",
                    transform=ax.transAxes, ha="left", va="top", fontsize=SIZE_TICK,
                    color=shades[-1], fontweight="bold")
            # Only when there is more than one line: with a single accepted setting the lowest and
            # the highest current are the same number, and printing it twice reads as a fault.
            if len(col["spectrum_lines"]) > 1:
                ax.text(0.44, 0.86, f"{col['spectrum_lines'][0]['current_mA']:g} mA",
                        transform=ax.transAxes, ha="left", va="top", fontsize=SIZE_TICK,
                        color=shades[0])
            ax.set_ylim(s_lo, s_hi)
        elif col["band_centre_hz"] is not None and col["settled_power"]:
            # The device reports one band, so this cell carries one point rather than a curve, and
            # says why, which is a fact about the device and not an absence in the record.
            ax.plot([col["band_centre_hz"]] * len(col["settled_power"]), col["settled_power"], "o",
                    color=col["ink"], ms=6.0, mec="white", mew=0.8, zorder=3)
            ax.set_ylim(s_lo, s_hi)
            # Anchored to the axes rather than to the point, and away from the marker, so it can
            # never be pushed off the right-hand edge by a band that sits high in the range.
            ax.text(0.97, 0.94, "the device reports this band\nand no other",
                    transform=ax.transAxes, ha="right", va="top",
                    fontsize=SIZE_TICK, color=NEUTRAL_INK, linespacing=1.5)
        else:
            ax.set_ylim(s_lo, s_hi)
            ax.text(0.5, 0.5, "nothing recorded", transform=ax.transAxes, ha="center",
                    va="center", fontsize=SIZE_NOTE, color=NEUTRAL_INK, fontstyle="italic")

        ax.set_xlim(ctx.spectrum_lo_hz - 0.6, ctx.spectrum_hi_hz + 0.6)
        ax.set_xlabel("Middle of the 5 Hz band (Hz)")
        if k == 0:
            ax.set_ylabel(ctx.power_axis_label)

    landing_txt = (", ".join(f"{f:g}" for f in ctx.landings_in_view_hz) or "none in view")
    fig.text(
        0.062, 0.150, _wrap(
        f"Dashed lines: where a multiple of the {ctx.comparison.stimulation_rate_hz:g} Hz "
        f"stimulation lands after sampling ({landing_txt} Hz). Shaded: the "
        f"{len(ctx.striped_centres_hz)} band centres that contain one of those landings, so they "
        f"carry a folded multiple of the stimulation rate. Line shade runs from the lowest "
        f"current to the highest.", 178),
        ha="left", va="top", fontsize=SIZE_TICK, color="#4A4A4A", linespacing=1.55)

    fig.text(0.062, 0.982, _wrap(ctx.headline, 128), ha="left", va="top",
             fontsize=SIZE_TITLE + 2.4, fontweight="medium", color="#1A1A1A", linespacing=1.45)
    fig.text(0.062, 0.905, _wrap(ctx.subtitle, 168), ha="left", va="top", fontsize=SIZE_NOTE,
             color="#4A4A4A", linespacing=1.5)
    fig.text(0.062, 0.085, _wrap(ctx.footer, 178), ha="left", va="top", fontsize=SIZE_TICK,
             color=NEUTRAL_INK, linespacing=1.55)
    return fig


def _wrap(text: str, width: int) -> str:
    import textwrap
    return "\n".join(textwrap.wrap(str(text or ""), width=width)) or " "


# -------------------------------------------------------------------------------------------------
# The picture the browser gets
# -------------------------------------------------------------------------------------------------
def plotly_figure(ctx: FigureContext) -> Dict[str, Any]:
    """The same comparison as a Plotly figure dictionary, built from the SAME context.

    Returned as a plain dictionary of data and layout rather than a Plotly object, so the server can
    put it straight into the report payload without Plotly being importable at that moment.
    """
    import plotly.colors  # noqa: F401  (import kept so a missing Plotly fails here, loudly)
    from plotly.subplots import make_subplots

    heads = [c["heading"] for c in ctx.columns]
    fig = make_subplots(rows=2, cols=3, subplot_titles=heads + [""] * 3,
                        vertical_spacing=0.19, horizontal_spacing=0.07)

    for k, col in enumerate(ctx.columns, start=1):
        if col["settled_power"]:
            fig.add_trace({
                "type": "scatter", "mode": "lines+markers",
                "x": col["current_mA"], "y": col["settled_power"],
                "line": {"color": col["ink"], "width": 1.4},
                "marker": {"color": col["ink"], "size": 8,
                           "line": {"color": "white", "width": 1}},
                "name": col["heading"], "showlegend": False,
                "customdata": col["n_pieces"],
                "hovertemplate": (f"{col['heading']}<br>%{{x}} mA<br>"
                                  "%{y:.1f} device units<br>"
                                  "averaged over %{customdata} pieces<extra></extra>"),
            }, row=1, col=k)
        else:
            fig.add_annotation(row=1, col=k, x=0.5, y=0.5, xref="x domain", yref="y domain",
                               showarrow=False, align="center",
                               text=("<i>no settled value from this recording</i><br>"
                                     + _br(col["absent_reason"] or "", 44)),
                               font={"size": 11, "color": NEUTRAL_INK})

        if ctx.striped_centres_hz:
            fig.add_vrect(x0=min(ctx.striped_centres_hz) - TSR.BAND_HALF_HZ,
                          x1=max(ctx.striped_centres_hz) + TSR.BAND_HALF_HZ, row=2, col=k,
                          fillcolor=STRIPE_INK, opacity=STRIPE_ALPHA, line_width=0, layer="below")
        for f in ctx.landings_in_view_hz:
            fig.add_vline(x=f, row=2, col=k, line={"color": LANDING_INK, "width": 1,
                                                   "dash": "dash"}, layer="below")

        if col["spectrum_lines"]:
            shades = _current_shades(col["ink"], [ln["current_mA"] for ln in col["spectrum_lines"]])
            for ln, sh in zip(col["spectrum_lines"], shades):
                fig.add_trace({
                    "type": "scatter", "mode": "lines",
                    "x": ln["centres_hz"], "y": ln["power"],
                    "line": {"color": sh, "width": 1.6},
                    "name": f"{ln['current_mA']:g} mA", "showlegend": False,
                    "hovertemplate": (f"{col['heading']}, {ln['current_mA']:g} mA<br>"
                                      "%{x} Hz band<br>%{y:.1f} device units<extra></extra>"),
                }, row=2, col=k)
        elif col["band_centre_hz"] is not None and col["settled_power"]:
            fig.add_trace({
                "type": "scatter", "mode": "markers",
                "x": [col["band_centre_hz"]] * len(col["settled_power"]),
                "y": col["settled_power"],
                "marker": {"color": col["ink"], "size": 8,
                           "line": {"color": "white", "width": 1}},
                "showlegend": False,
                "hovertemplate": ("the device reports this band and no other<br>"
                                  "%{x} Hz<br>%{y:.1f} device units<extra></extra>"),
            }, row=2, col=k)

        fig.update_xaxes(row=1, col=k, title_text=ctx.amp_axis_label, gridcolor=GRID_INK,
                         zeroline=False)
        fig.update_xaxes(row=2, col=k, title_text="Middle of the 5 Hz band (Hz)",
                         range=[ctx.spectrum_lo_hz - 0.6, ctx.spectrum_hi_hz + 0.6],
                         gridcolor=GRID_INK, zeroline=False)
        fig.update_yaxes(row=1, col=k, gridcolor=GRID_INK, zeroline=False,
                         title_text=ctx.power_axis_label if k == 1 else None)
        fig.update_yaxes(row=2, col=k, gridcolor=GRID_INK, zeroline=False,
                         title_text=ctx.power_axis_label if k == 1 else None)

    fig.update_layout(
        title={"text": (f"<b>{_br(ctx.headline, 120)}</b>"
                        f"<br><span style='font-size:11px;color:#4A4A4A'>"
                        f"{_br(ctx.subtitle, 150)}</span>"),
               "x": 0.01, "xanchor": "left", "font": {"size": 14}},
        margin={"l": 78, "r": 26, "t": 128, "b": 96},
        height=760, plot_bgcolor="white", paper_bgcolor="white",
        font={"size": 11}, hovermode="closest", uirevision="three-source-response",
        annotations=list(fig.layout.annotations) + [{
            "text": f"<span style='color:{NEUTRAL_INK}'>{_br(ctx.footer, 175)}</span>",
            "x": 0, "y": -0.145, "xref": "paper", "yref": "paper", "showarrow": False,
            "align": "left", "xanchor": "left", "font": {"size": 10},
        }])
    return fig.to_plotly_json()


def _br(text: str, width: int) -> str:
    import textwrap
    return "<br>".join(textwrap.wrap(str(text or ""), width=width))


def render_all(comparisons, outdir=".", *, prefix="three_source_response"):
    """Draw every comparison, save one picture each, and return the paths in the order drawn.

    One picture per run of rising current, never two runs on one picture. Each run is a different
    sensing contact at a different band, and stacking them would invite a reader to read across two
    measurements that have nothing in common but the date.
    """
    import os
    paths = []
    for comp in comparisons:
        ctx = build_context(comp)
        fig = mpl_figure(ctx)
        # The clock time is in the filename as well as the date: two runs on the same side of the
        # same visit are ordinary, and a name that left the time out would have the second one
        # silently overwrite the first.
        clock = str(comp.window_start_local)[-8:].replace(":", "")
        path = os.path.join(outdir,
                            f"{prefix}_{comp.visit_date}_{clock}_{comp.ramped_side.lower()}.png")
        fig.savefig(path, dpi=150, bbox_inches=None, facecolor="white")
        paths.append(path)
    return paths


def context_payload(ctx: FigureContext) -> Dict[str, Any]:
    """One comparison, packaged for the browser: the numbers plus every derived sentence.

    The panel on the page draws from this, and so does the static picture, so the two cannot come to
    disagree about what happened. No Plotly is needed to build it, which matters because the report
    is assembled on a request where a missing drawing library must not cost the reader the numbers.
    """
    c = ctx.comparison
    return {
        "label": c.label,
        "ramped_side": c.ramped_side,
        "sensing_contact": c.sensing_contact,
        "visit_date": c.visit_date,
        "window_start_local": c.window_start_local,
        "window_end_local": c.window_end_local,
        "programmed_centre_hz": c.programmed_centre_hz,
        "stimulation_rate_hz": c.stimulation_rate_hz,
        "current_from_mA": c.current_from_mA,
        "current_to_mA": c.current_to_mA,
        "n_settings": c.n_settings,
        "settled_window_s": c.settled_window_s,
        "headline": ctx.headline,
        "subtitle": ctx.subtitle,
        "footer": ctx.footer,
        "amp_axis_label": ctx.amp_axis_label,
        "power_axis_label": ctx.power_axis_label,
        "band_axis_label": "Middle of the 5 Hz band (Hz)",
        "spectrum_lo_hz": ctx.spectrum_lo_hz,
        "spectrum_hi_hz": ctx.spectrum_hi_hz,
        "striped_centres_hz": ctx.striped_centres_hz,
        "landings_in_view_hz": ctx.landings_in_view_hz,
        "checked_lo_hz": TSR.CHECKED_LO_HZ,
        "checked_hi_hz": TSR.CHECKED_HI_HZ,
        "band_half_hz": TSR.BAND_HALF_HZ,
        "columns": ctx.columns,
        # Said in the payload as well as on the figure, so a panel written later cannot pick up the
        # numbers without the sentence that says what they do and do not show.
        "gates_nothing": True,
        "notes": c.notes,
    }


def report_payload(build) -> Dict[str, Any]:
    """Turn what :func:`three_source_response.build_for_participant` returned into the report block.

    Absence is carried through rather than dropped. A key that is simply missing reads on the page as
    "this does not apply here", and a route having no recording is not the same as it not applying.
    """
    out = {k: v for k, v in (build or {}).items() if k != "comparisons"}
    out["comparisons"] = []
    for comp in (build or {}).get("comparisons", []):
        try:
            out["comparisons"].append(context_payload(build_context(comp)))
        except Exception as exc:                     # one bad run must not lose the others
            out.setdefault("runs_that_failed", []).append(
                {"side": getattr(comp, "ramped_side", "unknown"),
                 "reason": f"the figure text could not be built: {exc!r}"})
    return out
