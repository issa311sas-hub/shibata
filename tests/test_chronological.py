from copy import deepcopy
import pandas as pd
import pytest
from shibata.chronological import partition
from shibata.ingestion.contracts import DataError
from test_logistic import CONFIG


def test_boundaries_keep_all_horses_and_outside():
    days=['20250930','20251001','20260630','20260701','20260831','20260901','20260913','20260914']
    rows=pd.DataFrame([dict(race_id=d+'05010101',horse_id=str(h)) for d in days for h in (1,2)])
    parts,coverage=partition(rows.sample(frac=1,random_state=3),CONFIG)
    assert {k:v['races'] for k,v in coverage.items()}==dict(train=2,validation=2,test=2,outside=2)
    assert sum(len(p) for p in parts.values())==len(rows)
    assert all(p.groupby('race_id').size().eq(2).all() for p in parts.values())


def test_overlap_rejected():
    c=deepcopy(CONFIG);c['validation']['start']=c['train']['end_inclusive']
    with pytest.raises(DataError,match='Overlapping'):
        partition(pd.DataFrame([dict(race_id='2026010105010101',horse_id='1')]),c)


def test_duplicate_identity_rejected():
    row=dict(race_id='2026010105010101',horse_id='1')
    with pytest.raises(DataError,match='Duplicate'):partition(pd.DataFrame([row,row]),CONFIG)
