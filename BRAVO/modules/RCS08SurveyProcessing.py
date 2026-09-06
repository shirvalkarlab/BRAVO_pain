"""RCS08 daily survey scoring/QC reused from percept_analysis/updater.py.

Source snapshot and exact rule-file hashes are recorded in the deployment's
rcs08_processing manifest. No external writes or new scientific scoring rules.
"""
from pathlib import Path
import hashlib
import os
import pandas as pd

DAILY_INSTRUMENT = "stage_1_daily_surveys_vasnrsmpq"

SURVEY_START_COLUMN = "date_time_s1_daily"

SURVEY_END_COLUMN = f"{DAILY_INSTRUMENT}_timestamp"

SURVEY_COMPLETE_COLUMN = f"{DAILY_INSTRUMENT}_complete"

DAILY_COLUMNS = [
    "record_id",
    "redcap_event_name",
    "redcap_repeat_instrument",
    "redcap_repeat_instance",
    SURVEY_END_COLUMN,
    SURVEY_START_COLUMN,
    "mood_vas_s1_daily",
    "relief_vas_s1_daily",
    "pain_nrs_s1_daily",
    "pain_vas_s1_daily",
    "left_leg_vas_s1_daily",
    "back_vas_s1_daily",
    "throbbing_s1_daily",
    "shooting_s1_daily",
    "stabbing_s1_daily",
    "sharp_s1_daily",
    "cramping_s1_daily",
    "gnawing_s1_daily",
    "hot_burning_s1_daily",
    "aching_s1_daily",
    "heavy_s1_daily",
    "tender_s1_daily",
    "splitting_s1_daily",
    "tiring_exhausting_s1_daily",
    "sickening_s1_daily",
    "fearful_s1_daily",
    "cruel_punishing_s1_daily",
    "firey_s1_daily",
    "tingly_s1_daily",
    "electrocuting_s1_daily",
    "shortform_s1_daily",
    "completed_by_s1_daily",
    "mpq_s1_daily",
    SURVEY_COMPLETE_COLUMN,
]

SENSORY_MPQ = [
    "throbbing",
    "shooting",
    "stabbing",
    "sharp",
    "cramping",
    "gnawing",
    "hot_burning",
    "aching",
    "heavy",
    "tender",
    "splitting",
]

AFFECTIVE_MPQ = [
    "tiring_exhausting",
    "sickening",
    "fearful",
    "cruel_punishing",
]

STANDARD_MPQ = SENSORY_MPQ + AFFECTIVE_MPQ

EXTRA_MPQ = ["firey", "tingly", "electrocuting"]

CANONICAL_SURVEY_COLUMNS = [
    "participant_id",
    "source_event",
    "source_instrument",
    "repeat_instance",
    "survey_start",
    "survey_end",
    "survey_duration_min",
    "study_stage",
    "timestamp_source",
    "survey_complete",
    "completed_by",
    "nrs_intensity",
    "vas_intensity_raw",
    "vas_intensity",
    "vas_default_zero_suspect",
    "left_leg_vas_intensity",
    "back_vas_intensity",
    "relief_vas",
    "mood_vas",
    *[f"mpq_{name}" for name in STANDARD_MPQ],
    *EXTRA_MPQ,
    "mpq_sens",
    "mpq_aff",
    "mpq_standard_0_45",
    "mpq_redcap_expanded_0_54",
    "mpq_block_missing",
    "pain_description",
    "stim_testing_date",
    "include_in_analysis",
    "exclusion_reason",
]

def _load_testing_dates(path: str | Path) -> pd.DataFrame:
    dates = pd.read_csv(path)
    required = ["date", "stage", "event_type", "other_notes", "location"]
    missing = [column for column in required if column not in dates]
    if missing:
        raise ValueError(f"Stim-testing calendar is missing columns: {missing}")
    dates["date"] = pd.to_datetime(dates["date"], errors="raise").dt.normalize()
    if dates["date"].duplicated().any():
        raise ValueError("Stim-testing calendar contains duplicate dates")
    dates["exclude"] = dates["stage"].isin({"stage_1", "stage_2", "stage_3"})
    return dates

