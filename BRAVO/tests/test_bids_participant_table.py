"""The participant-table append preserves the exported schema and existing values."""
import json

import pandas as pd
import pytest

from modules.BIDSExport.Convert import upsert_participant


@pytest.mark.parametrize("existing", [
    None,
    "participant_id\tage\tsex\tdiagnosis\n",
    "participant_id\tage\tsex\tdiagnosis\nsub-001\t63\tM\tPD\n",
    "participant_id\tage\tsex\tdiagnosis\nsub-001\tn/a\tn/a\tn/a\n",
    "participant_id\tage\tsex\tdiagnosis\nsub-002\t42\tM\told\n",
    "participant_id\tage\tname\nsub-001\t63\tprivate fixture\n",
])
@pytest.mark.parametrize("age", [None, 0, 37, 37.5, "37.0"])
@pytest.mark.parametrize("sex,diagnosis", [(None, None), ("F", "synthetic")])
def test_append_matches_prior_export_bytes(tmp_path, existing, age, sex, diagnosis):
    path = tmp_path / "participants.tsv"
    columns = ["participant_id", "age", "sex", "diagnosis"]
    if existing is not None:
        path.write_text(existing)
        previous = pd.read_csv(path, sep="\t", dtype=str)
        previous = previous[previous["participant_id"] != "sub-002"].reindex(columns=columns)
    else:
        previous = pd.DataFrame(columns=columns)
    # Keep the prior implementation as an independent serialization oracle.
    expected = pd.concat([previous, pd.DataFrame([{
        "participant_id": "sub-002", "age": age if age is not None else "n/a",
        "sex": sex or "n/a", "diagnosis": diagnosis or "n/a",
    }])], ignore_index=True).to_csv(sep="\t", index=False, na_rep="n/a")
    upsert_participant(str(tmp_path), "002", age, sex, diagnosis)
    assert path.read_text() == expected
    assert "private fixture" not in path.read_text()
    assert list(pd.read_csv(path, sep="\t").columns) == columns
    assert set(json.loads((tmp_path / "participants.json").read_text())) == {"age", "sex", "diagnosis"}
    upsert_participant(str(tmp_path), "002", age, sex, diagnosis)
    assert path.read_text() == expected
