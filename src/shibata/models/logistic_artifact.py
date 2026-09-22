"""Portable coefficient-only logistic artifacts; no executable object deserialization."""
import hashlib
import json
import re
import numpy as np
from scipy.special import expit
from .logistic import NUMERIC,CATEGORICAL,FEATURES,validate,design
from ..ingestion.contracts import require


def save(model,path,*,config_sha256,dataset_sha256):
    require(all(re.fullmatch('[0-9a-f]{64}',x) for x in (config_sha256,dataset_sha256)), 'Expected source hashes')
    prep=model.named_steps['preprocess'];classifier=model.named_steps['classifier']
    require(classifier.classes_.tolist()==[0,1],'Unexpected classes')
    scaler=prep.named_transformers_['numeric'];encoder=prep.named_transformers_['categorical']
    artifact=dict(format='shibata-logistic-v1',features=FEATURES,numeric=NUMERIC,categorical=CATEGORICAL,
                  means=scaler.mean_.tolist(),scales=scaler.scale_.tolist(),
                  categories=[c.tolist() for c in encoder.categories_],
                  coefficients=classifier.coef_[0].tolist(),intercept=float(classifier.intercept_[0]),
                  config_sha256=config_sha256,dataset_sha256=dataset_sha256,
                  normalization='binary_probability_divided_by_race_sum')
    raw=json.dumps(artifact,indent=2,allow_nan=False).encode('utf-8')
    with path.open('xb') as stream:stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def load(path,expected_sha256):
    raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==expected_sha256,'Model hash mismatch')
    a=json.loads(raw)
    require(a['format']=='shibata-logistic-v1' and a['features']==FEATURES and
            a['numeric']==NUMERIC and a['categorical']==CATEGORICAL,'Unexpected model schema')
    require(a['normalization']=='binary_probability_divided_by_race_sum','Unexpected normalization')
    require(len(a['means'])==len(a['scales'])==len(NUMERIC),'Invalid scaler dimensions')
    require(len(a['categories'])==len(CATEGORICAL) and
            all(isinstance(c,list) and c and all(isinstance(v,str) for v in c)
                and len(c)==len(set(c)) for c in a['categories']),'Invalid categories')
    require(len(a['coefficients'])==len(NUMERIC)+sum(map(len,a['categories'])),'Invalid coefficient dimensions')
    require(np.isfinite(a['means']+a['scales']+a['coefficients']+[a['intercept']]).all()
            and (np.asarray(a['scales'])>0).all(),'Invalid numeric parameters')
    return a


def predict_saved(artifact,frame):
    validate(frame)
    x=design(frame)
    numeric=(x[NUMERIC].to_numpy(dtype=float)-artifact['means'])/artifact['scales']
    encoded=[(x[name].to_numpy()[:,None]==np.asarray(categories)[None,:]).astype(float)
             for name,categories in zip(CATEGORICAL,artifact['categories'])]
    matrix=np.concatenate([numeric,*encoded],axis=1)
    raw=expit(matrix@np.asarray(artifact['coefficients'])+artifact['intercept'])
    require(np.isfinite(raw).all() and (raw>0).all(),'Invalid saved-model probabilities')
    out=frame[['race_id','horse_id']].copy();out['raw_probability']=raw
    out['probability']=out.raw_probability/out.groupby('race_id').raw_probability.transform('sum')
    return out
