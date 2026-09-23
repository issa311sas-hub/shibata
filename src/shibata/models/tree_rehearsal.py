"""Synthetic-only tree model adapters with hash-pinned native artifacts."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .logistic import CATEGORICAL, NUMERIC, design, validate
from ..ingestion.contracts import require
from ..observed_features import FEATURES

MODELS = ('lightgbm', 'catboost')


def _matrix(frame, prep):
    values = prep.transform(design(frame))
    return np.asarray(values.toarray() if hasattr(values, 'toarray') else values, dtype=float)


def fit_synthetic(frame, config, name):
    require(name in MODELS and config['features'] == FEATURES and
            config['model'] == 'logistic_regression' and
            config['status'] == 'APPROVED_PREPARATION' and
            config['training_enabled'] is False, 'Synthetic-only tree preparation')
    validate(frame)
    dates = pd.to_datetime(frame.race_id.str[:8], format='%Y%m%d').dt.strftime('%Y-%m-%d')
    require(dates.between(config['train']['start'], config['train']['end_inclusive']).all(),
            'Fit accepts training dates only')
    require(frame.win.isin([0, 1]).all() and frame.groupby('race_id').win.sum().eq(1).all(),
            'Exactly one winner per training race required')
    prep = ColumnTransformer([
        ('numeric', StandardScaler(), NUMERIC),
        ('categorical', OneHotEncoder(handle_unknown='ignore'), CATEGORICAL),
    ])
    prep.fit(design(frame))
    x, y = _matrix(frame, prep), frame.win.astype(int)
    if name == 'lightgbm':
        from lightgbm import LGBMClassifier
        model = LGBMClassifier(n_estimators=24, max_depth=3, num_leaves=5,
                               min_child_samples=1, learning_rate=0.05,
                               random_state=0, n_jobs=1, verbosity=-1)
    else:
        from catboost import CatBoostClassifier
        model = CatBoostClassifier(iterations=24, depth=3, learning_rate=0.05,
                                   random_seed=0, thread_count=1, verbose=False,
                                   allow_writing_files=False)
    model.fit(x, y)
    return model, prep


def _metadata(prep, name, config_sha, dataset_sha):
    scaler = prep.named_transformers_['numeric']
    encoder = prep.named_transformers_['categorical']
    return dict(format='shibata-synthetic-tree-v1', name=name, features=FEATURES,
                numeric=NUMERIC, categorical=CATEGORICAL, means=scaler.mean_.tolist(),
                scales=scaler.scale_.tolist(),
                categories=[c.tolist() for c in encoder.categories_],
                config_sha256=config_sha, dataset_sha256=dataset_sha,
                normalization='binary_probability_divided_by_race_sum',
                synthetic_only=True)


def save(model, prep, folder: Path, name, *, config_sha, dataset_sha):
    require(name in MODELS and not folder.exists(), 'New model folder required')
    folder.mkdir(parents=True)
    native = folder/('model.txt' if name == 'lightgbm' else 'model.cbm')
    if name == 'lightgbm':
        model.booster_.save_model(str(native))
    else:
        model.save_model(str(native), format='cbm')
    meta = _metadata(prep, name, config_sha, dataset_sha)
    meta['native_sha256'] = hashlib.sha256(native.read_bytes()).hexdigest()
    raw = json.dumps(meta, indent=2, allow_nan=False).encode('utf-8')
    (folder/'metadata.json').write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def load(folder: Path, expected_meta_sha: str, name):
    require(name in MODELS, 'Unknown model')
    raw = (folder/'metadata.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected_meta_sha, 'Metadata hash mismatch')
    meta = json.loads(raw)
    require(meta['format'] == 'shibata-synthetic-tree-v1' and meta['name'] == name and
            meta['synthetic_only'] is True and meta['features'] == FEATURES and
            meta['numeric'] == NUMERIC and meta['categorical'] == CATEGORICAL and
            meta['normalization'] == 'binary_probability_divided_by_race_sum',
            'Unexpected model metadata')
    require(len(meta['means']) == len(meta['scales']) == len(NUMERIC) and
            len(meta['categories']) == len(CATEGORICAL) and
            all(len(c) > 0 and len(c) == len(set(c)) for c in meta['categories']),
            'Invalid preprocessing shape')
    require(np.isfinite(meta['means'] + meta['scales']).all() and
            (np.asarray(meta['scales']) > 0).all(), 'Invalid preprocessing values')
    native = folder/('model.txt' if name == 'lightgbm' else 'model.cbm')
    require(hashlib.sha256(native.read_bytes()).hexdigest() == meta['native_sha256'],
            'Native model hash mismatch')
    if name == 'lightgbm':
        from lightgbm import Booster
        model = Booster(model_file=str(native))
    else:
        from catboost import CatBoostClassifier
        model = CatBoostClassifier()
        model.load_model(str(native))
    return model, meta


def _saved_matrix(frame, meta):
    x = design(frame)
    numeric = (x[NUMERIC].to_numpy(dtype=float) - meta['means'])/meta['scales']
    encoded = [(x[name].to_numpy()[:, None] == np.asarray(categories)[None, :]).astype(float)
               for name, categories in zip(CATEGORICAL, meta['categories'])]
    return np.concatenate([numeric, *encoded], axis=1)


def predict(model, frame, *, prep=None, meta=None, name):
    validate(frame)
    require(name in MODELS and ((prep is None) != (meta is None)),
            'Specify exactly one preprocessing source')
    x = _matrix(frame, prep) if prep is not None else _saved_matrix(frame, meta)
    raw = (model.booster_.predict(x) if name == 'lightgbm' and prep is not None
           else model.predict(x) if name == 'lightgbm'
           else model.predict_proba(x)[:, 1])
    require(np.isfinite(raw).all() and (raw > 0).all() and (raw < 1).all(),
            'Invalid tree probabilities')
    out = frame[['race_id', 'horse_id']].copy()
    out['raw_probability'] = raw
    out['probability'] = out.raw_probability/out.groupby('race_id').raw_probability.transform('sum')
    return out
