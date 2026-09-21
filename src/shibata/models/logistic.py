"""Initial logistic model core. Callers must supply verified feature/label datasets."""
import warnings
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.exceptions import ConvergenceWarning
from ..observed_features import FEATURES
from ..ingestion.contracts import require

NUMERIC=['age','horse_number','runner_count','distance','carried_weight']
CATEGORICAL=['sex','bracket_number','surface','venue']


def validate(frame):
    require(len(frame)>0 and not frame[FEATURES+['race_id','horse_id']].isna().any().any(),'Missing model inputs')
    require(not frame.duplicated(['race_id','horse_id']).any(),'Duplicate horse row')
    require(np.isfinite(frame[NUMERIC].to_numpy(dtype=float)).all(),'Nonfinite model inputs')
    for _,race in frame.groupby('race_id'):
        require(race.runner_count.nunique()==1 and race.runner_count.iloc[0]==len(race)
                and 2<=len(race)<=18,'Incomplete race population')
        require(race.horse_number.nunique()==len(race),'Duplicate horse number')


def design(frame):
    values=frame[FEATURES].copy()
    for name in CATEGORICAL: values[name]=values[name].astype(str)
    return values


def fit_training(frame,config):
    validate(frame)
    require(config['features']==FEATURES and config['model']=='logistic_regression','Unexpected model scope')
    dates=pd.to_datetime(frame['race_id'].str[:8],format='%Y%m%d',errors='raise').dt.strftime('%Y-%m-%d')
    require(dates.between(config['train']['start'],config['train']['end_inclusive']).all(),
            'Fit accepts training dates only')
    require(frame['win'].isin([0,1]).all(),'Invalid label')
    require(frame.groupby('race_id').win.sum().eq(1).all(),'Exactly one winner required')
    prep=ColumnTransformer([('numeric',StandardScaler(),NUMERIC),
                            ('categorical',OneHotEncoder(handle_unknown='ignore'),CATEGORICAL)])
    model=Pipeline([('preprocess',prep),('classifier',LogisticRegression(C=1.0,solver='lbfgs',max_iter=1000))])
    with warnings.catch_warnings():
        warnings.simplefilter('error',ConvergenceWarning)
        model.fit(design(frame),frame['win'].astype(int))
    return model


def predict(model,frame):
    validate(frame)
    raw=model.predict_proba(design(frame))[:,1]
    require(np.isfinite(raw).all() and (raw>0).all(),'Invalid logistic probabilities')
    result=frame[['race_id','horse_id']].copy()
    result['raw_probability']=raw
    result['probability']=result.raw_probability/result.groupby('race_id').raw_probability.transform('sum')
    return result