def _load_study_stages(path: str | Path) -> pd.DataFrame:
    stages = pd.read_csv(path)
    required = ["stage", "start_date", "end_date"]
    missing = [column for column in required if column not in stages]
    if missing:
        raise ValueError(f"Study-stage table is missing columns: {missing}")
    stages["start_date"] = pd.to_datetime(stages["start_date"], errors="raise").dt.normalize()
    stages["end_date"] = pd.to_datetime(stages["end_date"], errors="coerce").dt.normalize()
    return stages

def _add_exclusion_reason(surveys: pd.DataFrame, mask: pd.Series, reason: str) -> None:
    existing = surveys.loc[mask, "exclusion_reason"].fillna("").astype(str)
    surveys.loc[mask, "exclusion_reason"] = (
        existing.where(existing.eq(""), existing + "; ") + reason
    )
    surveys.loc[mask, "include_in_analysis"] = False

def _canonicalize_daily_surveys(
    daily: pd.DataFrame,
    *,
    study_stages_path: str | Path,
    testing_dates_path: str | Path,
    corrections_path: str | Path,
    value_corrections_path: str | Path | None = None,
    exclusions_path: str | Path,
) -> pd.DataFrame:
    """Apply the explicit RCS08 Stage 1-3 scoring and QC contract."""

    surveys = pd.DataFrame(index=daily.index)
    source_map = {
        "record_id": "participant_id",
        "redcap_event_name": "source_event",
        "redcap_repeat_instrument": "source_instrument",
        "redcap_repeat_instance": "repeat_instance",
        SURVEY_START_COLUMN: "survey_start",
        SURVEY_END_COLUMN: "survey_end",
        SURVEY_COMPLETE_COLUMN: "survey_complete",
        "completed_by_s1_daily": "completed_by",
        "pain_nrs_s1_daily": "nrs_intensity",
        "pain_vas_s1_daily": "vas_intensity_raw",
        "left_leg_vas_s1_daily": "left_leg_vas_intensity",
        "back_vas_s1_daily": "back_vas_intensity",
        "relief_vas_s1_daily": "relief_vas",
        "mood_vas_s1_daily": "mood_vas",
        "mpq_s1_daily": "mpq_redcap_expanded_0_54",
        "shortform_s1_daily": "pain_description",
    }
    for source, target in source_map.items():
        surveys[target] = daily[source]

    surveys["repeat_instance"] = pd.to_numeric(surveys["repeat_instance"], errors="coerce").astype(
        "Int64"
    )
    surveys["survey_start"] = pd.to_datetime(surveys["survey_start"], errors="coerce")
    surveys["survey_end"] = pd.to_datetime(surveys["survey_end"], errors="coerce")
    surveys["timestamp_source"] = "redcap"

    corrections_file = Path(corrections_path).expanduser()
    if corrections_file.is_file():
        corrections = pd.read_csv(corrections_file)
        required = {
            "repeat_instance",
            "entered_survey_start",
            "corrected_survey_start",
            "correction_reason",
        }
        missing = sorted(required - set(corrections))
        if missing:
            raise ValueError(f"Timestamp corrections are missing columns: {missing}")
        if corrections.duplicated(["repeat_instance", "entered_survey_start"]).any():
            raise ValueError("Timestamp corrections contain duplicate survey identities")
        corrections["entered_survey_start"] = pd.to_datetime(
            corrections["entered_survey_start"], errors="raise"
        )
        corrections["corrected_survey_start"] = pd.to_datetime(
            corrections["corrected_survey_start"], errors="raise"
        )
        for correction in corrections.itertuples(index=False):
            mask = surveys["repeat_instance"].eq(correction.repeat_instance)
            mask &= surveys["survey_start"].eq(correction.entered_survey_start)
            if int(mask.sum()) != 1:
                raise ValueError(
                    f"Expected exactly one survey for timestamp correction; found {int(mask.sum())}"
                )
            surveys.loc[mask, "survey_start"] = correction.corrected_survey_start
            surveys.loc[mask, "survey_end"] = pd.NaT
            surveys.loc[mask, "timestamp_source"] = "qualtrics_correction"

    surveys["survey_duration_min"] = (
        surveys["survey_end"] - surveys["survey_start"]
    ).dt.total_seconds() / 60
    if surveys["survey_duration_min"].lt(0).any():
        raise ValueError("REDCap contains a survey ending before it started")

    numeric_columns = [
        "survey_complete",
        "nrs_intensity",
        "vas_intensity_raw",
        "left_leg_vas_intensity",
        "back_vas_intensity",
        "relief_vas",
        "mood_vas",
        "mpq_redcap_expanded_0_54",
    ]
    for column in numeric_columns:
        surveys[column] = pd.to_numeric(surveys[column], errors="coerce")
    for column, lower, upper in [
        ("nrs_intensity", 0, 10),
        ("vas_intensity_raw", 0, 100),
        ("left_leg_vas_intensity", 0, 100),
        ("back_vas_intensity", 0, 100),
        ("relief_vas", 0, 100),
        ("mood_vas", 0, 100),
    ]:
        invalid = surveys[column].notna() & ~surveys[column].between(lower, upper)
        if invalid.any():
            raise ValueError(f"REDCap {column} contains values outside {lower}-{upper}")
    invalid_completion = surveys["survey_complete"].notna() & ~surveys["survey_complete"].isin(
        {0, 1, 2}
    )
    if invalid_completion.any():
        raise ValueError("REDCap survey completion contains an unexpected status")

    raw_standard = daily[[f"{name}_s1_daily" for name in STANDARD_MPQ]].apply(
        pd.to_numeric, errors="coerce"
    )
    raw_standard.columns = [f"mpq_{name}" for name in STANDARD_MPQ]
    if ((raw_standard.notna()) & ~raw_standard.isin({1, 2, 3})).any().any():
        raise ValueError("REDCap standard MPQ items contain values outside 1-3")
    standard_present = raw_standard.notna().sum(axis=1)
    scored_standard = raw_standard.fillna(0).where(standard_present.gt(0))
    for column in scored_standard:
        surveys[column] = scored_standard[column]

    raw_extra = daily[[f"{name}_s1_daily" for name in EXTRA_MPQ]].apply(
        pd.to_numeric, errors="coerce"
    )
    raw_extra.columns = EXTRA_MPQ
    if ((raw_extra.notna()) & ~raw_extra.isin({1, 2, 3})).any().any():
        raise ValueError("REDCap extra MPQ items contain values outside 1-3")
    for column in EXTRA_MPQ:
        surveys[column] = (
            raw_extra[column].fillna(0).where(standard_present.gt(0) | raw_extra[column].notna())
        )

    surveys["mpq_sens"] = surveys[[f"mpq_{name}" for name in SENSORY_MPQ]].sum(axis=1, min_count=1)
    surveys["mpq_aff"] = surveys[[f"mpq_{name}" for name in AFFECTIVE_MPQ]].sum(axis=1, min_count=1)
    surveys["mpq_standard_0_45"] = surveys[[f"mpq_{name}" for name in STANDARD_MPQ]].sum(
        axis=1, min_count=1
    )
    surveys["mpq_block_missing"] = standard_present.eq(0)

    recomputed_expanded = surveys["mpq_standard_0_45"] + surveys[EXTRA_MPQ].sum(axis=1, min_count=3)
    compare = surveys["mpq_redcap_expanded_0_54"].notna() & recomputed_expanded.notna()
    if (
        not surveys.loc[compare, "mpq_redcap_expanded_0_54"]
        .eq(recomputed_expanded.loc[compare])
        .all()
    ):
        raise ValueError("Stored Stage 1-3 expanded MPQ totals do not match the 18 items")

    value_corrections_file = (
        Path(value_corrections_path).expanduser() if value_corrections_path is not None else None
    )
    if value_corrections_file is not None and value_corrections_file.is_file():
        value_corrections = pd.read_csv(value_corrections_file)
        required = {
            "repeat_instance",
            "survey_start",
            "canonical_column",
            "entered_value",
            "corrected_value",
            "correction_reason",
        }
        missing = sorted(required - set(value_corrections))
        if missing:
            raise ValueError(f"Survey value corrections are missing columns: {missing}")
        identity = ["repeat_instance", "survey_start", "canonical_column"]
        if value_corrections.duplicated(identity).any():
            raise ValueError("Survey value corrections contain duplicate identities")
        value_corrections["survey_start"] = pd.to_datetime(
            value_corrections["survey_start"], errors="raise"
        )
        for value_column in ["entered_value", "corrected_value"]:
            value_corrections[value_column] = pd.to_numeric(
                value_corrections[value_column], errors="raise"
            )

        allowed_columns = {f"mpq_{name}" for name in STANDARD_MPQ} | set(EXTRA_MPQ)
        for correction in value_corrections.itertuples(index=False):
            column = str(correction.canonical_column)
            if column not in allowed_columns:
                raise ValueError(f"Survey value correction column is not supported: {column}")
            if correction.corrected_value not in {0, 1, 2, 3}:
                raise ValueError(f"Survey value correction is outside 0-3: {column}")
            mask = surveys["repeat_instance"].eq(correction.repeat_instance)
            mask &= surveys["survey_start"].eq(correction.survey_start)
            if int(mask.sum()) != 1:
                raise ValueError(
                    f"Expected exactly one survey for value correction; found {int(mask.sum())}"
                )
            current = surveys.loc[mask, column].iloc[0]
            if pd.isna(current) or current not in {
                correction.entered_value,
                correction.corrected_value,
            }:
                raise ValueError(
                    f"Survey value correction expected {column} to be "
                    f"{correction.entered_value} or {correction.corrected_value}; found {current}"
                )
            surveys.loc[mask, column] = correction.corrected_value

        surveys["mpq_sens"] = surveys[[f"mpq_{name}" for name in SENSORY_MPQ]].sum(
            axis=1, min_count=1
        )
        surveys["mpq_aff"] = surveys[[f"mpq_{name}" for name in AFFECTIVE_MPQ]].sum(
            axis=1, min_count=1
        )
        surveys["mpq_standard_0_45"] = surveys[
            [f"mpq_{name}" for name in STANDARD_MPQ]
        ].sum(axis=1, min_count=1)
        surveys["mpq_redcap_expanded_0_54"] = surveys["mpq_standard_0_45"] + surveys[
            EXTRA_MPQ
        ].sum(axis=1, min_count=3)

    surveys["vas_default_zero_suspect"] = surveys["vas_intensity_raw"].eq(0) & surveys[
        "nrs_intensity"
    ].ge(7)
    surveys["vas_intensity"] = surveys["vas_intensity_raw"].mask(
        surveys["vas_default_zero_suspect"]
    )

    stages = _load_study_stages(study_stages_path)
    survey_dates = surveys["survey_start"].dt.normalize()
    surveys["study_stage"] = pd.NA
    for stage in stages.itertuples(index=False):
        end = stage.end_date if pd.notna(stage.end_date) else pd.Timestamp.max.normalize()
        surveys.loc[
            survey_dates.between(stage.start_date, end, inclusive="both"), "study_stage"
        ] = stage.stage

    surveys["include_in_analysis"] = True
    surveys["exclusion_reason"] = ""
    _add_exclusion_reason(
        surveys,
        surveys["survey_start"].isna(),
        "missing survey start",
    )
    _add_exclusion_reason(
        surveys,
        surveys["survey_complete"].ne(2),
        "survey incomplete",
    )
    _add_exclusion_reason(
        surveys,
        ~surveys["study_stage"].isin({"stage_1", "stage_2", "stage_3"}),
        "outside Stage 1-3",
    )

    exclusions_file = Path(exclusions_path).expanduser()
    if exclusions_file.is_file():
        exclusions = pd.read_csv(exclusions_file)
        required = {"repeat_instance", "survey_start", "exclusion_reason"}
        missing = sorted(required - set(exclusions))
        if missing:
            raise ValueError(f"Reviewed exclusions are missing columns: {missing}")
        if exclusions.duplicated(["repeat_instance", "survey_start"]).any():
            raise ValueError("Reviewed exclusions contain duplicate survey identities")
        exclusions["survey_start"] = pd.to_datetime(exclusions["survey_start"], errors="raise")
        for exclusion in exclusions.itertuples(index=False):
            mask = surveys["repeat_instance"].eq(exclusion.repeat_instance)
            mask &= surveys["survey_start"].eq(exclusion.survey_start)
            if int(mask.sum()) != 1:
                raise ValueError(
                    f"Expected exactly one survey for reviewed exclusion; found {int(mask.sum())}"
                )
            _add_exclusion_reason(surveys, mask, str(exclusion.exclusion_reason))

    testing_dates = _load_testing_dates(testing_dates_path)
    excluded_dates = set(testing_dates.loc[testing_dates["exclude"], "date"])
    surveys["stim_testing_date"] = survey_dates.isin(excluded_dates)
    _add_exclusion_reason(
        surveys,
        surveys["stim_testing_date"],
        "intentional stimulation-testing day",
    )

    result = (
        surveys[CANONICAL_SURVEY_COLUMNS]
        .sort_values("survey_start", na_position="last")
        .reset_index(drop=True)
    )
    result.attrs["timeline_testing_days"] = sorted(day.date().isoformat() for day in excluded_dates)
    result.attrs["timeline_testing_days_sha256"] = hashlib.sha256(Path(testing_dates_path).read_bytes()).hexdigest()
    return result

