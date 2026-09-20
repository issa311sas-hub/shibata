import pytest

from shibata.ingestion.contracts import DataError
from shibata.ingestion.jv_o1 import decode_o1
from shibata.ingestion.plan import build_plan


def fixture_record():
    # Fictional byte record. Offsets follow format 7, not the decoder's constants.
    data = bytearray(b" " * 960 + b"\r\n")
    data[0:3] = b"O11"
    data[3:11] = b"20240115"
    data[11:27] = b"2024011505010101"
    data[27:35] = b"01151140"
    data[35:43] = b"02027770"
    data[43:51] = b"01002001"
    data[51:59] = b"02004002"
    return data


def test_decode_real_format_with_fictional_bytes():
    decoded = decode_o1(bytes(fixture_record()))
    assert decoded["race_key"] == "2024011505010101"
    assert decoded["slots"][0]["win_odds"] == 2.0
    assert decoded["slots"][1]["win_odds"] == 4.0
    assert len(decoded["slots"]) == 28
    assert decoded["slots"][2]["status"] == "not_registered"
    assert decoded["prediction_ready"] is False
    assert decoded["announcement_mmddhhmm_raw"] == "01151140"


@pytest.mark.parametrize("quote,status", [(b"0000", "no_votes"), (b"----", "cancelled_before_sale"),
                                           (b"****", "cancelled_after_sale"), (b"9999", "capped")])
def test_special_values_are_not_zero_filled(quote, status):
    data = fixture_record()
    data[45:49] = quote
    decoded = decode_o1(bytes(data))
    slot = decoded["slots"][0]
    assert slot["status"] == status
    assert slot["odds_raw"] == quote.decode()
    assert slot["win_odds"] == (999.9 if status == "capped" else None)


@pytest.mark.parametrize("status,kind", [(b"3", "final"), (b"9", "cancelled"), (b"0", "deletion")])
def test_final_cancelled_and_deletion_never_become_pre_race(status, kind):
    data = fixture_record()
    data[2:3] = status
    data[27:35] = b"00000000"
    decoded = decode_o1(bytes(data))
    assert decoded["record_kind"] == kind
    assert decoded["prediction_ready"] is False


def test_truncated_and_malformed_bytes_rejected():
    with pytest.raises(DataError, match="962"):
        decode_o1(bytes(fixture_record()[:-1]))
    data = fixture_record()
    data[45:49] = b"oops"
    with pytest.raises(DataError, match="quote"):
        decode_o1(bytes(data))


def test_dry_run_plan_has_no_transport():
    plan = build_plan("2024011505010101")
    assert plan["network_requests"] == 0
    assert plan["transport_implemented"] is False
    assert plan["request"] == {"method": "JVRTOpen", "dataspec": "0B41", "key": "2024011505010101"}


@pytest.mark.parametrize("key", ["202401150501", "2024023005010101", "2024011599010101", "../data"])
def test_invalid_race_keys_rejected(key):
    with pytest.raises(DataError):
        build_plan(key)
