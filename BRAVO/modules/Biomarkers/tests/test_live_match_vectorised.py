"""The padded collapse in `live_lsb_spectrum_match` equals a per-pain-report loop, exactly.

`live_lsb_spectrum_match` used to walk the pain reports one at a time, taking a small
nan-median over each report's own selected pieces of recording. It now pads every report's
selection into one (reports x pieces x bands) block and collapses it with a SINGLE
`np.nanmedian`. These tests hold the new code against a deliberately slow reference written the
old way -- an explicit Python loop, brute-force nearest-report search, and `statistics.median`
rather than numpy -- so the reference shares no machinery with the code under test.

The constructed recordings below deliberately contain, all at once:
  * a pain report whose selection is EMPTY (every nearby piece failed the quality gate), which
    must stay unmatched rather than becoming a matched report with no values;
  * a pain report whose selection is entirely NaN (pieces passed the gate but carry no band
    values), which must stay MATCHED with every band reading None;
  * an EVEN number of selected pieces, where the median averages the middle two and is therefore
    sensitive to which pieces were selected;
  * a pain report exactly midway between two pieces, and two pieces exactly equidistant from one
    report, so both tie-break rules are exercised.
"""
import statistics

import numpy as np

from ..routines import availability as av
from ..routines import analytics

CENTERS = [4.9, 8.8, 12.7, 16.6, 20.5, 24.4]
TILE_S = 3.0
T0 = 1_700_000_000.0


# ---------------------------------------------------------------------------------------------
# the reference: how the function used to work, written out longhand
# ---------------------------------------------------------------------------------------------
def _reference(pro, cache, *, tol_s, quantity_s, reuse):
    """One pain report at a time, brute-force, `statistics.median`. Returns a list of dicts."""
    centers = [float(c) for c in cache["centers_hz"]]
    nC = len(centers)
    window_s = float(cache["window_s"])
    cap = max(1, int(round(quantity_s / window_s)))
    lo, hi = float(analytics.LSB_VALIDATED_HZ_LO), float(analytics.LSB_DEPLOYABLE_HZ_HI)
    cal_band = [(lo - 1e-9) <= c <= (hi + 1e-9) for c in centers]
    pro = [float(x) for x in pro]

    def owners(win_t, valid):
        """Each eligible piece -> its single nearest pain report. Ties go to the report that is
        earlier in time, and among identical times to the one listed first."""
        rank = sorted(range(len(pro)), key=lambda i: (pro[i], i))
        out = []
        for k, t in enumerate(win_t):
            if not valid[k]:
                out.append(-1); continue
            best, best_key = -1, None
            for slot, i in enumerate(rank):
                key = (abs(t - pro[i]), slot)
                if best_key is None or key < best_key:
                    best, best_key = i, key
            out.append(best if best_key[0] <= tol_s else -1)
        return out

    def select(win_t, valid, p):
        if reuse:
            return [k for k, t in enumerate(win_t)
                    if valid[k] and abs(t - pro[p]) <= tol_s]
        own = owners(win_t, valid)
        return [k for k, o in enumerate(own) if o == p]

    def med_over(rows, sel):
        """Per-band median of the finite values among the selected pieces."""
        out = []
        for j in range(nC):
            vals = [rows[k][j] for k in sel if rows[k][j] is not None]
            out.append(statistics.median(vals) if vals else None)
        return out

    td, psd = cache["td"], cache["psd"]
    td_t, psd_t = [float(x) for x in td["t"]], [float(x) for x in psd["t"]]
    td_valid = [bool(o) and np.isfinite(t) for o, t in zip(td["ok"], td_t)]
    psd_valid = [bool(np.isfinite(t)) for t in psd_t]

    recs = []
    for p in range(len(pro)):
        rec = {"t": pro[p], "tier": None, "lsb": [None] * nC, "calibrated": [False] * nC,
               "center_hz": list(centers), "used_s": 0.0, "saturated": False, "reason": "",
               "n_td_used": 0, "n_psd_used": 0}
        sel = select(td_t, td_valid, p)
        if sel:
            n_elig = len(sel)
            if n_elig > cap:                       # keep the cap pieces closest in time
                keep = sorted(sorted(sel, key=lambda k: (abs(td_t[k] - pro[p]), sel.index(k)))[:cap],
                              key=sel.index)
                sel = keep
            rec["tier"] = "td_transform"
            rec["lsb"] = med_over(td["lsb"], sel)
            rec["calibrated"] = [v is not None for v in rec["lsb"]]
            rec["n_td_used"] = len(sel)
            rec["used_s"] = float(len(sel) * window_s)
            rec["reason"] = ("live TD->LSB median over nearest %d of %d eligible tile(s) "
                             "(<=%.0fs signal within +/-%.0fs tol, k=%.2f)"
                             % (len(sel), n_elig, quantity_s, tol_s,
                                analytics.LSB_PER_UV2_TRANSFORM))
            recs.append(rec); continue
        sel = select(psd_t, psd_valid, p)
        if sel:
            rec["tier"] = "psd_bridge"
            rec["lsb"] = med_over(psd["lsb"], sel)
            rec["calibrated"] = [v is not None and cal_band[j]
                                 for j, v in enumerate(rec["lsb"])]
            rec["n_psd_used"] = len(sel)
            rec["reason"] = ("live PSD->LSB median over %d event(s) within +/-%.0fs (k=%.2f); "
                             "calibrated only in [%.1f,%.1f] Hz"
                             % (len(sel), tol_s, analytics.LSB_PER_DEVICE_PSD, lo, hi))
        recs.append(rec)
    return recs