def canonicalize_rows(rows, rules_dir=None):
    rules = Path(rules_dir or os.environ.get("RCS08_PROCESSING_RULES", "/run/secrets/rcs08_processing"))
    paths = {name: rules / filename for name, filename in {
        "study_stages_path": "rcs08_study_stages.csv",
        "testing_dates_path": "rcs08_stim_testing_dates.csv",
        "corrections_path": "rcs08_stage1_daily_timestamp_corrections.csv",
        "value_corrections_path": "rcs08_stage1_daily_survey_value_corrections.csv",
        "exclusions_path": "rcs08_stage1_daily_survey_exclusions.csv",
    }.items()}
    for path in paths.values():
        if not path.is_file(): raise ValueError(f"Required reviewed RCS08 rule table is missing: {path.name}")
    study_stages_path = paths["study_stages_path"]
    testing_dates_path = paths["testing_dates_path"]
    corrections_path = paths["corrections_path"]
    value_corrections_path = paths["value_corrections_path"]
    exclusions_path = paths["exclusions_path"]
    record_id = "RCS08"
    redcap = pd.DataFrame.from_records(rows)
    # REDCap JSON uses empty strings while CSV round-trips read those cells as
    # missing. Normalize only genuinely blank strings; numeric zero is retained.
    redcap = redcap.replace(r"^\s*$", pd.NA, regex=True)

    missing = [column for column in DAILY_COLUMNS if column not in redcap]
    if missing:
        raise ValueError(f"REDCap export is missing daily survey columns: {missing}")

    patient = redcap["record_id"].astype("string").eq(record_id)
    repeated = patient & redcap["redcap_repeat_instrument"].eq(DAILY_INSTRUMENT)
    response_columns = [
        column
        for column in DAILY_COLUMNS
        if column
        not in {
            "record_id",
            "redcap_event_name",
            "redcap_repeat_instrument",
            "redcap_repeat_instance",
            SURVEY_START_COLUMN,
            SURVEY_END_COLUMN,
            SURVEY_COMPLETE_COLUMN,
        }
    ]
    has_daily_response = redcap[response_columns].notna().any(axis=1)
    base_event = (
        patient
        & redcap["redcap_repeat_instrument"].isna()
        & redcap[SURVEY_START_COLUMN].notna()
        & redcap[SURVEY_COMPLETE_COLUMN].notna()
        & has_daily_response
    )
    populated_elsewhere = patient & has_daily_response & ~(repeated | base_event)
    if populated_elsewhere.any():
        instruments = sorted(
            redcap.loc[populated_elsewhere, "redcap_repeat_instrument"]
            .fillna("(non-repeating/root)")
            .astype(str)
            .unique()
        )
        raise ValueError(
            f"Stage 1 daily timestamps appeared under unexpected REDCap instruments: {instruments}"
        )

    daily = redcap.loc[repeated | base_event, DAILY_COLUMNS].copy()
    if daily.empty:
        raise ValueError(f"No {DAILY_INSTRUMENT} rows found for {record_id}")
    daily[SURVEY_START_COLUMN] = pd.to_datetime(daily[SURVEY_START_COLUMN], errors="raise")
    daily[SURVEY_END_COLUMN] = pd.to_datetime(daily[SURVEY_END_COLUMN], errors="coerce")
    identity = [
        "record_id",
        "redcap_event_name",
        "redcap_repeat_instrument",
        "redcap_repeat_instance",
    ]
    if daily.duplicated(identity, keep=False).any():
        raise ValueError("REDCap daily survey identity is not unique")
    ignored_non_survey = patient & ~(repeated | base_event)
    result = _canonicalize_daily_surveys(
        daily,
        study_stages_path=study_stages_path,
        testing_dates_path=testing_dates_path,
        corrections_path=corrections_path,
        value_corrections_path=value_corrections_path,
        exclusions_path=exclusions_path,
    )
    result.attrs["ignored_non_survey_rows"] = int(ignored_non_survey.sum())
    return result
