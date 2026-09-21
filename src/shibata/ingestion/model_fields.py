"""Decode approved initial-model raw fields, without certifying availability."""
from .contracts import require
from .jv_race import decode_race_record


def decode_model_fields(payload):
    base=decode_race_record(payload)
    def number(start,end):
        raw=payload[start:end].decode('ascii')
        if not raw.strip() or (raw.isdigit() and int(raw)==0):
            return None
        require(raw.isdigit(),'Invalid model-field number')
        return int(raw)
    if base['record_id']=='RA':
        track=base['track_code_raw']
        # JV-Data code 2009: 10..22 turf; 23..26/29 dirt; 27/28 sand; obstacle outside scope.
        surface='turf' if track in {str(i) for i in range(10,23)} else (
            'dirt' if track in {'23','24','25','26','29'} else ('sand' if track in {'27','28'} else None))
        fields=dict(distance=number(697,701),surface=surface,venue=base['race_key'][8:10],
                    registered_count=base['registered_count'])
    else:
        sex=payload[78:79].decode('ascii')
        require(sex in {'0','1','2','3',' '},'Unknown sex code')
        weight=number(288,291)
        bracket=number(27,28)
        require(bracket is None or 1<=bracket<=8,'Invalid bracket')
        fields=dict(age=number(82,84),sex=None if sex in {'0',' '} else sex,
                    bracket_number=bracket,horse_number=base['horse_number'],
                    carried_weight=None if weight is None else weight/10)
    return dict(race_id=base['race_key'],record_type=base['record_id'],
                data_status=base['data_status'],raw_fields=fields,
                source_sha256=base['payload_sha256'],availability_at=None,training_ready=False)

