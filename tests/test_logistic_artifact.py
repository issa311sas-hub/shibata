import json
import hashlib
import numpy as np
import pytest
from shibata.models.logistic import fit_training,predict
from shibata.models.logistic_artifact import save,load,predict_saved
from shibata.ingestion.contracts import DataError
from test_logistic import sample,CONFIG


def test_round_trip_matches_sklearn_on_unseen_categories(tmp_path):
    train=sample();model=fit_training(train,CONFIG);p=tmp_path/'model.json'
    digest=save(model,p,config_sha256='a'*64,dataset_sha256='b'*64)
    evaluation=train.copy();evaluation.loc[0,'surface']='unseen';evaluation.loc[1,'age']=12
    expected=predict(model,evaluation);actual=predict_saved(load(p,digest),evaluation)
    np.testing.assert_allclose(actual.raw_probability,expected.raw_probability,rtol=1e-12)
    np.testing.assert_allclose(actual.probability,expected.probability,rtol=1e-12)
    with pytest.raises(FileExistsError):save(model,p,config_sha256='a'*64,dataset_sha256='b'*64)
    p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(DataError,match='hash'):load(p,digest)

@pytest.mark.parametrize('bad',['scale','dimension','categories'])
def test_corrupt_parameters_rejected(tmp_path,bad):
    p=tmp_path/'model.json';save(fit_training(sample(),CONFIG),p,config_sha256='a'*64,dataset_sha256='b'*64)
    a=json.loads(p.read_text())
    if bad=='scale':a['scales'][0]=0
    if bad=='dimension':a['coefficients'].pop()
    if bad=='categories':a['categories'][0].append(a['categories'][0][0])
    p.write_text(json.dumps(a));digest=hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(DataError):load(p,digest)
