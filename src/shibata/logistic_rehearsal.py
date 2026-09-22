"""Run a synthetic integration rehearsal; never reads real racing data."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .chronological import partition
from .models.logistic import fit_training,predict
from .models.logistic_artifact import save,load,predict_saved
from .evaluation.compare import compare


def run(config_path,output):
    config_raw=config_path.read_bytes();config=json.loads(config_raw.decode('utf-8-sig'))
    rows=[]
    for day in ('20260101','20260201','20260701'):
        for h in range(1,5):
            rows.append(dict(race_id=day+'05010101',horse_id=f'{day}{h}',age=2+h,sex='1',
                bracket_number=h,horse_number=h,runner_count=4,distance=1600,surface='turf',venue='05',
                carried_weight=55.,win=int(h==1)))
    dataset=pd.DataFrame(rows);parts,coverage=partition(dataset,config)
    output.mkdir(parents=True,exist_ok=False)
    status=dict(status='RUNNING',experiment_kind='synthetic_integration_rehearsal',
                real_data_used=False,test_evaluated=False,phase_promotion=False)
    try:
        dataset.to_csv(output/'synthetic-input.csv',index=False)
        model=fit_training(parts['train'],config)
        digest=save(model,output/'model.json',config_sha256=hashlib.sha256(config_raw).hexdigest(),
                    dataset_sha256=hashlib.sha256((output/'synthetic-input.csv').read_bytes()).hexdigest())
        validation=parts['validation'];predictions=predict_saved(load(output/'model.json',digest),validation)
        np.testing.assert_allclose(predictions.probability,predict(model,validation).probability,rtol=1e-12)
        market=validation[['race_id','horse_id']].copy()
        market['start_at']=pd.Timestamp('2026-07-01T12:00:00+09:00')
        market['win_odds']=[2.,4.,6.,8.];market['popularity']=[1,2,3,4];market['odds_rank']=[1,2,3,4]
        inverse=1/market.win_odds;market['market_probability']=inverse/inverse.sum()
        results=validation[['race_id','horse_id','win']].copy()
        results['result_status']='official';results['result_observed_at']='2026-07-01T13:00:00+09:00'
        metrics,tables=compare(predictions,market,results)
        predictions.to_csv(output/'validation-predictions.csv',index=False)
        (output/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
        for model_name,group in tables.items():
            for name,table in group.items():table.to_csv(output/f'{model_name}-{name}.csv',index=False)
        status.update(status='PASS',coverage=coverage,model_sha256=digest,
                      artifact_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()})
    except Exception as exc:
        status.update(status='FAILED',error=str(exc));raise
    finally:
        (output/'status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
    return status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path('configs/logistic-initial-v1.json'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(run(args.config,args.output)))


if __name__=='__main__':main()
