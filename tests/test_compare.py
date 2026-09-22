import pandas as pd
import pytest
from shibata.evaluation.compare import compare
from shibata.ingestion.contracts import DataError


def data():
    market=pd.DataFrame(dict(race_id=['race1']*2,horse_id=['h1','h2'],market_probability=[.6,.4],
        start_at=[pd.Timestamp('2026-01-01T12:00:00+09:00')]*2,
        win_odds=[2.,3.],popularity=[1,2],odds_rank=[1,2]))
    model=market[['race_id','horse_id']].copy();model['probability']=[.8,.2]
    results=pd.DataFrame(dict(race_id=['race1']*2,horse_id=['h1','h2'],win=[1,0],
        result_status=['official']*2,result_observed_at=['2026-01-01T13:00:00+09:00']*2))
    return model,market,results


def test_identical_population_and_manual_brier():
    m,b,y=data();metrics,tables=compare(m.iloc[::-1],b,y)
    assert metrics['model']['binary_brier_per_runner']==pytest.approx(.04)
    assert metrics['market']['binary_brier_per_runner']==pytest.approx(.16)
    assert metrics['model_minus_market']['binary_brier_per_runner']==pytest.approx(-.12)
    assert metrics['model']['roi'] is None
    assert set(tables['model'])==set(tables['market'])


@pytest.mark.parametrize('bad',['missing','duplicate','probability','result_missing'])
def test_comparison_rejects_invalid_or_selected_population(bad):
    m,b,y=data()
    if bad=='missing':m=m.iloc[:1]
    if bad=='duplicate':m=pd.concat([m,m.iloc[:1]])
    if bad=='probability':m['probability']=[.8,.8]
    if bad=='result_missing':y=y.iloc[:1]
    with pytest.raises(DataError):compare(m,b,y)
