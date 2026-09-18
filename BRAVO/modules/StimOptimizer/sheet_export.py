"""Turns `titration_plan.py`'s flat `sheet_rows` into an actual clinic-visit workbook -- either a
real, shared Google Sheet (when the server has Google credentials, see `google_sheets_client.py`)
or a downloaded `.xlsx` built from the lab's own template (when it does not). The PI's ruling of
2026-09-14, verbatim: "make a button that says 'Make Google sheet' that has a date input to use
that entered date. This should use Google Sheets template -> copy to a new file (do not write into
template) -> write schedule into the new file -> rename new file with date (Wed, Sep 16 OR USER
ENTERED DATE) and allow it to be overwritten if re-exported."

WHERE IT IS ON SCREEN. Stim Optimizer page, the "Titration session to run next" card
(`TitrationSessionCard.js`): the date field and the "Make Google sheet" button at its top right.

THE TEMPLATE NEVER TAKES A WRITE. `fill_workbook` copies the template's bytes to a new file BEFORE
opening anything with openpyxl and re-checks the template's own sha256 after saving, so a bug that
somehow opened the template itself for writing is caught rather than silently shipped. The Drive
path never calls a Drive or Sheets write method (`copy`, `clear`, `update`) against the template's
own file id -- `copy_file` COPIES the template into a new file and returns the new file's id; every
write after that goes to the new id only.

A RE-EXPORT OVERWRITES THE VISIT'S OWN FILE, NOT THE TEMPLATE. The visit's file name
(`sheet_name_for`) is deterministic from the participant code and the visit date, so exporting the
same date twice finds the file already sitting in the lab's Drive folder and clears-and-rewrites
it rather than making a second copy -- the PI's own "allow it to be overwritten if re-exported."

NO DJANGO HERE. `export` takes the already-built `titration_plan` block (the `sheet_rows` /
`sheet_columns` fields `StimOptimizer.titration_plan.plan_for_sides` returns) and an optional
`drive` client (an object exposing the four small operations this file calls; see
`google_sheets_client.py` for the real one). The Django view (`Server/APIs/DataAnalysis.py`,
`ExportTitrationSheet`) is what decides whether a `drive` client is available and reads the request
date.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
import tempfile

#: The template workbook's "Stim Testing" tab, read directly with openpyxl on 2026-09-14
#: (`titration_plan.SHEET_SOURCE`): header row 11, columns A-S, data from row 12.
SHEET_TAB = "Stim Testing"
DATA_START_ROW = 12

#: The range the Drive path clears before writing new rows. 2000 is generous headroom over the
#: largest plan seen so far (68 rows, decision 160-162) so a smaller re-export never leaves a
#: stale tail of rows from a longer previous one.
CLEAR_MAX_ROW = 2000

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

# Participant-specific provenance and examples are maintained outside source control.
TEMPLATE_PATH = os.path.normpath(os.path.join(
    _MODULE_DIR, "..", "..", "_pro_dump", "clinic_sheets", "RCS08",
    "_Template_RCS08 Stage 2 - _Month_ 2025 Clinic Testing _MM___DD___YY_.xlsx"))


def _parse_date(visit_date):
    """Accepts a `date`, a `datetime`, or an ISO "YYYY-MM-DD" string (what the page's
    `<input type="date">` sends); always returns a plain `date`."""
    if isinstance(visit_date, _dt.datetime):
        return visit_date.date()
    if isinstance(visit_date, _dt.date):
        return visit_date
    s = str(visit_date).strip()
    return _dt.datetime.strptime(s, "%Y-%m-%d").date()


def sheet_name_for(visit_date, participant_code="RCS08") -> str:
    """Generic implementation; participant-specific examples are kept outside source control."""
    d = _parse_date(visit_date)
    return (f"{participant_code} Stage 2 - {d.strftime('%B')} {d.year} In-Clinic Testing "
            f"{d.strftime('%m_%d_%y')}")


def values_for_sheets_api(sheet_rows, sheet_columns):
    """`sheet_rows` (a list of dicts keyed by `sheet_columns`, plus `block`/`step`/`row_kind`
    which are NOT sheet columns and are ignored here) as a plain 2-D list in `sheet_columns`
    order. `None` becomes `""`: the Sheets API's `values.update` cannot carry a JSON null."""
    return [["" if row.get(c) is None else row.get(c) for c in sheet_columns] for row in sheet_rows]


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fill_workbook(template_path, sheet_rows, sheet_columns, visit_date, out_path, *,
                   tab=SHEET_TAB, data_start_row=DATA_START_ROW) -> dict:
    """Copy `template_path`'s BYTES to `out_path` (never open the template itself for writing),
    open the copy, set `tab`'s B1 cell to the visit date (the real visit sheets' own convention --
    a real Excel date, `mm/dd/yy`, not a string), write `sheet_rows` from `data_start_row` down in
    `sheet_columns` order (by column POSITION, A=1..S=19 -- the real template's header row carries
    per-editor suffixes ("... (Aditya)", "... (Donna)") that `sheet_columns` does not, so columns
    are matched by their fixed order, never by matching header text), save.

    Returns `{"tab", "row_start", "row_end", "n_rows"}`. Raises if the template's own sha256
    changed while this ran -- it never should, since it is only ever read, but a bug that somehow
    opened it for writing must not ship silently."""
    import shutil

    import openpyxl

    before = _sha256(template_path)
    shutil.copyfile(template_path, out_path)
    d = _parse_date(visit_date)

    wb = openpyxl.load_workbook(out_path)
    ws = wb[tab]
    ws["B1"] = _dt.datetime(d.year, d.month, d.day)
    ws["B1"].number_format = "mm/dd/yy"

    from openpyxl.styles import Alignment
    centred = Alignment(horizontal="center")           # the PI's rule of 2026-09-16, written rows only
    row = data_start_row
    for r in sheet_rows:
        for i, col in enumerate(sheet_columns, start=1):
            # `ws.cell(row, column, value=None)` is a no-op in openpyxl (it only assigns when the
            # value is not None), so a `None` row value would silently leave whatever the
            # template's own cell already held -- e.g. row 12 column L's stray "Detailed pain
            # survey" label. Assigning `.value` directly always overwrites, `None` included.
            cell = ws.cell(row=row, column=i)
            cell.value = r.get(col)
            cell.alignment = centred
        row += 1
    wb.save(out_path)

    after = _sha256(template_path)
    if after != before:
        raise RuntimeError(
            f"the template at {template_path} changed while building {out_path}; an export must "
            "never write into the template itself")

    return {"tab": tab, "row_start": data_start_row, "row_end": row - 1, "n_rows": len(sheet_rows)}


