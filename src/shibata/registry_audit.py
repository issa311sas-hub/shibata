"""Check the approved nine-feature implementation against the Phase 3 ledger."""
import argparse
import hashlib
import json
from pathlib import Path

from .ingestion.contracts import require
from .models.logistic import NUMERIC, CATEGORICAL
from .observed_features import FEATURES

COLUMNS = ('feature_name', 'category', 'description', 'formula', 'raw_source',
           'available_time', 'missing_rate', 'leakage_risk', 'hypothesis',
           'implemented', 'validation_result', 'keep_or_drop', 'notes')
SECTION = '## 初期ロジスティック回帰の承認済み特徴量'


def approved_rows(markdown):
    require(markdown.count(SECTION) == 1, 'Approved feature section missing or ambiguous')
    section = markdown.split(SECTION, 1)[1]
    lines = section.splitlines()
    header_index = next((i for i, line in enumerate(lines)
                         if line.strip().startswith('| feature_name |')), None)
    require(header_index is not None, 'Approved feature table missing')
    table = []
    for line in lines[header_index:]:
        if table and not line.strip().startswith('|'):
            break
        if line.strip().startswith('|'):
            table.append([part.strip() for part in line.strip().strip('|').split('|')])
    require(len(table) >= 3 and tuple(table[0]) == COLUMNS and
            all(len(row) == len(COLUMNS) for row in table), 'Ledger needs all 13 columns')
    rows = [dict(zip(COLUMNS, values)) for values in table[2:]]
    require(all(all(row[column] for column in COLUMNS) for row in rows),
            'Blank approved feature ledger field')
    names = [row['feature_name'] for row in rows]
    require(len(names) == len(set(names)) and set(names) == set(FEATURES),
            'Approved ledger differs from implemented features')
    return rows


def audit(registry_path: Path, config_path: Path):
    ledger_bytes, config_bytes = registry_path.read_bytes(), config_path.read_bytes()
    rows = approved_rows(ledger_bytes.decode('utf-8-sig'))
    config = json.loads(config_bytes.decode('utf-8-sig'))
    require(config['features'] == FEATURES and set(NUMERIC+CATEGORICAL) == set(FEATURES) and
            len(NUMERIC+CATEGORICAL) == len(FEATURES),
            'Feature config/preprocessor differs from approved ledger')
    return dict(status='PASS', phase_promotion=False, features=FEATURES,
                ledger_columns=list(COLUMNS), ledger_rows=len(rows),
                registry_sha256=hashlib.sha256(ledger_bytes).hexdigest(),
                config_sha256=hashlib.sha256(config_bytes).hexdigest(),
                scope='approved nine features only; no performance or availability certification')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, default=Path('docs/feature-registry.md'))
    parser.add_argument('--config', type=Path, default=Path('configs/logistic-initial-v1.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.registry, args.config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
