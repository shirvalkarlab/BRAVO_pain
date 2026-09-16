"""The "Make Google sheet" export (`sheet_export.py`), the PI's ruling of 2026-09-14: copy the
lab's template into a new file (never write into the template itself), write the schedule into the
new file, name it from the visit date, and let a re-export for the same date overwrite that file.

Every workbook here is CONSTRUCTED with openpyxl and read back through the real `openpyxl`
reader, the same discipline `test_clinic_pain.py` established, rather than asserted against a
hand-built dict; the rows written are the REAL output of `titration_plan.build_sheet_rows`, not
hand-typed values, so a column-order or a bilateral-formatting regression in that function would
also fail here. `export`'s Drive path is tested against a small fake client recording every call
it receives, checked value for value: which file id every write landed on, and that the template's
own id is only ever used as `copy_file`'s SOURCE, never as a write target.
"""
import datetime

import pandas as pd
import pytest

openpyxl = pytest.importorskip("openpyxl")

from ClosedLoopDeployment import post_ramp as PR
from StimOptimizer import sheet_export as SE
from StimOptimizer import titration_plan as TP


# ---------------------------------------------------------------------------------------------
# a real, small clinic sheet, built the same way test_titration_plan.py does
# ---------------------------------------------------------------------------------------------
def _side(**kw):
    base = dict(rate_in_force_hz=55.0, rate_source="stream", pulse_width_us=100.0,
                pulse_width_source="stream", ceiling_mA=1.5, ceiling_source="stated by PI",
                contact={"channel": "ONE_THREE_LEFT", "display_short": "L 1⁻3⁺", "n_responding": 12,
                         "n_bands": 18, "laterality": "ipsilateral", "deployable": True,
                         "rate_hz": 55.0, "sensing_side": "Left"},
                contact_source="the readiness screen",
                record_today=TP.record_today_for_contact(None, None, "ONE_THREE_LEFT"))
    base.update(kw)
    return base


def _real_sheet_rows():
    """A real, small clinic sheet built through the actual production functions: two ladders
    (1.5 mA ceilings, so 4 up-steps + 2 down-steps = 6 steps each) plus the joint-corners block,
    exactly `titration_plan.build_sheet_rows`'s own output."""
    margin = PR.margin_becomes_available(None)
    left = TP.side_plan("Left", margin=margin, held_other_side_mA=1.0,
                        held_other_side_source="the Right side", **_side())
    right = TP.side_plan("Right", margin=margin, held_other_side_mA=0.5,
                         held_other_side_source="the Left side",
                         **_side(rate_in_force_hz=55.0, pulse_width_us=150.0))
    sides = {"Left": left, "Right": right}
    in_force = {"Left": {"contacts_short": "L C+2-", "pulse_width_us": 100.0},
               "Right": {"contacts_short": "R C+1-", "pulse_width_us": 150.0}}
    timing = TP.step_timing()
    jc = TP.joint_corners(1.5, 1.5)
    rows = TP.build_sheet_rows(sides, jc, in_force=in_force, timing=timing)
    return rows, list(TP.SHEET_COLUMNS)


