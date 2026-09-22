"""Whole-race chronological partitions; does not certify source availability."""
from datetime import date
import pandas as pd
from .ingestion.contracts import require
from .ingestion.jv_o1 import validate_race_key

PARTITIONS=('train','validation','test')


def partition(frame,config):
    require(config['timezone']=='Asia/Tokyo' and config['split_unit']=='whole_race_by_race_date',
            'Unexpected partition policy')
    windows={}
    previous=None
    for name in PARTITIONS:
        start=date.fromisoformat(config[name]['start']);end=date.fromisoformat(config[name]['end_inclusive'])
        require(start<=end and (previous is None or previous<start),'Overlapping or unordered periods')
        windows[name]=(start,end);previous=end
    require(not frame.empty,'Empty dataset')
    require(frame.race_id.notna().all() and frame.horse_id.notna().all(),'Missing identity')
    require(not frame.duplicated(['race_id','horse_id']).any(),'Duplicate race/horse')
    assignment={}
    for key in frame.race_id.unique():
        validate_race_key(key)
        day=pd.to_datetime(key[:8],format='%Y%m%d').date()
        assignment[key]=next((name for name,(lo,hi) in windows.items() if lo<=day<=hi),'outside')
    labels=frame.race_id.map(assignment)
    parts={name:frame.loc[labels==name].copy() for name in (*PARTITIONS,'outside')}
    coverage={name:dict(rows=len(rows),races=rows.race_id.nunique()) for name,rows in parts.items()}
    return parts,coverage
