"""Fixtures: a synthetic ha-connect response (no real customer data)."""
from __future__ import annotations

import copy
from datetime import date, timedelta
from typing import Any

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]

KEY = "ridds_ha_" + "ab" * 32
TODAY = date.today()


def _d(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


def _reading(value, label, unit, verdict, status, ideal, advice=None, dose=None, days_ago=3, by="You"):
    return {
        "value": value, "label": label, "unit": unit, "verdict": verdict, "status": status,
        "ideal": ideal, "advice": advice, "dose": dose, "date": _d(days_ago), "by": by,
    }


TEST_RECORD = {
    "id": "rec-test-1",
    "date": _d(3),
    "recorded_at": _d(3) + "T08:00:00+00:00",
    "kind": "test",
    "job_type": "routine_service",
    "by": "You",
    "overall": "attention",
    "summary": "Needs attention: Alkalinity low, pH high",
    "details": [
        "Water looked: Clear.",
        "Alkalinity is low — Add sodium bicarbonate. Dose: about 3.4 kg sodium bicarbonate for this 40,000 L pool (raises it to ~90 ppm).",
        "pH is high — Lower pH with pool acid in small doses. Retest after 6 hours.",
    ],
    "conditions": ["Clear"],
    "work": [],
    "spares": [],
    "readings": {
        "free_chlorine": {"value": 2, "verdict": "ok", "status": "In range"},
        "ph": {"value": 8.2, "verdict": "high", "status": "High"},
        "alkalinity": {"value": 40, "verdict": "low", "status": "Low"},
    },
    "christina": [],
    "report_url": None,
}

VISIT_RECORD = {
    "id": "rec-visit-1",
    "date": _d(10),
    "recorded_at": _d(10) + "T09:00:00+00:00",
    "kind": "visit",
    "job_type": "routine_service",
    "by": "Thabo",
    "overall": "ok",
    "summary": "Routine service by Thabo — backwash, brushed, vacuumed — all readings in range",
    "details": ["Done: Backwash, Brushed, Vacuumed.", "Water: Clear."],
    "conditions": ["Clear"],
    "work": ["Backwash", "Brushed", "Vacuumed"],
    "spares": ["1 × Pump basket lid"],
    "work_carried_out": "Replaced pump basket lid",
    "observations": "Leaves in the weir",
    "filter_pressure": 1.1,
    "readings": {"salt": {"value": 3800, "verdict": "ok", "status": "In range"}},
    "christina": [],
    "report_url": "https://example.invalid/report.pdf?token=secret",
}

MAINT_RECORD = {
    "id": "rec-maint-1",
    "date": _d(5),
    "kind": "maintenance",
    "job_type": "maintenance",
    "by": "You",
    "overall": None,
    "summary": "Your maintenance log — pump basket, backwash",
    "details": ["Done: Pump basket, Backwash."],
    "work": ["Pump basket", "Backwash"],
    "readings": None,
    "report_url": None,
}

SNAPSHOT: dict[str, Any] = {
    "api_version": 1,
    "key_id": "key-uuid-1",
    "label": "Home Assistant",
    "owner": {"name": "Pat Owner"},
    "refresh_seconds": 900,
    "generated_at": "2026-10-09T12:00:00Z",
    "pools": [
        {
            "id": "pool-1",
            "name": "Main pool",
            "type": "pool",
            "details": {
                "volume_litres": 40000,
                "surface_type": "plaster",
                "chlorination_type": "salt",
                "heated": True,
                "heating_type": "heat_pump",
                "has_blanket": True,
                "filter_type": "sand",
                "pump_size_kw": 0.75,
                "next_service_date": _d(1),
                "service_frequency": "monthly",
            },
            "equipment": {"pumps": [{"make": "Speck", "model": "Badu", "size": "0.75kW"}], "filters": [],
                          "chlorinators": [], "heat_pumps": []},
            "readings": {
                "free_chlorine": _reading(2, "Free Chlorine", "ppm", "ok", "In range", "1.5–3"),
                "ph": _reading(8.2, "pH", "", "high", "High", "7.2–7.6",
                               advice="Lower pH with pool acid in small doses. Retest after 6 hours."),
                "alkalinity": _reading(40, "Alkalinity", "ppm", "low", "Low", "80–120",
                                       advice="Add sodium bicarbonate.",
                                       dose="about 3.4 kg sodium bicarbonate for this 40,000 L pool"),
                "salt": _reading(3800, "Salt", "ppm", "ok", "In range", "3000–5000", days_ago=10, by="Thabo"),
            },
            "health": {"score": 66, "label": "Attention", "in_range": 1, "measured": 4},
            "score_trend": [{"date": _d(60), "score": 64}, {"date": _d(40), "score": 100},
                            {"date": _d(25), "score": 82}, {"date": _d(10), "score": 91},
                            {"date": _d(3), "score": 66}],
            "latest_chemistry": TEST_RECORD,
            "latest_test": TEST_RECORD,
            "latest_visit": VISIT_RECORD,
            "latest_maintenance": MAINT_RECORD,
            "counts": {"tests": 6, "visits": 4, "maintenance": 2},
            "history": [
                {k: TEST_RECORD[k] for k in ("id", "date", "kind", "job_type", "by", "overall", "summary")},
                {k: MAINT_RECORD[k] for k in ("id", "date", "kind", "job_type", "by", "overall", "summary")},
                {k: VISIT_RECORD[k] for k in ("id", "date", "kind", "job_type", "by", "overall", "summary")},
            ],
        },
        {
            "id": "pond-1",
            "name": "Koi pond",
            "type": "koi_pond",
            "details": {"volume_litres": 8000, "next_service_date": None},
            "equipment": {},
            "readings": {
                "ammonia": {"value": 0.25, "label": "Ammonia", "unit": "ppm", "verdict": None, "date": _d(20), "by": "Thabo"},
                "water_temp": {"value": 21.5, "label": "Water temperature", "unit": "°C", "verdict": None, "date": _d(20), "by": "Thabo"},
            },
            "latest_chemistry": {
                "id": "rec-pond-1", "date": _d(20), "kind": "visit", "by": "Thabo", "overall": "unknown",
                "summary": "Maintenance by Thabo — netted pond", "details": [],
            },
            "latest_test": None,
            "latest_visit": None,
            "latest_maintenance": None,
            "counts": {"tests": 0, "visits": 1, "maintenance": 0},
            "history": [{"id": "rec-pond-1", "date": _d(20), "kind": "visit", "by": "Thabo",
                         "overall": "unknown", "summary": "Maintenance by Thabo — netted pond"}],
        },
    ],
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def snapshot() -> dict[str, Any]:
    return copy.deepcopy(SNAPSHOT)
