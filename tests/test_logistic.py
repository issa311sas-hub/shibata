import json
from pathlib import Path
import pandas as pd
import numpy as np
import pytest
from shibata.models.logistic import fit_training,predict,NUMERIC
from shibata.ingestion.contracts import DataError

CONFIG=json.loads((Path(__file__).parents[1]/'configs/logistic-initial-v1.json').read_text(encoding='utf-8-sig'))

def sample():
    return pd.DataFrame([dict(race_id=f'202601010501010{r}',horse_id=f'{r}{h}',age=2+h,sex='1',
        bracket_number=h,horse_number=h,runner_count=3,distance=1600,surface='turf',venue='05',
        carried_weight=55.0,win=int(h==1)) for r in (1,2) for h in (1,2,3)])

def test_training_only_preprocessing_and_normalization():
    train=sample();model=fit_training(train,CONFIG)
    means=model.named_steps['preprocess'].named_transformers_['numeric'].mean_.copy()
    validation=train.copy();validation['age']=99;validation['surface']='unseen';validation['win']=1
    out=predict(model,validation)
    assert np.allclose(out.groupby('race_id').probability.sum(),1)
    assert np.array_equal(means,model.named_steps['preprocess'].named_transformers_['numeric'].mean_)
    assert np.allclose(means,train[NUMERIC].mean())

@pytest.mark.parametrize('change',['test','validation','missing','winner','population'])
def test_invalid_fit_rejected(change):
    frame=sample()
    if change in {'test','validation'}:
        frame['race_id']=frame.race_id.str.replace('20260101','20260912' if change=='test' else '20260701')
    if change=='missing':frame.loc[0,'age']=None
    if change=='winner':frame['win']=0
    if change=='population':frame=frame.iloc[:-1]
    with pytest.raises(DataError):fit_training(frame,CONFIG)
