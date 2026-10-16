"""
tests/test_normaliser.py
Tests for normalisation: field mapping, location parsing, carrier canonicalisation,
trade direction, deduplication, derived keys.
"""
from __future__ import annotations

import pytest

from app.normalize.normaliser import normalise_all, normalise_record
from app.normalize.reference_data import canonicalise_carrier, parse_location, trade_direction


# ── Carrier canonicalisation ──────────────────────────────────────────────────

class TestCarrierCanonicalisation:
    def test_msc(self):
        assert canonicalise_carrier("MSC AGENCY (INDIA) PVT. LTD") == "MSC"

    def test_mediterranean(self):
        assert canonicalise_carrier("MEDITERRANEAN SHIPPING COMPANY") == "MSC"

    def test_hapag(self):
        assert canonicalise_carrier("HAPAG-LLOYD AG") == "Hapag-Lloyd"

    def test_hlag(self):
        assert canonicalise_carrier("HLAG CONTAINER LINE") == "Hapag-Lloyd"

    def test_cma(self):
        assert canonicalise_carrier("CMA CGM S.A.") == "CMA CGM"

    def test_maersk(self):
        assert canonicalise_carrier("MAERSK LINE") == "Maersk"

    def test_sealand(self):
        assert canonicalise_carrier("SEALAND MAERSK") == "Maersk"

    def test_one(self):
        assert canonicalise_carrier("ONE OCEAN NETWORK EXPRESS") == "ONE"
        assert canonicalise_carrier("OCEAN NETWORK EXPRESS PTE. LTD") == "ONE"

    def test_evergreen(self):
        assert canonicalise_carrier("EVERGREEN MARINE CORP.") == "Evergreen"

    def test_cosco(self):
        assert canonicalise_carrier("COSCO SHIPPING LINES CO. LTD") == "COSCO"

    def test_oocl(self):
        assert canonicalise_carrier("OOCL HONG KONG") == "COSCO"

    def test_hmm(self):
        assert canonicalise_carrier("HMM CO. LTD") == "HMM"
        assert canonicalise_carrier("HYUNDAI MERCHANT MARINE") == "HMM"

    def test_yang_ming(self):
        assert canonicalise_carrier("YANG MING MARINE TRANSPORT") == "Yang Ming"

    def test_zim(self):
        assert canonicalise_carrier("ZIM INTEGRATED SHIPPING SERVICES") == "ZIM"

    def test_unknown_fallback(self):
        result = canonicalise_carrier("ACME SHIPPING CORP")
        assert result == "ACME SHIPPING"

    def test_none(self):
        assert canonicalise_carrier(None) == "Unknown"

    def test_case_insensitive(self):
        assert canonicalise_carrier("msc agency india") == "MSC"


# ── Location parsing ──────────────────────────────────────────────────────────

class TestParseLocation:
    def test_full_format(self):
        r = parse_location("SGSIN,Singapore (Singapore)")
        assert r["code"] == "SGSIN"
        assert r["portName"] == "Singapore"
        assert r["countryName"] == "Singapore"
        assert r["countryIso2"] == "SG"

    def test_mundra_format(self):
        r = parse_location("INMUN,Mundra(India)")
        assert r["code"] == "INMUN"
        assert r["portName"] == "Mundra"
        assert r["countryIso2"] == "IN"

    def test_code_only(self):
        r = parse_location("DEHAM")
        assert r["code"] == "DEHAM"
        assert r["countryIso2"] == "DE"

    def test_none_input(self):
        assert parse_location(None) is None

    def test_empty_string(self):
        assert parse_location("") is None


# ── Trade direction ───────────────────────────────────────────────────────────

