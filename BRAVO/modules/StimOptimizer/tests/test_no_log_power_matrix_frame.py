"""The older spectrum frame reads raw power (decision 204).

``lfp_evidence.frame_from_matrix`` turns the Biomarkers module's assembled full-spectrum matrix
into the row frame ``build_evidence`` consumes, and ``band_power_linear`` integrates a band out of
it. Until now the matrix held decibels and this module undid them (``10 ** (x / 10)``) at every
call site, with a named convention so the undoing could not be got wrong by a factor of ten in the
exponent. The matrix now holds raw power under ``X`` (decision 204, on the PI's rule of 2026-09-19
that log power enters no calculation), so there is nothing to undo: the frame column is ``psd``,
the band power is the plain integral of the raw bins, and the convention table is gone.

This frame is not the live route (the calibrated device-scale frame has been the default since
2026-09-06), but it reads the same stored field and must read it correctly.
"""
import ast
import pathlib

import numpy as np
import pytest

from StimOptimizer.routines import lfp_evidence as EV

SRC = pathlib.Path(EV.__file__)


def test_frame_from_matrix_reads_X_and_emits_a_raw_psd_column():
    f = np.array([10.0, 20.0, 30.0])
    mat = {"X": np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]), "t": np.array([1.0, 2.0]),
           "channel": np.array(["ZERO_TWO_LEFT", "ZERO_TWO_LEFT"], dtype=object),
           "source": np.array(["TD streaming", "TD streaming"], dtype=object), "f_set": f}
    fr = EV.frame_from_matrix(mat)
    assert "psd" in fr.columns and "log_psd" not in fr.columns, list(fr.columns)
    assert np.array_equal(np.vstack(fr["psd"].to_numpy()), mat["X"])


def test_frame_from_matrix_refuses_the_old_decibel_field():
    mat = {"logX": np.zeros((1, 3)), "t": np.array([1.0]), "channel": np.array(["a"], dtype=object),
           "f_set": np.array([1.0, 2.0, 3.0])}
    with pytest.raises(KeyError):
        EV.frame_from_matrix(mat)


def test_band_power_is_the_integral_of_the_raw_bins_with_nothing_undone():
    f = np.arange(1.0, 41.0, 1.0)
    psd = np.zeros((2, f.size))
    sel = (f >= 17.5) & (f <= 22.5)                    # 18..22 inclusive, five bins
    psd[0, sel] = [1.0, 2.0, 3.0, 2.0, 1.0]
    psd[1, sel] = [10.0, 10.0, 10.0, 10.0, 10.0]
    v = EV.band_power_linear(psd, f, 20.0, 5.0)
    assert np.array_equal(v, np.array([9.0, 50.0])), v


def test_the_decibel_convention_table_is_gone():
    assert not hasattr(EV, "LOG_SCALES") and not hasattr(EV, "DEFAULT_LOG_SCALE")


def test_no_reader_of_the_matrix_frame_takes_a_logarithm_or_a_power_of_ten():
    tree = ast.parse(SRC.read_text())
    fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
           and n.name in ("frame_from_matrix", "band_power_linear", "build_evidence")}
    assert set(fns) == {"frame_from_matrix", "band_power_linear", "build_evidence"}
    bad = {}
    for name, fn in fns.items():
        hits = [n.lineno for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr in ("log10", "log", "log2", "power")]
        hits += [n.lineno for n in ast.walk(fn)
                 if isinstance(n, ast.Constant) and n.value == "log_psd"]
        if hits:
            bad[name] = hits
    assert bad == {}, bad