# ---------------------------------------------------------------------------------------------
# the constructed recordings
# ---------------------------------------------------------------------------------------------
def _row(seed, nC=len(CENTERS), holes=()):
    rng = np.random.default_rng(seed)
    row = [float(v) for v in rng.uniform(100.0, 2000.0, size=nC)]
    for j in holes:
        row[j] = None
    return row


def _cache():
    """Eleven pieces of recording and four device-spectrum windows, laid out so that every branch
    named in this module's docstring is reached by at least one pain report."""
    nC = len(CENTERS)
    td_t, td_lsb, td_ok = [], [], []

    def add(t, row, ok):
        td_t.append(float(t)); td_lsb.append(row); td_ok.append(bool(ok))

    # pieces 0-5: six good pieces on a 3 s grid -> an EVEN selection when all six are kept
    for k in range(6):
        add(T0 + 1.5 + 3.0 * k, _row(10 + k, nC, holes=(k % nC,) if k in (2, 4) else ()), True)
    # pieces 6-7: pass the quality gate but hold no band values at all -> all-NaN selection
    add(T0 + 500.0, [None] * nC, True)
    add(T0 + 503.0, [None] * nC, True)
    # pieces 8-9: real values but FAILED the quality gate -> never eligible -> empty selection
    add(T0 + 1000.0, _row(30, nC), False)
    add(T0 + 1003.0, _row(31, nC), False)
    # piece 10: on its own, so a report next to it keeps a single piece (odd count of one)
    add(T0 + 2000.0, _row(40, nC), True)

    psd_t = [T0 + 1000.5, T0 + 1002.0, T0 + 3000.0, T0 + 3004.0]
    psd_lsb = [_row(50, nC), _row(51, nC, holes=(0, 1)), _row(52, nC), [None] * nC]

    return {"channel": "ZERO_THREE_LEFT", "centers_hz": [float(c) for c in CENTERS],
            "window_s": TILE_S, "band_half_hz": 2.5,
            "td": {"t": td_t, "lsb": td_lsb, "saturated": [False] * len(td_t),
                   "source": ["constructed"] * len(td_t),
                   "n_finite_s": [TILE_S] * len(td_t), "ok": td_ok},
            "psd": {"t": psd_t, "lsb": psd_lsb,
                    "calibrated": [[True] * nC] * len(psd_t),
                    "source": ["constructed"] * len(psd_t)},
            "n_td_windows": len(td_t), "n_psd_windows": len(psd_t)}


def _pro_times():
    """Pain reports aimed at each branch, in a deliberately unsorted order.

    Every time here is DISTINCT. Two pain reports filed at the identical second are not separated
    by the nearest-report rule at all -- which of them owns a piece of recording depends on which
    side of them the piece falls, because the search compares a piece against its two neighbours in
    time and two identical times are one neighbour twice. That is long-standing behaviour and is
    covered on its own in `test_two_pain_reports_at_the_same_second_share_no_piece`, where the
    assertion is the property that matters (no piece counted twice) rather than a rule about which
    report wins. Mixing it in here would make the reference below encode that quirk instead of the
    documented rule it is meant to check independently.
    """
    return [
        T0 + 9.0,        # 0: middle of the six-piece run -> EVEN selection when the cap allows
        T0 + 501.5,      # 1: exactly midway between the two all-NaN pieces -> matched, no values
        T0 + 1001.5,     # 2: beside the two gate-failed pieces -> no eligible piece -> falls to
                         #    the device-spectrum windows at 1000.5 / 1002.0
        T0 + 2000.0,     # 3: on top of the lone piece -> single-piece selection
        T0 + 3002.0,     # 4: midway between two device-spectrum windows, one of them all-NaN
        T0 + 90000.0,    # 5: nowhere near anything -> unmatched
        T0 + 6.0,        # 6: exactly midway between pieces 1 and 2 -> tie on distance
        T0 + 12.0,       # 7: exactly midway between pieces 3 and 4 -> a second distance tie
    ]