def _write_template(path, *, header_row=11, data_row=12):
    """A workbook shaped like the lab's real template: 12 sheets, the one that matters is
    "Stim Testing" with the header at row 11 and a stray "Detailed pain survey" label at row 12
    column L -- the exact shape `_probe_inspect_template.py` found in the real template on
    2026-09-14, so `fill_workbook`'s row/column arithmetic is checked against the real layout."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    notes = wb.create_sheet("Notes")
    notes["A1"] = "placeholder tab, unrelated to Stim Testing"
    ws = wb.create_sheet("Stim Testing")
    for c, name in enumerate(TP.SHEET_COLUMNS, start=1):
        ws.cell(row=header_row, column=c, value=name)
    ws.cell(row=data_row, column=12, value="Detailed pain survey")  # column L, a label to overwrite
    wb.save(str(path))
    return path


# ---------------------------------------------------------------------------------------------
# sheet_name_for: the lab's own visit-file naming convention
# ---------------------------------------------------------------------------------------------
def test_sheet_name_for_matches_the_lab_convention():
    assert (SE.sheet_name_for(datetime.date(2026, 9, 16))
            == "RCS08 Stage 2 - September 2026 In-Clinic Testing 09_16_26")
    assert (SE.sheet_name_for("2026-09-16")
            == "RCS08 Stage 2 - September 2026 In-Clinic Testing 09_16_26")
    assert (SE.sheet_name_for(datetime.datetime(2026, 8, 18, 14, 30), participant_code="RCS08")
            == "RCS08 Stage 2 - August 2026 In-Clinic Testing 08_18_26")


# ---------------------------------------------------------------------------------------------
# values_for_sheets_api: a plain 2-D list, None -> ""
# ---------------------------------------------------------------------------------------------
def test_values_for_sheets_api_replaces_none_with_empty_string_and_keeps_column_order():
    rows, cols = _real_sheet_rows()
    values = SE.values_for_sheets_api(rows, cols)
    assert len(values) == len(rows)
    for row_dict, row_values in zip(rows, values):
        assert row_values == [("" if row_dict.get(c) is None else row_dict.get(c)) for c in cols]
        assert all(v != None for v in row_values)  # noqa: E711 -- None must never survive


# ---------------------------------------------------------------------------------------------
# fill_workbook: the template's bytes are never touched; rows land at A12.. in column order
# ---------------------------------------------------------------------------------------------
def test_fill_workbook_leaves_the_template_byte_identical(tmp_path):
    tmpl = _write_template(tmp_path / "template.xlsx")
    before = SE._sha256(tmpl)
    rows, cols = _real_sheet_rows()
    out = tmp_path / "out.xlsx"
    SE.fill_workbook(str(tmpl), rows, cols, "2026-09-16", str(out))
    after = SE._sha256(tmpl)
    assert before == after


def test_fill_workbook_writes_every_row_in_column_order_starting_at_row_12(tmp_path):
    tmpl = _write_template(tmp_path / "template.xlsx")
    rows, cols = _real_sheet_rows()
    out = tmp_path / "out.xlsx"
    info = SE.fill_workbook(str(tmpl), rows, cols, "2026-09-16", str(out))
    assert info["row_start"] == 12
    assert info["n_rows"] == len(rows)
    assert info["row_end"] == 12 + len(rows) - 1

    wb = openpyxl.load_workbook(str(out))
    ws = wb["Stim Testing"]
    for i, row_dict in enumerate(rows):
        r = 12 + i
        for c, col in enumerate(cols, start=1):
            expected = row_dict.get(col)
            got = ws.cell(row=r, column=c).value
            assert got == expected, f"row {r} col {col!r}: expected {expected!r}, got {got!r}"
    # the header row itself is untouched
    for c, name in enumerate(cols, start=1):
        assert ws.cell(row=11, column=c).value == name
    # the row-12 label the real template carries at column L is overwritten by the first row's
    # own "General Notes / Pt Verbal Notes" value (None for a ramp row) -- proving the write
    # really replaces it rather than leaving it alone by accident
    assert ws.cell(row=12, column=12).value == rows[0].get("General Notes / Pt Verbal Notes")


def test_fill_workbook_sets_the_b1_date_cell_as_a_real_date(tmp_path):
    tmpl = _write_template(tmp_path / "template.xlsx")
    rows, cols = _real_sheet_rows()
    out = tmp_path / "out.xlsx"
    SE.fill_workbook(str(tmpl), rows, cols, "2026-09-16", str(out))
    wb = openpyxl.load_workbook(str(out))
    ws = wb["Stim Testing"]
    assert ws["B1"].value == datetime.datetime(2026, 9, 16)
    assert ws["B1"].number_format == "mm/dd/yy"


def test_fill_workbook_leaves_other_tabs_untouched(tmp_path):
    tmpl = _write_template(tmp_path / "template.xlsx")
    rows, cols = _real_sheet_rows()
    out = tmp_path / "out.xlsx"
    SE.fill_workbook(str(tmpl), rows, cols, "2026-09-16", str(out))
    wb = openpyxl.load_workbook(str(out))
    assert wb["Notes"]["A1"].value == "placeholder tab, unrelated to Stim Testing"


def test_fill_workbook_raises_if_the_template_is_mutated_mid_run(tmp_path, monkeypatch):
    tmpl = _write_template(tmp_path / "template.xlsx")
    rows, cols = _real_sheet_rows()
    out = tmp_path / "out.xlsx"

    real_sha = SE._sha256
    calls = {"n": 0}

    def _lying_sha(path):
        calls["n"] += 1
        if calls["n"] == 1:
            return real_sha(path)
        return "not-the-real-hash"  # simulate a mutation being detected on the second check

    monkeypatch.setattr(SE, "_sha256", _lying_sha)
    with pytest.raises(RuntimeError, match="must never write into the template"):
        SE.fill_workbook(str(tmpl), rows, cols, "2026-09-16", str(out))


# ---------------------------------------------------------------------------------------------
# export: a fake drive client, reusing an existing file vs copying, never writing the template id
# ---------------------------------------------------------------------------------------------
class _FakeDrive:
    """Records every call, in order, so a test can assert exactly which file id each write
    landed on -- in particular, that the TEMPLATE's own id is only ever passed as `copy_file`'s
    SOURCE, and never to `clear_values` or `update_values`."""

    def __init__(self, existing_by_name=None):
        self.existing_by_name = dict(existing_by_name or {})
        self.calls = []
        self._next_id = 1000

    def find_file_in_folder(self, folder_id, name):
        self.calls.append(("find_file_in_folder", folder_id, name))
        return self.existing_by_name.get(name)

    def center_cells(self, file_id, sheet_tab, first_row, n_rows, n_cols):
        self.calls.append(("center_cells", file_id, sheet_tab, first_row, n_rows, n_cols))

    def copy_file(self, source_id, folder_id, name):
        self.calls.append(("copy_file", source_id, folder_id, name))
        self._next_id += 1
        new_id = f"copy-{self._next_id}"
        self.existing_by_name[name] = new_id
        return new_id

    def clear_values(self, file_id, range_a1):
        self.calls.append(("clear_values", file_id, range_a1))

    def update_values(self, file_id, range_a1, values):
        self.calls.append(("update_values", file_id, range_a1, values))

    def file_url(self, file_id):
        return f"https://example.test/{file_id}"


def _plan():
    rows, cols = _real_sheet_rows()
    return {"sheet_rows": rows, "sheet_columns": cols}


def test_export_copies_the_template_when_no_file_exists_yet():
    drive = _FakeDrive()
    result = SE.export(_plan(), "RCS08", "2026-09-16", drive=drive)
    assert result["mode"] == "drive"
    assert result["overwrote"] is False
    assert result["name"] == "RCS08 Stage 2 - September 2026 In-Clinic Testing 09_16_26"
    kinds = [c[0] for c in drive.calls]
    assert kinds[:2] == ["find_file_in_folder", "copy_file"]
    assert "clear_values" in kinds and "update_values" in kinds
    # the template id is passed only as copy_file's SOURCE, never as a write target
    from StimOptimizer import google_sheets_client as gsc
    template = gsc.template_id()
    for call in drive.calls:
        kind = call[0]
        if kind == "copy_file":
            assert call[1] == template  # source
            assert call[3] != template
        elif kind in ("clear_values", "update_values"):
            assert call[1] != template, f"a write ({kind}) touched the template's own id"


def test_export_reuses_an_existing_file_of_the_same_name():
    name = "RCS08 Stage 2 - September 2026 In-Clinic Testing 09_16_26"
    drive = _FakeDrive(existing_by_name={name: "already-there-42"})
    result = SE.export(_plan(), "RCS08", "2026-09-16", drive=drive)
    assert result["mode"] == "drive"
    assert result["overwrote"] is True
    assert result["file_id"] == "already-there-42"
    kinds = [c[0] for c in drive.calls]
    assert "copy_file" not in kinds  # never re-copies when the file already exists
    assert kinds[0] == "find_file_in_folder"
    write_targets = {c[1] for c in drive.calls if c[0] in ("clear_values", "update_values")}
    assert write_targets == {"already-there-42"}


def test_export_writes_every_data_row_through_update_values():
    drive = _FakeDrive()
    rows, cols = _real_sheet_rows()
    result = SE.export({"sheet_rows": rows, "sheet_columns": cols}, "RCS08", "2026-09-16",
                       drive=drive)
    assert result["n_rows"] == len(rows)
    data_updates = [c for c in drive.calls if c[0] == "update_values" and "A12" in c[2]]
    assert len(data_updates) == 1
    written_values = data_updates[0][3]
    assert written_values == SE.values_for_sheets_api(rows, cols)


def test_export_without_a_drive_client_falls_back_to_a_filled_xlsx(tmp_path):
    tmpl = _write_template(tmp_path / "template.xlsx")
    plan = _plan()
    result = SE.export(plan, "RCS08", "2026-09-16", drive=None, template_path=str(tmpl))
    assert result["mode"] == "xlsx"
    assert result["name"] == "RCS08 Stage 2 - September 2026 In-Clinic Testing 09_16_26"
    assert result["n_rows"] == len(plan["sheet_rows"])
    assert "setup" in result and "service account" in result["setup"]
    import os
    assert os.path.isfile(result["path"])
    wb = openpyxl.load_workbook(result["path"])
    assert wb["Stim Testing"]["B1"].value == datetime.datetime(2026, 9, 16)


def test_export_with_no_sheet_rows_is_reported_as_an_error_not_an_exception():
    result = SE.export({"sheet_rows": [], "sheet_columns": list(TP.SHEET_COLUMNS)},
                       "RCS08", "2026-09-16", drive=_FakeDrive())
    assert result["mode"] == "error"
    assert "no clinic-sheet rows" in result["reason"]


# --- the PI's formatting rule of 2026-09-16: the rows the export enters are centred; the rest untouched
def test_the_drive_export_centres_only_the_rows_it_wrote(monkeypatch):
    from StimOptimizer import sheet_export as SE
    calls = []

    class _Drive:
        def find_file_in_folder(self, folder, name): return None
        def copy_file(self, src, folder, name): return "NEW"
        def clear_values(self, fid, rng): calls.append(("clear", rng))
        def update_values(self, fid, rng, values): calls.append(("update", rng, len(values)))
        def center_cells(self, fid, sheet_tab, first_row, n_rows, n_cols): calls.append(("center", sheet_tab, first_row, n_rows, n_cols))
        def file_url(self, fid): return "u"
    plan = {"sheet_rows": [{"Step": "1", "Amp": "L 1 / R 1"}, {"Step": "2", "Amp": "L 2 / R 2"}],
            "sheet_columns": ["Step", "Amp"]}
    SE.export(plan, "RCS08", "2026-12-30", drive=_Drive())
    centre = [c for c in calls if c[0] == "center"]
    assert centre == [("center", SE.SHEET_TAB, SE.DATA_START_ROW, 2, 2)], calls


def test_the_xlsx_export_centres_the_written_cells_and_leaves_the_header_row_alone(tmp_path):
    from StimOptimizer import sheet_export as SE
    from openpyxl import load_workbook
    tmpl = tmp_path / "tmpl.xlsx"
    _write_template(str(tmpl))
    rows = [{"Group": "A", "Contacts": "L C+2- / R C+1-"}]
    out = tmp_path / "out.xlsx"
    SE.fill_workbook(str(tmpl), rows, ["Group", "Contacts"], "2026-12-30", str(out))
    ws = load_workbook(str(out))["Stim Testing"]
    assert ws.cell(row=SE.DATA_START_ROW, column=1).alignment.horizontal == "center"
    assert ws.cell(row=SE.DATA_START_ROW, column=2).alignment.horizontal == "center"
    assert ws.cell(row=SE.DATA_START_ROW - 1, column=1).alignment.horizontal != "center"
