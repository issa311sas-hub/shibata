import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip('lightgbm')
pytest.importorskip('catboost')

from shibata.ingestion.contracts import DataError
from shibata.evaluation.compare import SCORES
from shibata.observed_features import build
from shibata.models.tree_rehearsal import fit_synthetic, load, predict, save
from shibata.phase2_rehearsal import run
from shibata.synthetic_jv import assemble

CONFIG = Path(__file__).resolve().parents[1]/'configs'/'logistic-initial-v1.json'


@pytest.mark.parametrize('name', ['lightgbm', 'catboost'])
def test_tree_saved_prediction_matches_fit_and_unknown_category(name, tmp_path):
    config = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
    dataset, _, _ = assemble(tmp_path/'raw')
    train = dataset.query("race_id.str.startswith('20260101') or race_id.str.startswith('20260201')")
    model, prep = fit_synthetic(train, config, name)
    means = prep.named_transformers_['numeric'].mean_.copy()
    check = train.copy()
    check['age'] = 99
    check['surface'] = 'unseen'
    direct = predict(model, check, prep=prep, name=name)
    pin = save(model, prep, tmp_path/name, name, config_sha='a'*64, dataset_sha='b'*64)
    restored, meta = load(tmp_path/name, pin, name)
    saved = predict(restored, check, meta=meta, name=name)
    np.testing.assert_allclose(saved.probability, direct.probability, rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(means, prep.named_transformers_['numeric'].mean_)
    np.testing.assert_allclose(saved.groupby('race_id').probability.sum(), 1)
    with pytest.raises(DataError, match='hash mismatch'):
        load(tmp_path/name, '0'*64, name)
    native = tmp_path/name/('model.txt' if name == 'lightgbm' else 'model.cbm')
    native.write_bytes(native.read_bytes()+b'altered')
    with pytest.raises(DataError, match='hash mismatch'):
        load(tmp_path/name, pin, name)


@pytest.mark.parametrize('change', ['validation_date', 'test_date', 'missing', 'winner', 'coverage'])
def test_tree_fit_rejects_invalid_or_future_training_rows(change, tmp_path):
    config = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
    dataset, _, _ = assemble(tmp_path/'raw')
    frame = dataset.query("race_id.str.startswith('20260101') or race_id.str.startswith('20260201')").copy()
    if change == 'validation_date': frame['race_id'] = frame.race_id.str.replace('20260101', '20260701')
    if change == 'test_date': frame['race_id'] = frame.race_id.str.replace('20260101', '20260912')
    if change == 'missing': frame.loc[frame.index[0], 'age'] = None
    if change == 'winner': frame['win'] = 0
    if change == 'coverage': frame = frame.iloc[:-1]
    with pytest.raises(DataError):
        fit_synthetic(frame, config, 'lightgbm')


def test_three_models_exact_same_market_population_and_no_test(tmp_path):
    status = run(CONFIG, tmp_path/'first')
    assert status['status'] == 'PASS' and not status['real_data_used']
    assert not status['test_evaluated'] and not status['phase_promotion']
    assert status['coverage']['train'] == {'rows': 8, 'races': 2}
    assert status['coverage']['validation'] == {'rows': 4, 'races': 1}
    assert status['coverage']['test'] == {'rows': 0, 'races': 0}
    scores = json.loads((tmp_path/'first'/'comparison.json').read_text())
    import pandas as pd
    features = pd.read_csv(tmp_path/'first'/'synthetic-features.csv')
    labels = pd.read_csv(tmp_path/'first'/'synthetic-labels.csv')
    assert 'win' not in features and set(labels) == {'race_id', 'horse_id', 'win'}
    assert status['output_sha256']['synthetic-jv/2026070105010101/entries/probe.json']
    assert set(scores) == {'logistic_regression', 'lightgbm', 'catboost'}
    assert len({tuple(sorted(v['market'].items())) for v in scores.values()}) == 1
    for name in scores:
        metric = json.loads((tmp_path/'first'/f'{name}-metrics.json').read_text())
        assert metric['model'] == scores[name]['model']
        assert metric['market'] == scores[name]['market']
    second = run(CONFIG, tmp_path/'second')
    for name in ('synthetic-labels.csv', 'synthetic-features.csv', 'synthetic-dataset.csv'):
        assert hashlib.sha256((tmp_path/'first'/name).read_bytes()).hexdigest() == second['output_sha256'][name]
    repeated = json.loads((tmp_path/'second'/'comparison.json').read_text())
    for name in scores:
        assert scores[name]['market'] == repeated[name]['market']
        for scope in ('model', 'market', 'model_minus_market'):
            for metric in SCORES:
                assert repeated[name][scope][metric] == pytest.approx(
                    scores[name][scope][metric], abs=1e-12)
    with pytest.raises(FileExistsError):
        run(CONFIG, tmp_path/'first')


def test_tampered_jv_record_is_rejected_before_feature_assembly(tmp_path):
    assemble(tmp_path/'raw')
    folder = tmp_path/'raw'/'2026010105010101'
    entry = folder/'entries'/'record-0001.bin'
    original = entry.read_bytes()
    entry.write_bytes(original[:-3]+b'x'+original[-2:])
    with pytest.raises(DataError, match='hash mismatch'):
        build(folder/'entries', folder/'odds', '2026-01-01T11:50:00+09:00')
