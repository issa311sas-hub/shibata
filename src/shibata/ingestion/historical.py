"""Verify bounded JVOpen captures and index every revision without choosing latest."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from .contracts import DataError, require, timestamp
from .jv_race import decode_race_record


def verify(path):
    path=Path(path)
    try:
        raw=path.read_bytes()
        manifest=json.loads(raw.decode('utf-8-sig'))
        require(manifest.get('dataspec')=='RACE' and type(manifest.get('option')) is int
                and manifest['option']==1, 'Expected RACE normal-data capture')
        require(manifest.get('complete') is True and not manifest.get('error')
                and not manifest.get('close_error'), 'Incomplete or failed capture')
        require(all(type(manifest.get(k)) is int and manifest[k]==0
                    for k in ('init_code','open_code','close_code')), 'Unsuccessful COM capture')
        begin,end=timestamp(manifest['started_at']),timestamp(manifest['finished_at'])
        require(begin<=end,'Capture time order invalid')
        records=manifest['records']
        require(isinstance(records,list) and 0<len(records)<=20000,'Invalid record count')
        folder=Path(str(path)+'.records')
        require(not folder.is_symlink(),'Capture directory must not be a symlink')
        names={f'record-{i:04d}.bin' for i in range(len(records))}
        require({p.name for p in folder.glob('*.bin')}==names,'Capture file set mismatch')
        verified=[]
        previous=begin
        for i,item in enumerate(records):
            name=f'record-{i:04d}.bin'
            require(item['file']==name,'Invalid record path or order')
            target=folder/name
            require(not target.is_symlink() and target.resolve().parent==folder.resolve(),'Unsafe record path')
            payload=target.read_bytes()
            require(type(item['size']) is int and len(payload)==item['size'],'Record size mismatch')
            require(hashlib.sha256(payload).hexdigest()==item['sha256'],'Record hash mismatch')
            require(len(payload)>=13 and payload.endswith(b'\r\n'),'Invalid record framing')
            at=timestamp(item['retrieved_at'])
            require(previous<=at<=end,'Record time order invalid')
            previous=at
            require(isinstance(item['source_file'],str) and bool(item['source_file']),'Missing source file')
            verified.append((item,payload))
        return manifest,hashlib.sha256(raw).hexdigest(),verified
    except (OSError,KeyError,TypeError,UnicodeError,json.JSONDecodeError) as exc:
        raise DataError(f'Invalid JVOpen capture: {exc}') from exc


def index_capture(path,output):
    manifest,digest,records=verify(path)
    indexed=[]
    for item,payload in records:
        kind=payload[:2].decode('ascii')
        row=dict(record_type=kind,data_status=payload[2:3].decode('ascii'),
                 payload_sha256=item['sha256'],source_file=item['source_file'],
                 record_file=item['file'],retrieved_at=item['retrieved_at'],
                 availability_at=None,training_ready=False)
        if kind in {'RA','SE'}:
            try:
                decoded=decode_race_record(payload)
                row.update(decoded)
                row['race_id']=decoded['race_key']
                row['race_date']=decoded['race_key'][:8]
                row['decoded']=True
            except DataError as exc:
                # Keep deletion, cancellation, unnumbered and malformed versions visible.
                row.update(decoded=False,decode_error=str(exc))
        else:
            row.update(decoded=False,decode_error='Record type not yet supported')
        indexed.append(row)
    keys={r['race_id'] for r in indexed if r.get('decoded')}
    summary=dict(capture_manifest_sha256=digest,request_fromtime=manifest['fromtime'],
                 record_count=len(indexed),record_types=dict(Counter(r['record_type'] for r in indexed)),
                 status_counts=dict(Counter(r['record_type']+':'+r['data_status'] for r in indexed)),
                 decoded_count=sum(r['decoded'] for r in indexed),race_count=len(keys),
                 race_dates=sorted({k[:8] for k in keys}),
                 raw_integrity_verified=True,latest_revision_selected=False,training_ready=False)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    (output/'records.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in indexed),encoding='utf-8')
    summary['index_sha256']=hashlib.sha256((output/'records.jsonl').read_bytes()).hexdigest()
    (output/'status.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(index_capture(args.manifest,args.output),indent=2))


if __name__=='__main__': main()

