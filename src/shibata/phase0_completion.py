"""Synthetic environment acceptance run; no JRA input or performance claim."""
import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import sys

import numpy as np
import pandas as pd

from .phase0 import run as run_basics
from .phase0_validation import check_later_period


def run(output, notebook):
    output.mkdir(parents=True, exist_ok=False)
    report = dict(status='RUNNING', scope='Phase 0 environment acceptance', real_data=False,
                  model_performance_claim=False, python=platform.python_version(), executable=sys.executable)
    report['operation_source_sha256'] = hashlib.sha256(Path(__file__).with_name('phase0.py').read_bytes()).hexdigest()
    runtime_variables = ['MPLCONFIGDIR', 'IPYTHONDIR', 'JUPYTER_RUNTIME_DIR']
    previous_environment = {name: os.environ.get(name) for name in runtime_variables}
    for name in runtime_variables:
        directory = output.resolve()/'runtime'/name.lower()
        directory.mkdir(parents=True)
        os.environ[name] = str(directory)
    try:
        report['basics'] = run_basics(output/'basics')
        later, report['later_period'] = check_later_period()
        later.to_csv(output/'later-period.csv', index=False)
        later.to_parquet(output/'later-period.parquet', index=False)
        csv = pd.read_csv(output/'later-period.csv', dtype={c: 'string' for c in ['race_id', 'horse_id', 'date']})
        pd.testing.assert_frame_equal(later, csv)
        pd.testing.assert_frame_equal(later, pd.read_parquet(output/'later-period.parquet'))

        import matplotlib
        matplotlib.use('Agg')
        from matplotlib import pyplot as plt
        fig, ax = plt.subplots(figsize=(6, 3.5), layout='constrained')
        for horse, group in later.groupby('horse_id'):
            ax.plot(pd.to_datetime(group.date), group.previous_two_mean, marker='o', label=horse)
        ax.set(xlabel='Synthetic race date', ylabel='Previous two outcomes: mean', ylim=(-.05, 1.05),
               title='Phase 0: shifted history (synthetic data)')
        ax.legend(); fig.autofmt_xdate(); fig.savefig(output/'history.png', dpi=150); plt.close(fig)

        from sklearn.linear_model import LogisticRegression
        from lightgbm import LGBMClassifier
        from catboost import CatBoostClassifier
        x = np.arange(-8, 8, dtype=float).reshape(-1, 1)
        y = (x[:, 0] >= 0).astype(int)
        unseen = np.array([[-5.5], [-.5], [.5], [5.5]])
        models = {
            'scikit-learn': LogisticRegression(random_state=0),
            'lightgbm': LGBMClassifier(n_estimators=8, num_leaves=4, min_child_samples=1,
                                      min_data_in_bin=1, random_state=0, n_jobs=1, verbosity=-1),
            'catboost': CatBoostClassifier(iterations=8, depth=2, random_seed=0, thread_count=1,
                                           verbose=False, allow_writing_files=False),
        }
        report['library_smoke'] = {}
        for name, model in models.items():
            model.fit(pd.DataFrame(x, columns=['x']), y)
            p = model.predict_proba(pd.DataFrame(unseen, columns=['x']))
            assert p.shape == (4, 2) and np.isfinite(p).all() and ((p >= 0) & (p <= 1)).all()
            np.testing.assert_allclose(p.sum(axis=1), 1)
            report['library_smoke'][name] = dict(status='PASS', train_rows=16, prediction_rows=4,
                                                synthetic=True, probabilities=p.tolist())

        import nbformat
        from nbclient import NotebookClient
        from jupyter_client import KernelManager
        nb = nbformat.read(notebook, as_version=4)
        manager = KernelManager(kernel_name='python3')
        manager.kernel_spec.argv[0] = sys.executable
        client = NotebookClient(nb, km=manager, timeout=120, allow_errors=False,
                                resources={'metadata': {'path': str(Path.cwd())}})
        # Explicit cleanup is needed because this function supplied the manager.
        executed = client.execute(cleanup_kc=True)
        streams = ''.join(o.get('text', '') for c in executed.cells if c.cell_type == 'code'
                          for o in c.get('outputs', []) if o.output_type == 'stream')
        assert sys.executable.lower() in streams.lower(), 'Notebook used a different Python environment'
        nbformat.write(executed, output/'phase0-foundations.executed.ipynb')
        report['notebook'] = dict(status='PASS', source_sha256=hashlib.sha256(notebook.read_bytes()).hexdigest(),
                                 kernel_executable=manager.kernel_spec.argv[0],
                                 executed_cells=sum(c.cell_type == 'code' and c.execution_count is not None
                                                    for c in executed.cells))
        report['packages'] = {name: version(name) for name in
                              ['numpy', 'pandas', 'pyarrow', 'matplotlib', 'scikit-learn', 'lightgbm',
                               'catboost', 'jupyterlab', 'nbclient', 'nbformat', 'ipykernel', 'pytest']}
        report['status'] = 'PASS'
        report['artifact_hashes'] = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in output.rglob('*') if p.is_file() and 'runtime' not in p.relative_to(output).parts}
    except BaseException as exc:
        report.update(status='FAILED', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
        for name, previous in previous_environment.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--notebook', type=Path, default=Path('notebooks/phase0-foundations.ipynb'))
    args = parser.parse_args()
    print(json.dumps(run(args.output, args.notebook), indent=2))


if __name__ == '__main__':
    main()