def _assert_same(new_recs, ref_recs, label):
    assert len(new_recs) == len(ref_recs), "%s: %d records vs %d" % (
        label, len(new_recs), len(ref_recs))
    for i, (a, b) in enumerate(zip(new_recs, ref_recs)):
        for f in ("t", "tier", "lsb", "calibrated", "center_hz", "used_s", "saturated",
                  "reason", "n_td_used", "n_psd_used"):
            assert a[f] == b[f], "%s: report %d field %s: %r != %r" % (label, i, f, a[f], b[f])
            assert type(a[f]) is type(b[f]), "%s: report %d field %s type %s != %s" % (
                label, i, f, type(a[f]).__name__, type(b[f]).__name__)


# ---------------------------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------------------------
def test_padded_collapse_equals_per_report_loop_across_lengths_and_reuse():
    """The single padded nan-median reproduces the per-report loop for every length of signal the
    band sweep uses, in both window-reuse settings, on recordings holding an empty selection, an
    all-NaN selection, an even piece count and both kinds of tie."""
    cache, pro = _cache(), _pro_times()
    checked = 0
    for quantity_s in (3.0, 6.0, 9.0, 15.0, 21.0, 24.0, 30.0, 45.0, 60.0, 300.0):
        for reuse in (False, True):
            for tol_s in (5.0, 30.0, 600.0):
                got, _ = av.live_lsb_spectrum_match(
                    pro, cache, tol_s=tol_s, td_quantity_s=quantity_s,
                    allow_window_reuse=reuse)
                want = _reference(pro, cache, tol_s=tol_s, quantity_s=quantity_s, reuse=reuse)
                _assert_same(got, want, "q=%g reuse=%s tol=%g" % (quantity_s, reuse, tol_s))
                checked += 1
    assert checked == 60


def test_every_branch_is_actually_reached():
    """The constructed recordings are worth nothing unless they hit all three outcomes and both
    NaN cases, so assert the coverage rather than trusting the layout."""
    cache, pro = _cache(), _pro_times()
    recs, stats = av.live_lsb_spectrum_match(pro, cache, tol_s=30.0, td_quantity_s=300.0)
    tiers = [r["tier"] for r in recs]
    assert tiers.count("td_transform") >= 4, tiers
    assert tiers.count("psd_bridge") >= 2, tiers
    assert tiers.count(None) >= 1, tiers
    # the all-NaN selection: matched on the time-domain pieces, every band reading None
    all_nan = recs[1]
    assert all_nan["tier"] == "td_transform"
    assert all_nan["n_td_used"] == 2 and all_nan["used_s"] == 6.0
    assert all_nan["lsb"] == [None] * len(CENTERS)
    assert all_nan["calibrated"] == [False] * len(CENTERS)
    # the empty selection: the two nearby pieces failed the quality gate, so the report must NOT
    # be a time-domain match; it falls through to the device-spectrum windows beside it
    assert recs[2]["tier"] == "psd_bridge" and recs[2]["n_td_used"] == 0
    # the unmatched report keeps its untouched record
    assert recs[5]["tier"] is None and recs[5]["lsb"] == [None] * len(CENTERS)
    assert recs[5]["used_s"] == 0.0 and recs[5]["reason"] == ""
    assert stats["n_pro_td"] + stats["n_pro_psd"] + stats["n_pro_unmatched"] == len(pro)


