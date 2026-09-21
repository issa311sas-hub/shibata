"""Build nine approved inputs from verified pre-race captures, without labels."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from .observed import observed_tables
from .ingestion.capture import verify_capture
from .ingestion.model_fields import decode_model_fields
from .ingestion.jv_race import decode_race_record
from .ingestion.contracts import require

FEATURES=['age','sex','bracket_number','horse_number','runner_count','distance','surface','venue','carried_weight']


def build(entries_dir,odds_dir,cutoff,confirmation=None):
    races,entries,odds,provenance=observed_tables(entries_dir,odds_dir,cutoff,confirmation)
    captured=verify_capture(entries_dir)
    require(captured['manifest_sha256']==provenance['entries_manifest_sha256'], 'Entries changed during feature assembly')
    # Require the same bytes validated by observed_tables, including the recapture check.
    race_fields=[];horse_fields={}
    for record in captured['records']:
        b=record['payload']
        if b[:2] not in (b'RA',b'SE'): continue
        decoded=decode_model_fields(b)
        if b[:2]==b'RA': race_fields.append(decoded['raw_fields'])
        else:
            identity=decode_race_record(b)['horse_id']
            require(identity not in horse_fields,'Duplicate horse feature row')
            horse_fields[identity]=decoded['raw_fields']
    require(len(race_fields)==1,'Expected one race feature row')
    race=race_fields[0]
    require(race['surface'] in {'turf','dirt','sand'},'Only flat races supported')
    require(race['registered_count']==len(entries),'Feature population mismatch')
    rows=[]
    for entry in entries.to_dict('records'):
        horse=horse_fields[entry['horse_id']]
        require(horse['horse_number']==entry['horse_number'],'Horse number mismatch')
        row={**horse,**{k:race[k] for k in ('distance','surface','venue')},'runner_count':len(entries)}
        require(all(row[k] is not None for k in FEATURES),'Missing approved feature; no zero imputation')
        rows.append(dict(race_id=entry['race_id'],horse_id=entry['horse_id'],prediction_at=cutoff,**row))
    return pd.DataFrame(rows),provenance


def export(entries_dir,odds_dir,cutoff,output,confirmation=None):
    frame,provenance=build(entries_dir,odds_dir,cutoff,confirmation)
    output.mkdir(parents=True,exist_ok=False)
    file=output/'features.csv';frame.to_csv(file,index=False)
    status=dict(status='PASS',feature_names=FEATURES,rows=len(frame),
                features_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                results_used=False,model_fitted=False,live_prediction_created=False,
                input_availability_basis='verified local pre-cutoff acquisition',provenance=provenance)
    (output/'status.json').write_text(json.dumps(status,indent=2,default=str),encoding='utf-8')
    return status


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--entries',type=Path,required=True);p.add_argument('--odds',type=Path,required=True)
    p.add_argument('--cutoff',required=True);p.add_argument('--confirmation',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(export(a.entries,a.odds,a.cutoff,a.output,a.confirmation),default=str))


if __name__=='__main__':main()

