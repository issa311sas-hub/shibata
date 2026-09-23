import json
from pathlib import Path

import pytest

from shibata.registry_audit import audit, approved_rows
from shibata.ingestion.contracts import DataError

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT/'docs/feature-registry.md'
CONFIG = ROOT/'configs/logistic-initial-v1.json'


def test_approved_features_have_all_13_ledger_fields_and_match_code(tmp_path):
    result = audit(REGISTRY, CONFIG)
    assert result['status'] == 'PASS' and result['ledger_rows'] == 9
    assert len(result['ledger_columns']) == 13 and not result['phase_promotion']
    assert len(approved_rows(REGISTRY.read_text(encoding='utf-8-sig'))) == 9


@pytest.mark.parametrize('change', ['missing_feature', 'empty_available_time', 'duplicate', 'short_row'])
def test_ledger_drift_is_rejected(change):
    raw = REGISTRY.read_text(encoding='utf-8-sig')
    start = raw.index('## 初期ロジスティック回帰の承認済み特徴量')
    end = raw.index('## ロジスティック回帰の前処理', start)
    section = raw[start:end]
    lines = section.splitlines()
    position = next(i for i, line in enumerate(lines) if line.startswith('| age |'))
    if change == 'missing_feature': lines.pop(position)
    if change == 'duplicate': lines.insert(position, lines[position])
    if change == 'short_row': lines[position] = lines[position].rsplit('|', 2)[0]+' |'
    if change == 'empty_available_time':
        cells = lines[position].split('|')
        cells[6] = ' '
        lines[position] = '|'.join(cells)
    with pytest.raises(DataError):
        approved_rows(raw[:start]+'\n'.join(lines)+raw[end:])


def test_config_feature_change_does_not_pass(tmp_path):
    config = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
    config['features'][0] = 'future_rank'
    path = tmp_path/'config.json'; path.write_text(json.dumps(config))
    with pytest.raises(DataError):
        audit(REGISTRY, path)
