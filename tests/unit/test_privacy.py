import pandas as pd

from breachlens.privacy.hashing import KEY_HEX, dl_key, passport_key, ssn_key
from breachlens.privacy.masking import mask_id, mask_premasked, mask_ssn, mask_text
from breachlens.privacy.stage import MENTION_COLUMNS, drop_raw, mask_excluded, privacy_row

SALT = b"unit-test-salt-0123456789abcdef"


def test_masks_keep_last_four_only():
    assert mask_ssn("123-45-6789") == "***-**-6789"
    assert mask_id("4111111111111111") == "************1111"
    assert mask_id("A1234567") == "****4567"
    assert mask_id("123") == "***"
    assert mask_premasked("xxx-xx-1234") == "XXX-XX-1234"
    # free text: every 9+ digit run is masked, phones included (conservative)
    assert mask_text("call 212 555 0123 or SSN 123-45-6789") == "call ******0123 or SSN *****6789"
    assert mask_text("Seen 3 times on 04/12") == "Seen 3 times on 04/12"
    assert mask_ssn(None) is None and mask_id("") is None


def test_keys_are_deterministic_salted_and_kind_separated():
    k = ssn_key(SALT, "123-45-6789")
    assert k == ssn_key(SALT, "123456789") and len(k) == KEY_HEX
    assert k != ssn_key(b"another-salt-0123456789abcdef!!", "123456789")
    assert dl_key(SALT, "123456789", "NY") != ssn_key(SALT, "123456789")
    assert dl_key(SALT, "a123-4567", "ca") == dl_key(SALT, "A1234567", "CA")
    assert passport_key(SALT, "a12345678", None) == passport_key(SALT, "A12345678", "US")
    assert ssn_key(SALT, "1234") is None


def test_trio_columns_and_keys():
    row = {
        "_raw_ssn": "123456789",
        "_ssn_status": "TEXT",
        "qc_reasons": "SSN_GROUP_INVALID",
        "_raw_card": "4.11111E+15",
        "_card_status": "PRECISION_LOST",
        "_raw_dl": "A1234567",
        "dl_state": "CA",
        "_raw_routing": "021000021",
        "_raw_member_id": "M12345678",
        "_raw_group_number": "G1",
    }
    out = privacy_row(row, SALT)
    assert (out["ssn_present"], out["ssn_masked"], out["ssn_valid"]) == (
        True,
        "***-**-6789",
        "SSN_GROUP_INVALID",
    )
    assert out["ssn_key"] == ssn_key(SALT, "123456789")
    assert out["card_valid"] == "XL_NUMBER_PRECISION_LOST" and out["card_present"]
    assert out["dl_valid"] == "PASS" and out["dl_key"]
    assert out["routing_number_valid"] == "PASS" and out["health_group_number_present"]
    assert out["health_member_id_masked"] == "*****5678"
    assert (out["passport_present"], out["passport_valid"], out["passport_key"]) == (
        False,
        None,
        None,
    )


def test_premasked_values_get_no_key():
    out = privacy_row({"_raw_ssn": "XXX-XX-6789", "_ssn_status": "PREMASKED"}, SALT)
    assert (out["ssn_masked"], out["ssn_valid"], out["ssn_key"]) == (
        "XXX-XX-6789",
        "PREMASKED_VALUE",
        None,
    )


def test_drop_raw_and_excluded_masking():
    df = pd.DataFrame({"mention_id": ["M00001"], "_raw_ssn": ["123456789"], "_repair_codes": [""]})
    assert list(drop_raw(df).columns) == ["mention_id"]
    ex = mask_excluded(
        pd.DataFrame(
            {
                "doc_id": ["D1"],
                "kind": ["EIN"],
                "_raw_value": ["12-3456789"],
                "value_masked": [None],
                "reason": ["EIN_EXCLUDED"],
            }
        )
    )
    assert ex["value_masked"].tolist() == ["*****6789"] and "_raw_value" not in ex


def test_schema_columns_are_unique():
    assert len(MENTION_COLUMNS) == len(set(MENTION_COLUMNS))