def export(plan, participant_code, visit_date, *, drive=None, template_path=None) -> dict:
    """Build the visit's clinic sheet from `plan["sheet_rows"]` / `plan["sheet_columns"]`
    (`titration_plan.plan_for_sides`'s own fields).

    With a `drive` client available (see `google_sheets_client.py`): copy the template into the
    lab's Drive folder under the visit's own name (`sheet_name_for`), REUSING an existing file of
    that name if a previous export already made one, so a re-export overwrites rather than
    duplicating; clear the old data rows; write the date and the new rows. Returns
    `{"mode": "drive", "url", "file_id", "name", "n_rows", "overwrote"}`.

    Without one: fill a local copy of the template and return its path for the caller to serve as
    a download. Returns `{"mode": "xlsx", "path", "name", "n_rows", "setup"}`, where `setup` is
    the plain-language note on what a server operator must do to turn the Drive path on.

    Returns `{"mode": "error", "reason"}` rather than raising when the plan carries no rows to
    export or the local template is missing (the xlsx path only)."""
    sheet_rows = list(plan.get("sheet_rows") or [])
    sheet_columns = list(plan.get("sheet_columns") or [])
    if not sheet_rows or not sheet_columns:
        return {"mode": "error", "reason": "the titration plan has no clinic-sheet rows to export"}

    name = sheet_name_for(visit_date, participant_code)

    if drive is not None:
        from . import google_sheets_client as gsc

        folder = gsc.folder_id()
        template = gsc.template_id()
        existing = drive.find_file_in_folder(folder, name)
        overwrote = existing is not None
        file_id = existing if overwrote else drive.copy_file(template, folder, name)

        rng = f"'{SHEET_TAB}'!A{DATA_START_ROW}:S{CLEAR_MAX_ROW}"
        drive.clear_values(file_id, rng)
        values = values_for_sheets_api(sheet_rows, sheet_columns)
        drive.update_values(file_id, f"'{SHEET_TAB}'!A{DATA_START_ROW}", values)
        # The PI's rule of 2026-09-16: the rows this export enters are centred in every column;
        # nothing above them (the header, the date, the template's own rows) is touched.
        drive.center_cells(file_id, SHEET_TAB, DATA_START_ROW, len(values), len(sheet_columns))
        d = _parse_date(visit_date)
        drive.update_values(file_id, f"'{SHEET_TAB}'!B1", [[d.strftime("%m/%d/%Y")]])

        return {"mode": "drive", "url": drive.file_url(file_id), "file_id": file_id, "name": name,
                "n_rows": len(sheet_rows), "overwrote": overwrote}

    tmpl = template_path or TEMPLATE_PATH
    if not os.path.isfile(tmpl):
        return {"mode": "error",
                "reason": f"the clinic-sheet template is not on this server at {tmpl}"}

    from . import google_sheets_client as gsc

    out_dir = tempfile.mkdtemp(prefix="sheet_export_")
    out_path = os.path.join(out_dir, name + ".xlsx")
    fill_workbook(tmpl, sheet_rows, sheet_columns, visit_date, out_path)
    return {"mode": "xlsx", "path": out_path, "name": name, "n_rows": len(sheet_rows),
            "setup": gsc.SETUP_NOTE}