def test_even_piece_count_median_averages_the_middle_two():
    """An even selection is the case where which pieces were selected changes the answer, so check
    the value against an explicit average of the two middle numbers."""
    cache = _cache()
    pro = [T0 + 9.0]
    recs, _ = av.live_lsb_spectrum_match(pro, cache, tol_s=30.0, td_quantity_s=18.0)
    assert recs[0]["n_td_used"] == 6, recs[0]["n_td_used"]
    for j in range(len(CENTERS)):
        vals = sorted(r[j] for r in cache["td"]["lsb"][:6] if r[j] is not None)
        n = len(vals)
        want = (vals[n // 2] if n % 2 else 0.5 * (vals[n // 2 - 1] + vals[n // 2]))
        assert recs[0]["lsb"][j] == want, (j, recs[0]["lsb"][j], want)


def test_distance_tie_keeps_the_earlier_piece():
    """A pain report exactly midway between two pieces, with room for only one, must keep the
    earlier piece -- the rule the docstring states and the one an even median depends on."""
    cache = _cache()
    pro = [T0 + 6.0]                                    # midway between pieces at 4.5 s and 7.5 s
    recs, _ = av.live_lsb_spectrum_match(pro, cache, tol_s=5.0, td_quantity_s=3.0)
    assert recs[0]["n_td_used"] == 1
    assert recs[0]["lsb"] == [v for v in cache["td"]["lsb"][1]]


def test_two_pain_reports_at_the_same_second_share_no_piece():
    """Two pain reports filed at the identical second must not both count the same piece of
    recording when window reuse is off, and must produce identical records when it is on."""
    cache = _cache()
    pro = [T0 + 6.0, T0 + 6.0]
    alone, s1 = av.live_lsb_spectrum_match([T0 + 6.0], cache, tol_s=5.0, td_quantity_s=300.0)
    pair, s2 = av.live_lsb_spectrum_match(pro, cache, tol_s=5.0, td_quantity_s=300.0)
    # the same pieces are eligible either way, and adding the second report cannot make any piece
    # serve twice -- the total used stays what one report alone used
    assert s2["n_td_used"] == s1["n_td_used"] == alone[0]["n_td_used"]
    # the eligible pieces are PARTITIONED between the two reports (some fall before them, some
    # after, and each piece goes to exactly one), so the two used counts sum to the one-report total
    assert sum(r["n_td_used"] for r in pair) == alone[0]["n_td_used"]
    assert all(r["n_td_used"] >= 1 and r["tier"] == "td_transform" for r in pair)
    # with window reuse both reports see the same pieces and must agree exactly
    both, _ = av.live_lsb_spectrum_match(pro, cache, tol_s=5.0, td_quantity_s=300.0,
                                         allow_window_reuse=True)
    assert both[0]["lsb"] == both[1]["lsb"] and both[0]["n_td_used"] == both[1]["n_td_used"]
    assert both[0]["lsb"] == alone[0]["lsb"]


def test_row_conversion_fast_path_equals_the_elementwise_fill():
    """The one-call conversion of the cache's list of lists must equal the old element-by-element
    fill, including for a ragged row, a missing row and a row of all None."""
    nC = 4
    tidy = [[1.0, None, 3.5, 4.0], [None] * nC, [0.0, 0.0, 0.0, 0.0]]
    fast = av._lsb_rows_to_mat(tidy, nC)
    slow = np.full((len(tidy), nC), np.nan)
    for i, row in enumerate(tidy):
        for j, v in enumerate(row):
            if v is not None:
                slow[i, j] = v
    assert np.array_equal(fast, slow, equal_nan=True)
    ragged = [[1.0, 2.0], None, [1.0, 2.0, 3.0, 4.0, 5.0]]
    got = av._lsb_rows_to_mat(ragged, nC)
    assert got.shape == (3, nC)
    assert np.array_equal(got[0], [1.0, 2.0, np.nan, np.nan], equal_nan=True)
    assert np.all(np.isnan(got[1]))
    assert np.array_equal(got[2], [1.0, 2.0, 3.0, 4.0], equal_nan=True)
    assert av._lsb_rows_to_mat([], nC).shape == (0, nC)


def test_converted_matrix_is_reused_and_invalidated_with_the_rows():
    """The matrix is converted once per cache and handed back on later calls, but a replaced row
    list must force a fresh conversion rather than serving a stale matrix."""
    fam = {"lsb": [[1.0, 2.0], [3.0, None]]}
    first = av._lsb_family_mat(fam, 2)
    assert av._lsb_family_mat(fam, 2) is first
    assert not first.flags.writeable
    fam["lsb"] = [[9.0, 9.0]]
    second = av._lsb_family_mat(fam, 2)
    assert second is not first and second.shape == (1, 2)
    assert av._lsb_family_mat(fam, 3).shape == (1, 3)     # a different band count re-converts


def test_length_cap_selects_the_same_pieces_as_the_old_per_report_argsort():
    """The all-reports-at-once nearest-N cap must pick the identical pieces the per-report
    `argsort(|dt|, stable)[:cap]` picked, including the pieces it leaves in place when a report
    owns fewer than the cap."""
    rng = np.random.default_rng(7)
    win_t = np.sort(rng.uniform(0.0, 400.0, size=40))
    pro = rng.uniform(0.0, 400.0, size=9)
    idx = np.tile(np.arange(40, dtype=np.int64), (9, 1))
    idx[3, 25:] = -1                                     # a short row, below every cap tested
    idx[6, 2:] = -1                                      # a row of one
    for cap in (1, 2, 5, 25, 40, 100):
        got = av._cap_nearest_windows(idx.copy(), win_t, pro, cap)
        for p in range(9):
            sel = idx[p][idx[p] >= 0]
            if sel.size > cap:
                keep = np.argsort(np.abs(win_t[sel] - pro[p]), kind="stable")[:cap]
                want = sel[np.sort(keep)]
            else:
                want = sel
            have = got[p][got[p] >= 0]
            assert np.array_equal(np.sort(have), np.sort(want)), (cap, p, have, want)
            assert np.array_equal(have, want), (cap, p, have, want)
