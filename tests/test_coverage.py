"""
tests/test_coverage.py
Tests for coverage analytics: carrier-depth logic, India board, KPIs.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.coverage.analytics import (
    COV_ALL_EXPIRED,
    COV_COVERED,
    COV_GAP,
    COV_THIN,
    country_coverage,
    india_board,
    port_coverage,
)

TZ = "Asia/Kolkata"
THRESHOLD = 14
MIN = 2


def d(delta: int) -> str:
    return (date.today() + timedelta(days=delta)).isoformat()


def make_rate(dest_iso2="US", dest_code="USNYC", carrier="MSC",
              end=None, start=None, origin_code="INMUN"):
    return {
        "id": f"{carrier}-{dest_code}-{end}",
        "carrier_brand": carrier,
        "destination_iso2": dest_iso2,
        "destination_code": dest_code,
        "origin_code": origin_code,
        "validity_start_date": start or d(-30),
        "validity_end_date": end,
    }


# ── Country coverage ──────────────────────────────────────────────────────────

class TestCountryCoverage:
    def test_gap_no_rates(self):
        result = country_coverage([], ["US"], MIN, THRESHOLD, TZ)
        assert result["items"][0]["coverageStatus"] == COV_GAP

    def test_all_expired(self):
        rates = [
            make_rate("US", carrier="MSC",   end=d(-10)),
            make_rate("US", carrier="Maersk", end=d(-5)),
        ]
        result = country_coverage(rates, ["US"], MIN, THRESHOLD, TZ)
        assert result["items"][0]["coverageStatus"] == COV_ALL_EXPIRED

    def test_thin_cover_one_carrier(self):
        rates = [make_rate("US", carrier="MSC", end=d(30))]
        result = country_coverage(rates, ["US"], MIN, THRESHOLD, TZ)
        assert result["items"][0]["coverageStatus"] == COV_THIN
        assert result["items"][0]["validCarrierCount"] == 1

    def test_covered_two_active_carriers(self):
        rates = [
            make_rate("US", carrier="MSC",   end=d(30)),
            make_rate("US", carrier="Maersk", end=d(25)),
        ]
        result = country_coverage(rates, ["US"], MIN, THRESHOLD, TZ)
        assert result["items"][0]["coverageStatus"] == COV_COVERED

    def test_expiring_carrier_still_valid(self):
        """An expiring carrier counts towards valid cover."""
        rates = [
            make_rate("US", carrier="MSC",   end=d(7)),   # expiring
            make_rate("US", carrier="Maersk", end=d(30)),  # active
        ]
        result = country_coverage(rates, ["US"], MIN, THRESHOLD, TZ)
        item = result["items"][0]
        assert item["coverageStatus"] == COV_COVERED
        assert item["hasExpiring"] is True

    def test_expiring_flag_set(self):
        rates = [
            make_rate("US", carrier="MSC",    end=d(5)),   # expiring
            make_rate("US", carrier="Maersk", end=d(30)),  # active
        ]
        result = country_coverage(rates, ["US"], MIN, THRESHOLD, TZ)
        assert result["items"][0]["hasExpiring"] is True

    def test_sort_order_gap_first(self):
        rates = [
            make_rate("US", carrier="MSC",   end=d(30)),
            make_rate("US", carrier="Maersk", end=d(25)),
        ]
        result = country_coverage(rates, ["US", "ZA", "GB"], MIN, THRESHOLD, TZ)
        statuses = [i["coverageStatus"] for i in result["items"]]
        # GAP items should come before COVERED
        gap_idx     = statuses.index(COV_GAP)     if COV_GAP     in statuses else 999
        covered_idx = statuses.index(COV_COVERED) if COV_COVERED in statuses else 999
        assert gap_idx < covered_idx

    def test_summary_all_fine(self):
        rates = [
            make_rate("US", carrier="MSC",   end=d(30)),
            make_rate("US", carrier="Maersk", end=d(25)),
        ]
        result = country_coverage(rates, ["US"], MIN, THRESHOLD, TZ)
        assert "adequate" in result["summary"].lower() or "all" in result["summary"].lower()

    def test_summary_has_gap(self):
        result = country_coverage([], ["ZA"], MIN, THRESHOLD, TZ)
        summary = result["summary"].lower()
        assert "no rate" in summary or "attention" in summary


# ── Port coverage ─────────────────────────────────────────────────────────────

class TestPortCoverage:
    def test_gap_port(self):
        result = port_coverage([], ["GBLGP"], MIN, THRESHOLD, TZ)
        assert result["items"][0]["coverageStatus"] == COV_GAP

    def test_covered_port(self):
        rates = [
            make_rate("GB", "GBLGP", "MSC",        end=d(30)),
            make_rate("GB", "GBLGP", "Hapag-Lloyd", end=d(25)),
        ]
        result = port_coverage(rates, ["GBLGP"], MIN, THRESHOLD, TZ)
        assert result["items"][0]["coverageStatus"] == COV_COVERED

    def test_thin_port_one_carrier(self):
        rates = [make_rate("GB", "GBLGP", "MSC", end=d(30))]
        result = port_coverage(rates, ["GBLGP"], MIN, THRESHOLD, TZ)
        assert result["items"][0]["coverageStatus"] == COV_THIN

    def test_carrier_chips_present(self):
        rates = [
            make_rate("GB", "GBLGP", "MSC",         end=d(30)),
            make_rate("GB", "GBLGP", "Hapag-Lloyd",  end=d(5)),   # expiring
            make_rate("GB", "GBLGP", "CMA CGM",      end=d(-5)),  # expired
        ]
        result = port_coverage(rates, ["GBLGP"], MIN, THRESHOLD, TZ)
        chips = result["items"][0]["carrierChips"]
        states = {c["state"] for c in chips}
        assert "active" in states
        assert "expiring" in states
        assert "expired" in states


# ── India board ───────────────────────────────────────────────────────────────

class TestIndiaBoard:
    def _rate(self, code, carrier, end, as_origin=True):
        if as_origin:
            return {
                "id": f"{code}-{carrier}-{end}",
                "carrier_brand": carrier,
                "origin_code": code,
                "destination_code": "USNYC",
                "destination_iso2": "US",
                "validity_start_date": d(-30),
                "validity_end_date": end,
            }
        else:
            return {
                "id": f"{code}-{carrier}-{end}",
                "carrier_brand": carrier,
                "origin_code": "USNYC",
                "destination_code": code,
                "destination_iso2": "IN",
                "validity_start_date": d(-30),
                "validity_end_date": end,
            }

    def test_zone_assignment(self):
        rates = [self._rate("INNSA", "MSC", d(30)), self._rate("INNSA", "Maersk", d(25))]
        result = india_board(rates, ["INNSA"], {}, MIN, THRESHOLD, TZ)
        west_codes = [e["code"] for e in result["zones"]["West"]]
        assert "INNSA" in west_codes

    def test_unclassified_unknown_port(self):
        rates = [self._rate("INXYZ", "MSC", d(30))]
        result = india_board(rates, ["INXYZ"], {}, MIN, THRESHOLD, TZ)
        # INXYZ is not in the static mapping, should be Unclassified
        all_codes = [
            e["code"] for zone in result["zones"].values() for e in zone
        ] + [e["code"] for e in result["detectedNotWatched"]]
        assert "INXYZ" in all_codes

    def test_override_changes_zone(self):
        rates = [self._rate("INNSA", "MSC", d(30)), self._rate("INNSA", "Maersk", d(25))]
        overrides = {"INNSA": {"name": "Custom Name", "zone": "North"}}
        result = india_board(rates, ["INNSA"], overrides, MIN, THRESHOLD, TZ)
        north_codes = [e["code"] for e in result["zones"]["North"]]
        assert "INNSA" in north_codes

    def test_detected_not_watched(self):
        rates = [self._rate("INHAL", "MSC", d(30))]  # INHAL not in watched
        result = india_board(rates, ["INNSA"], {}, MIN, THRESHOLD, TZ)
        detected_codes = [e["code"] for e in result["detectedNotWatched"]]
        assert "INHAL" in detected_codes

    def test_matches_origin_or_destination(self):
        """India board should catch ports in both origin and destination."""
        rate_as_dest = self._rate("INMUN", "MSC", d(30), as_origin=False)
        result = india_board([rate_as_dest], ["INMUN"], {}, MIN, THRESHOLD, TZ)
        west_codes = [e["code"] for e in result["zones"]["West"]]
        assert "INMUN" in west_codes


# ── Coverage maths edge cases ─────────────────────────────────────────────────

class TestCoverageEdgeCases:
    def test_min_carriers_1(self):
        """With min=1, a single active carrier gives COVERED."""
        rates = [make_rate("US", carrier="MSC", end=d(30))]
        result = country_coverage(rates, ["US"], 1, THRESHOLD, TZ)
        assert result["items"][0]["coverageStatus"] == COV_COVERED

    def test_min_carriers_3(self):
        """With min=3, two carriers gives THIN."""
        rates = [
            make_rate("US", carrier="MSC",   end=d(30)),
            make_rate("US", carrier="Maersk", end=d(25)),
        ]
        result = country_coverage(rates, ["US"], 3, THRESHOLD, TZ)
        assert result["items"][0]["coverageStatus"] == COV_THIN

    def test_expired_only_not_gap(self):
        """ALL_EXPIRED is different from GAP (rates exist, but none valid)."""
        rates = [make_rate("US", carrier="MSC", end=d(-10))]
        result = country_coverage(rates, ["US"], MIN, THRESHOLD, TZ)
        item = result["items"][0]
        assert item["coverageStatus"] == COV_ALL_EXPIRED
        assert item["coverageStatus"] != COV_GAP
