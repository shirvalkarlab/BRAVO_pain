"""
REDCap PRO pull for the Biomarkers module.

PROVENANCE
----------
`pull_redcap` is vendored from `dbs_stage2_percept/dbs_io/utils.py` (original author: J. Prosky).
The PyCap export call is UNCHANGED. The only difference is credential sourcing: instead of
reading the API token from a committed/local JSON file (or prompting interactively), credentials
come from environment variables first:

    REDCAP_API_URL    e.g. https://redcap.ucsf.edu/api/
    REDCAP_API_TOKEN  the project API token (NEVER commit this)

For local dev a JSON file fallback ({"api_url": ..., "api_key": ...}) is still supported so the
notebook workflow keeps working, but the env-var path is preferred and is the only path used in
any shared/server context.

`load_processed_pro_csv` mirrors the lightweight CSV path used by the notebooks
(`pt_data/<pt>_redcap_proc.csv`) for offline/library-mode runs without hitting the API.
"""

import os
import json

import pandas as pd


def get_redcap_credentials(redcap_config=None):
    """
    Resolve REDCap (api_url, api_key).

    Order of precedence:
      1. REDCAP_API_URL / REDCAP_API_TOKEN environment variables.
      2. `redcap_config` JSON file with keys {"api_url", "api_key"} (local dev only).

    Never returns a token sourced from a committed file; the JSON fallback is intended for
    a gitignored local config (the dbs_stage2 repo gitignores *.json for exactly this).
    """
    api_url = os.environ.get("REDCAP_API_URL")
    api_key = os.environ.get("REDCAP_API_TOKEN")
    if api_url and api_key:
        return api_url, api_key

    if redcap_config and os.path.isfile(redcap_config):
        with open(redcap_config, "r") as fp:
            api_dict = json.load(fp)
        return api_dict["api_url"], api_dict["api_key"]

    raise RuntimeError(
        "REDCap credentials not found. Set REDCAP_API_URL and REDCAP_API_TOKEN "
        "environment variables, or pass a local redcap_config JSON path "
        '({"api_url": ..., "api_key": ...}).'
    )


def pull_redcap(redcap_config=None, save=False, save_path=None):
    """
    Pull survey data from REDCap, returning a pandas DataFrame.

    Vendored from dbs_io.utils.pull_redcap; the PyCap export call is identical. Credentials
    are resolved via `get_redcap_credentials` (env vars preferred). `redcap` (PyCap) is
    imported lazily so this module is importable in environments without it installed.
    """
    import redcap  # PyCap; lazy so tests / library imports don't require it

    api_url, api_key = get_redcap_credentials(redcap_config)

    project = redcap.Project(api_url, api_key)
    redcap_data = project.export_records(
        format_type="df",
        export_checkbox_labels=True,
        export_survey_fields=True,
    )

    if save:
        if save_path is None:
            date = pd.Timestamp.now().strftime("%Y-%m-%d_%H-%M-%S")
            save_path = os.path.join(os.getcwd(), f"{date}_redcap_data.csv")
        redcap_data.to_csv(save_path)
        print(f"The data has been saved to {save_path}")
    return redcap_data


# Canonical timestamp column the Pain Scores / Biomarker endpoints expect downstream.
TIDY_TIMESTAMP_COL = "date_time_s1_daily"


def process_redcap(redcap_data, field_map):
    """Turn a raw REDCap export into the tidy per-report PRO table the module consumes.

    Ports the filter -> subset -> rename/sum -> sort -> fillna processing from
    `dbs_stage2_percept/redcap_pull.py` so raw REDCap column names map to the canonical metric
    keys (`nrs`, `vas`, `mpq_sum`, ...) that `bravo_service` / the Pain Scores endpoint read.

    Driven by a patient field map (the relevant `pt_config` keys):
      instruments      list of `redcap_repeat_instrument` values to keep (the PRO survey rows)
      timestamp_label  raw REDCap column holding the report timestamp; emitted as the canonical
                       `date_time_s1_daily`
      metric_labels    {canonical_key: raw_column}  OR  {canonical_key: [raw_col, ...]}. A list is
                       summed row-wise into the key (e.g. MPQ item subscores).
      pt / record_id   optional; restricts to this patient's `record_id`.

    (The notebook also kept each list component under `raw_col[:-9]`; that fixed-suffix slice
    collides for some field-naming schemes and is unused downstream, so only the summed canonical
    key is emitted here.)

    Pure pandas (no Django, no network) so it is unit-testable and reusable from library mode.
    """
    timestamp_label = field_map.get("timestamp_label")
    metric_labels = field_map.get("metric_labels") or {}
    if not (timestamp_label and metric_labels):
        raise ValueError("field_map must define 'timestamp_label' and a non-empty 'metric_labels'.")

    df = redcap_data.reset_index()

    instruments = field_map.get("instruments")
    if instruments and "redcap_repeat_instrument" in df.columns:
        df = df[df["redcap_repeat_instrument"].isin(instruments)]
    record_id = field_map.get("pt", field_map.get("record_id"))
    if record_id is not None and "record_id" in df.columns:
        df = df[df["record_id"].astype(str) == str(record_id)]
    df = df.reset_index(drop=True)

    if timestamp_label not in df.columns:
        raise ValueError(f"timestamp column {timestamp_label!r} not found in the REDCap export.")

    proc = pd.DataFrame(index=df.index)
    for key, value in metric_labels.items():
        if isinstance(value, list):
            present = [v for v in value if v in df.columns]
            if present:
                proc[key] = df[present].apply(pd.to_numeric, errors="coerce").sum(axis=1)
        elif value in df.columns:
            proc[key] = df[value]

    proc[TIDY_TIMESTAMP_COL] = df[timestamp_label]
    proc = proc.sort_values(TIDY_TIMESTAMP_COL).reset_index(drop=True)
    return proc.fillna(0)


def load_processed_pro_csv(csv_path):
    """
    Load a pre-processed PRO CSV (the `pt_data/<pt>_redcap_proc.csv` produced by the
    dbs_stage2 `redcap_pull.py` driver). Used for offline / library-mode runs.

    Expected columns include a timestamp (`date_time_s1_daily`) and metric columns such as
    `nrs`, `vas`, `mpq_sum`. Returned unchanged except a parsed `date` helper column.
    """
    df = pd.read_csv(csv_path)
    if "date_time_s1_daily" in df.columns:
        df["date"] = pd.to_datetime(df["date_time_s1_daily"]).dt.date
    return df
