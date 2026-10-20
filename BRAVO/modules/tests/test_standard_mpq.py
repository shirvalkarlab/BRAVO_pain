"""Synthetic standard-MPQ aggregate and source-binding regressions."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("standard_mpq_under_test", Path(__file__).parents[1] / "SurveyForms" / "StandardMPQ.py")
mpq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mpq)


def mapping():
    return {"instruments": ["stage_1_daily_surveys_vasnrsmpq"],
            "timestamp_label": "date_time_s1_daily",
            "metric_labels": {"mpq_sen": list(mpq.SENSORY), "mpq_aff": list(mpq.AFFECTIVE),
                              "mpq_sum": "mpq_s1_daily"}}


def test_exact_item_derivation_preserves_rows_legacy_and_extras():
    source = [{"_pro_time_utc": "same-time", "mpq_sen": 33, "mpq_aff": 12, "mpq_sum": 54,
               "electrocuting": 3, "tingly": 3},
              {"_pro_time_utc": "same-time", "mpq_sen": 2, "mpq_aff": 1, "mpq_sum": 12}]
    original = deepcopy(source)
    actual, audit = mpq.derive(source, mapping())
    assert source == original
    assert [row["mpq_standard_0_45"] for row in actual] == [45, 3]
    assert [row["mpq_sum"] for row in actual] == [54, 12]
    assert actual[0]["mpq_standard_sensory_0_33"] == 33
    assert actual[0]["mpq_standard_affective_0_12"] == 12
    assert audit["derived_rows"] == 2 and audit["mapping_verified"]
    assert not audit["completion_status_available"] and not audit["item_level_validation_available"]
    assert actual[0]["_pro_time_utc"] == actual[1]["_pro_time_utc"]


@pytest.mark.parametrize("sensory,affective,expected", [(None,None,None), (None,3,3), (2,None,2), (0,0,0)])
def test_unselected_items_zero_only_inside_observed_standard_block(sensory, affective, expected):
    actual, audit = mpq.derive([{"mpq_sen": sensory, "mpq_aff": affective}], mapping())
    assert actual[0].get("mpq_standard_0_45") == expected
    assert audit["missing_rows"] == int(expected is None)


@pytest.mark.parametrize("bad", [True,"1",-1,34,1.5,float("nan"),float("inf")])
def test_invalid_aggregate_never_becomes_valid_standard_score(bad):
    actual, audit = mpq.derive([{"mpq_sen": bad, "mpq_aff": 2}], mapping())
    assert "mpq_standard_0_45" not in actual[0]
    assert audit["invalid_rows"] == 1


def test_affective_bound_and_missing_columns():
    actual, audit = mpq.derive([{"mpq_sen": 1, "mpq_aff": 13}, {}], mapping())
    assert all("mpq_standard_0_45" not in row for row in actual)
    assert audit["invalid_rows"] == 1 and audit["missing_rows"] == 1


@pytest.mark.parametrize("change", [
    lambda b: None, lambda b: [], lambda b: {},
    lambda b: {**b,"metric_labels": []},
    lambda b: {**b,"instruments": ["other_form"]},
    lambda b: {**b,"timestamp_label": "other_time"},
    lambda b: {**b,"metric_labels": {**b["metric_labels"],"mpq_sen": None}},
    lambda b: {**b,"metric_labels": {**b["metric_labels"],"mpq_sen": list(mpq.SENSORY)[:-1]}},
    lambda b: {**b,"metric_labels": {**b["metric_labels"],"mpq_sen": [None]*11}},
    lambda b: {**b,"metric_labels": {**b["metric_labels"],"mpq_sen": [mpq.SENSORY[0]]*11}},
    lambda b: {**b,"metric_labels": {**b["metric_labels"],"mpq_aff": ["other"]*4}},
])
def test_unverified_mapping_cannot_claim_standard_or_accept_supplied_derived(change):
    actual, audit = mpq.derive([{"mpq_sen": 1,"mpq_aff": 1,"mpq_standard_0_45": 45}], change(mapping()))
    assert not audit["mapping_verified"]
    assert "mpq_standard_0_45" not in actual[0]
    assert not audit["expanded_total_mapping_verified"]


def test_field_order_does_not_change_item_membership_and_expanded_mapping_is_separate():
    binding = mapping()
    binding["metric_labels"]["mpq_sen"].reverse()
    binding["metric_labels"]["mpq_sum"] = "unverified_total"
    rows, audit = mpq.derive([{"mpq_sen":1,"mpq_aff":2}],binding)
    assert rows[0]["mpq_standard_0_45"] == 3
    assert not audit["expanded_total_mapping_verified"]


def test_display_range_is_bound_to_verified_expanded_mapping_without_rescoring():
    source = {"metrics":[{"key":"mpq_sum","label":"MPQ Sum","range":[0,72],"points":[{"v":51}]},
                         {"key":"nrs","label":"NRS","range":[0,10],"points":[]}]}
    original = deepcopy(source)
    actual = mpq.display_metrics(source, {"expanded_total_mapping_verified":True})
    assert actual["metrics"][0]["range"] == [0,54]
    assert actual["metrics"][0]["points"] == source["metrics"][0]["points"]
    assert source == original
    assert actual["metrics"][1] == source["metrics"][1]
    assert mpq.display_metrics(source,{"expanded_total_mapping_verified":False}) == source
    assert mpq.display_metrics({}, {"expanded_total_mapping_verified":False}) == {"metrics":[]}
