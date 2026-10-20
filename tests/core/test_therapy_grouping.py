"""Prove indexed grouping equals the legacy algorithm on independent synthetic data."""
import copy
import importlib.util
from pathlib import Path
import random

import numpy as np
import pytest

MODULE = Path(__file__).resolve().parents[2] / "BRAVO/modules/therapy_grouping.py"
spec = importlib.util.spec_from_file_location("therapy_grouping", MODULE)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def legacy(rows):
    groups=[]
    for source in np.unique([r["SourceId"] for r in rows]):
        for date in np.unique([r["Date"] for r in rows]):
            for group in np.unique([r["GroupId"] for r in rows]):
                for kind in ("Pre-visit Therapy", "Post-visit Therapy", "Past Therapy"):
                    subset=sorted([r for r in rows if r["GroupId"]==group and r["Date"]==date and r["Type"]==kind and r["SourceId"]==source],key=lambda r:r["Date"])
                    if subset:
                        for extra in subset[1:]:
                            subset[0]["StimulationSettings"].extend(extra["StimulationSettings"])
                            subset[0]["AdaptiveSettings"].extend(extra["AdaptiveSettings"])
                        groups.append(subset[0])
    return groups


def row(source="B", date=2, group="Group_B", kind="Past Therapy", n=0):
    return {"SourceId":source,"Date":date,"GroupId":group,"Type":kind,"Id":str(n),
            "StimulationSettings":[{"current":n}],"AdaptiveSettings":[{"threshold":n}],
            "Unmerged":{"label":str(n)}}


@pytest.mark.parametrize("seed", range(12))
def test_exact_output_equivalence_with_shuffled_duplicates_and_unobserved_combinations(seed):
    rng=random.Random(seed)
    rows=[row(rng.choice(["A","B","C"]),rng.choice([0,2,10]),rng.choice(["Group_A","Group_B"]),rng.choice([*module.THERAPY_TYPES,"Other"]),i) for i in range(90)]
    rng.shuffle(rows); original=copy.deepcopy(rows)
    assert module.group_therapy_rows(rows)==legacy(copy.deepcopy(rows))
    assert rows==original


def test_explicit_output_order_and_stable_first_row_metadata():
    rows=[row("B",1,"A",module.THERAPY_TYPES[0],1),row("A",2,"A",module.THERAPY_TYPES[2],2),
          row("A",1,"B",module.THERAPY_TYPES[0],3),row("A",1,"A",module.THERAPY_TYPES[1],4),
          row("A",1,"A",module.THERAPY_TYPES[0],5),row("A",1,"A",module.THERAPY_TYPES[0],6)]
    out=module.group_therapy_rows(rows)
    assert [r["Id"] for r in out]==["5","4","3","2","1"]
    assert out[0]["StimulationSettings"]==[{"current":5},{"current":6}]
    assert out[0]["AdaptiveSettings"]==[{"threshold":5},{"threshold":6}]
    assert out[0]["Unmerged"]=={"label":"5"}
    assert len(rows[4]["StimulationSettings"])==1


def test_empty_unknown_type_nan_date_and_empty_settings():
    assert module.group_therapy_rows([])==[]
    assert module.group_therapy_rows([row(kind="Other"),row(date=float("nan"))])==[]
    one=row();one["StimulationSettings"]=[];one["AdaptiveSettings"]=[]
    assert module.group_therapy_rows([one,copy.deepcopy(one)])==[one]


def test_sparse_large_input_does_not_enumerate_missing_combinations():
    # The old loop would scan 20k rows for each of 20k x 20k source/date pairs.
    rows=[row(str(n),n,"A",n=n) for n in range(20000)]
    out=module.group_therapy_rows(rows)
    assert len(out)==len(rows)
    assert [r["SourceId"] for r in out]==sorted(r["SourceId"] for r in rows)
