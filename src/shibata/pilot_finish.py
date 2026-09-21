"""One bounded post-racing pass to collect and evaluate saved pilot predictions."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import uuid

from . import pilot
from .pilot_runner import ACTIVE, rows, runner_lock, log
from .ingestion.contracts import require, timestamp


def finish(workspace):
    workspace = workspace.resolve()
    with runner_lock(workspace):
        registered = rows(workspace)
        require(not any(r['state'] in ACTIVE for r in registered),
                'Finish acquisition/expire missed predictions before collecting results')
        require(all(pilot.now_utc() > timestamp(r['start_at']) for r in registered),
                'Result batch starts only after every scheduled race start')
        shell = shutil.which('pwsh') or shutil.which('powershell')
        require(shell is not None, 'PowerShell is unavailable')
        script = Path(__file__).resolve().parents[2]/'scripts'/'collect-jvlink.ps1'
        for row in registered:
            key = row['race_id']
            if row['state'] == 'EVALUATING':
                pilot.transition(workspace,key,{'EVALUATING'},'RESULT_PENDING',
                                 'Previous evaluation interrupted; preserve artifacts and retry in a fresh folder')
            elif row['state'] not in {'PREDICTED','RESULT_PENDING'}:
                continue
            destination = workspace/'raw'/key/('results-'+uuid.uuid4().hex)
            try:
                subprocess.run([shell,'-NoProfile','-NonInteractive','-File',str(script),
                                '-DataSpec','0B12','-RaceKey',key,'-OutputDirectory',str(destination)],
                               check=True,timeout=60,capture_output=True,text=True)
            except (OSError,subprocess.SubprocessError) as exc:
                pilot.transition(workspace,key,{'PREDICTED','RESULT_PENDING'},'RESULT_PENDING',str(exc))
                log(workspace,'RESULT_CAPTURE_ERROR',race_id=key,detail=str(exc))
                continue
            try:
                pilot.evaluate_race(workspace,key,destination)
            except (ValueError,OSError,KeyError,TypeError) as exc:
                log(workspace,'RESULT_EVALUATION_ERROR',race_id=key,detail=str(exc))
                if pilot.get_race(workspace,key)['state'] != 'RESULT_PENDING':
                    raise
        output = workspace/'reports'/('report-'+uuid.uuid4().hex)
        summary = pilot.report(workspace,output)
        return dict(report_directory=str(output),coverage=summary)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(finish(args.workspace),indent=2))


if __name__=='__main__': main()