class TestTradeDirection:
    def test_rate_type_oe_export(self):
        assert trade_direction("OE", "IN", "US") == "Export"

    def test_rate_type_oi_import(self):
        assert trade_direction("OI", "US", "IN") == "Import"

    def test_rate_type_ae_export(self):
        assert trade_direction("AE", None, None) == "Export"

    def test_rate_type_ai_import(self):
        assert trade_direction("AI", None, None) == "Import"

    def test_rate_type_exp(self):
        assert trade_direction("EXP", "IN", "SG") == "Export"

    def test_rate_type_imp(self):
        assert trade_direction("IMP", "US", "IN") == "Import"

    def test_origin_in_export(self):
        assert trade_direction(None, "IN", "US") == "Export"

    def test_dest_in_import(self):
        assert trade_direction(None, "US", "IN") == "Import"

    def test_both_in_domestic(self):
        assert trade_direction(None, "IN", "IN") == "Domestic"

    def test_neither_in_cross(self):
        assert trade_direction(None, "US", "DE") == "Cross-trade"

    def test_rate_type_takes_priority_over_countries(self):
        # Rate type OI should override IN→US heuristic
        assert trade_direction("OI", "IN", "US") == "Import"


# ── Deduplication ─────────────────────────────────────────────────────────────

class TestDeduplication:
    def test_duplicate_ids_deduplicated(self, field_map):
        raw = [
            {"id": "R1", "originName": "INMUN,Mundra(India)", "destinationName": "USNYC,New York(US)",
             "shippingLineName": "MSC", "rate": 1000, "currency": "USD",
             "validityEndDate": "2025-12-31", "rateType": "OE"},
            {"id": "R1", "originName": "INMUN,Mundra(India)", "destinationName": "USNYC,New York(US)",
             "shippingLineName": "MSC", "rate": 1100, "currency": "USD",
             "validityEndDate": "2025-12-31", "rateType": "OE"},
        ]
        records, dups = normalise_all(raw, field_map)
        assert len(records) == 1
        assert dups == 1
        # Last occurrence wins
        assert records[0]["rate"] == 1100

    def test_no_duplicates_unchanged(self, field_map):
        raw = [
            {"id": "R1", "originName": "INMUN,Mundra(India)", "destinationName": "USNYC,New York(US)",
             "rate": 1000, "currency": "USD"},
            {"id": "R2", "originName": "INNSA,Nhava Sheva(India)", "destinationName": "GBLGP,London Gateway(UK)",
             "rate": 2000, "currency": "USD"},
        ]
        records, dups = normalise_all(raw, field_map)
        assert len(records) == 2
        assert dups == 0

    def test_derived_key_when_no_id(self, field_map):
        """Records without an ID should get a DERIVED: key and be flagged."""
        raw = [
            {"originName": "INMUN,Mundra(India)", "destinationName": "USNYC,New York(US)",
             "shippingLineName": "MSC", "validityEndDate": "2025-12-31"},
        ]
        records, _ = normalise_all(raw, field_map)
        assert records[0]["is_derived_key"] is True
        assert records[0]["id"].startswith("DERIVED:")

    def test_duplicate_pages_no_duplicate_records(self, field_map):
        """Simulate a paginator returning the same page twice."""
        page = [
            {"id": f"R{i}", "originName": "INMUN,Mundra(India)",
             "destinationName": "USNYC,New York(US)", "rate": 1000}
            for i in range(5)
        ]
        raw = page + page  # duplicate the entire page
        records, dups = normalise_all(raw, field_map)
        assert len(records) == 5
        assert dups == 5


# ── Rate & currency pairing ────────────────────────────────────────────────────

class TestRateCurrencyPairing:
    def test_rate_currency_stay_paired(self, field_map):
        raw = [
            {"id": "R1", "rate": 2500, "currency": "USD"},
            {"id": "R2", "rate": 1800, "currency": "EUR"},
        ]
        records, _ = normalise_all(raw, field_map)
        by_id = {r["id"]: r for r in records}
        assert by_id["R1"]["rate"] == 2500
        assert by_id["R1"]["currency"] == "USD"
        assert by_id["R2"]["rate"] == 1800
        assert by_id["R2"]["currency"] == "EUR"

    def test_null_rate_does_not_drop_record(self, field_map):
        raw = [{"id": "R1", "rate": None, "currency": "USD",
                "originName": "INMUN,Mundra(India)"}]
        records, _ = normalise_all(raw, field_map)
        assert len(records) == 1
        assert records[0]["rate"] is None
