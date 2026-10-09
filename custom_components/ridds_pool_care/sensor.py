"""Sensors: water chemistry, pool details, and the latest test / visit summaries."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    EntityCategory,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import POOL_MODELS
from .coordinator import RiddsConfigEntry, RiddsCoordinator
from .entity import RiddsPoolEntity

# HA caps a state at 255 characters; the full text lives in attributes.
MAX_STATE = 255

# Attributes that are useful on a card but pointless (and large) in history.
BIG_ATTRS = frozenset(
    {"details", "history", "readings", "equipment", "christina", "report_url", "work", "conditions", "spares"}
)


# ── Chemistry ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class ChemDescription(SensorEntityDescription):
    """A water parameter, read from the snapshot's per-parameter latest readings."""

    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT


CHEMISTRY: tuple[ChemDescription, ...] = (
    ChemDescription(key="free_chlorine", translation_key="free_chlorine",
                    native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION, icon="mdi:flask-outline"),
    ChemDescription(key="total_chlorine", translation_key="total_chlorine",
                    native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION, icon="mdi:flask-outline"),
    ChemDescription(key="ph", device_class=SensorDeviceClass.PH),
    ChemDescription(key="alkalinity", translation_key="alkalinity",
                    native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION, icon="mdi:water-opacity"),
    ChemDescription(key="stabiliser", translation_key="stabiliser",
                    native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION, icon="mdi:shield-sun-outline"),
    ChemDescription(key="salt", translation_key="salt",
                    native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION, icon="mdi:shaker-outline"),
    ChemDescription(key="calcium_hardness", translation_key="calcium_hardness",
                    native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION, icon="mdi:water-outline"),
    ChemDescription(key="iron", translation_key="iron",
                    native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION, icon="mdi:atom"),
    ChemDescription(key="copper", translation_key="copper",
                    native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION, icon="mdi:atom"),
    ChemDescription(key="bromine", translation_key="bromine",
                    native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION, icon="mdi:flask-outline"),
    ChemDescription(key="tds", translation_key="tds",
                    native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION, icon="mdi:water-outline"),
    ChemDescription(key="ammonia", translation_key="ammonia",
                    native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION, icon="mdi:fish"),
    ChemDescription(key="nitrite", translation_key="nitrite",
                    native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION, icon="mdi:fish"),
    ChemDescription(key="nitrate", translation_key="nitrate",
                    native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION, icon="mdi:fish"),
    ChemDescription(key="kh", translation_key="kh", native_unit_of_measurement="dKH", icon="mdi:water-opacity"),
    ChemDescription(key="gh", translation_key="gh", native_unit_of_measurement="dGH", icon="mdi:water-opacity"),
    ChemDescription(key="dissolved_oxygen", translation_key="dissolved_oxygen",
                    native_unit_of_measurement="mg/L", icon="mdi:bubble"),
    ChemDescription(key="water_temp", translation_key="water_temp",
                    device_class=SensorDeviceClass.TEMPERATURE,
                    native_unit_of_measurement=UnitOfTemperature.CELSIUS),
)
CHEM_BY_KEY = {d.key: d for d in CHEMISTRY}

# What every pool gets from day one, before its first test of that parameter.
BASE_CHEMISTRY: dict[str, tuple[str, ...]] = {
    "pool": ("free_chlorine", "ph", "alkalinity", "stabiliser"),
    "spa": ("free_chlorine", "ph", "alkalinity"),
    "koi_pond": ("ph", "ammonia", "nitrite", "nitrate", "kh", "water_temp"),
}


def _chem_keys(pool: dict[str, Any]) -> set[str]:
    keys = set(BASE_CHEMISTRY.get(pool.get("type") or "pool", BASE_CHEMISTRY["pool"]))
    if (pool.get("details") or {}).get("chlorination_type") == "salt":
        keys.add("salt")
    keys |= {k for k, v in (pool.get("readings") or {}).items()
             if k in CHEM_BY_KEY and isinstance((v or {}).get("value"), (int, float))}
    return keys


class ChemistrySensor(RiddsPoolEntity, SensorEntity):
    """The most recent value of one parameter, with Ridd's verdict alongside."""

    entity_description: ChemDescription
    _unrecorded_attributes = BIG_ATTRS

    def __init__(self, coordinator: RiddsCoordinator, pool_id: str, desc: ChemDescription) -> None:
        super().__init__(coordinator, pool_id, f"chem_{desc.key}")
        self.entity_description = desc

    @property
    def _reading(self) -> dict[str, Any] | None:
        return ((self.pool or {}).get("readings") or {}).get(self.entity_description.key)

    @property
    def native_value(self) -> float | None:
        r = self._reading
        v = r.get("value") if r else None
        return v if isinstance(v, (int, float)) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        r = self._reading
        if not r:
            return None
        return {
            "status": r.get("status"),
            "verdict": r.get("verdict"),
            "ideal_range": r.get("ideal"),
            "advice": r.get("advice"),
            "dose": r.get("dose"),
            "tested_on": r.get("date"),
            "tested_by": r.get("by"),
        }


# ── Everything else on a pool ────────────────────────────────────────────────


def _clip(text: Any) -> str | None:
    if not isinstance(text, str) or not text.strip():
        return None
    text = text.strip()
    return text if len(text) <= MAX_STATE else text[: MAX_STATE - 1] + "…"


def _date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    return dt_util.parse_date(value[:10])


def _record_attrs(rec: dict[str, Any] | None) -> dict[str, Any] | None:
    if not rec:
        return None
    attrs = {
        "date": rec.get("date"),
        "by": rec.get("by"),
        "kind": rec.get("kind"),
        "job_type": rec.get("job_type"),
        "overall": rec.get("overall"),
        "summary": rec.get("summary"),
        "details": rec.get("details") or [],
        "conditions": rec.get("conditions") or [],
        "work": rec.get("work") or [],
        "spares": rec.get("spares") or [],
        "work_carried_out": rec.get("work_carried_out"),
        "observations": rec.get("observations"),
        "filter_pressure": rec.get("filter_pressure"),
        "pump_watts": rec.get("pump_watts"),
        "report_url": rec.get("report_url"),
    }
    if rec.get("readings"):
        attrs["readings"] = {
            k: {"value": v.get("value"), "status": v.get("status")}
            for k, v in rec["readings"].items()
            if isinstance(v, dict)
        }
    return {k: v for k, v in attrs.items() if v not in (None, [], {})}


@dataclass(frozen=True, kw_only=True)
class PoolDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any] | None] = lambda _p: None


def _days_since(pool: dict[str, Any]) -> int | None:
    d = _date((pool.get("latest_chemistry") or {}).get("date"))
    return (dt_util.now().date() - d).days if d else None


def _history_attrs(pool: dict[str, Any]) -> dict[str, Any]:
    counts = pool.get("counts") or {}
    return {
        "tests": counts.get("tests", 0),
        "visits": counts.get("visits", 0),
        "maintenance": counts.get("maintenance", 0),
        "history": pool.get("history") or [],
    }


def _details_attrs(pool: dict[str, Any]) -> dict[str, Any]:
    d = dict(pool.get("details") or {})
    d.pop("updated_at", None)
    attrs = {k: v for k, v in d.items() if v is not None}
    eq = {k: v for k, v in (pool.get("equipment") or {}).items() if v}
    if eq:
        attrs["equipment"] = eq
    return attrs


POOL_SENSORS: tuple[PoolDescription, ...] = (
    PoolDescription(
        key="water_status",
        translation_key="water_status",
        device_class=SensorDeviceClass.ENUM,
        options=["ok", "fair", "attention", "unknown"],
        icon="mdi:pool",
        value_fn=lambda p: (p.get("latest_chemistry") or {}).get("overall") or "unknown",
        attrs_fn=lambda p: _record_attrs(p.get("latest_chemistry")),
    ),
    PoolDescription(
        key="last_water_test",
        translation_key="last_water_test",
        icon="mdi:test-tube",
        value_fn=lambda p: _clip((p.get("latest_chemistry") or {}).get("summary")),
        attrs_fn=lambda p: _record_attrs(p.get("latest_chemistry")),
    ),
    PoolDescription(
        key="last_water_test_date",
        translation_key="last_water_test_date",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar-check",
        value_fn=lambda p: _date((p.get("latest_chemistry") or {}).get("date")),
    ),
    PoolDescription(
        key="days_since_test",
        translation_key="days_since_test",
        native_unit_of_measurement=UnitOfTime.DAYS,
        icon="mdi:calendar-clock",
        value_fn=_days_since,
    ),
    PoolDescription(
        key="last_visit",
        translation_key="last_visit",
        icon="mdi:account-wrench",
        value_fn=lambda p: _clip((p.get("latest_visit") or {}).get("summary")),
        attrs_fn=lambda p: _record_attrs(p.get("latest_visit")),
    ),
    PoolDescription(
        key="last_visit_date",
        translation_key="last_visit_date",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar-account",
        value_fn=lambda p: _date((p.get("latest_visit") or {}).get("date")),
    ),
    PoolDescription(
        key="last_maintenance",
        translation_key="last_maintenance",
        icon="mdi:broom",
        value_fn=lambda p: _clip((p.get("latest_maintenance") or {}).get("summary")),
        attrs_fn=lambda p: _record_attrs(p.get("latest_maintenance")),
    ),
    PoolDescription(
        key="next_service",
        translation_key="next_service",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar-arrow-right",
        value_fn=lambda p: _date((p.get("details") or {}).get("next_service_date")),
    ),
    PoolDescription(
        key="service_history",
        translation_key="service_history",
        icon="mdi:history",
        value_fn=lambda p: sum((p.get("counts") or {}).values()),
        attrs_fn=_history_attrs,
    ),
    PoolDescription(
        key="volume",
        translation_key="volume",
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        icon="mdi:cup-water",
        value_fn=lambda p: (p.get("details") or {}).get("volume_litres"),
    ),
    PoolDescription(
        key="pool_details",
        translation_key="pool_details",
        icon="mdi:information-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda p: POOL_MODELS.get(p.get("type") or "pool", "Pool"),
        attrs_fn=_details_attrs,
    ),
    PoolDescription(
        key="pump_size",
        translation_key="pump_size",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda p: (p.get("details") or {}).get("pump_size_kw"),
    ),
)


class PoolSensor(RiddsPoolEntity, SensorEntity):
    entity_description: PoolDescription
    _unrecorded_attributes = BIG_ATTRS

    def __init__(self, coordinator: RiddsCoordinator, pool_id: str, desc: PoolDescription) -> None:
        super().__init__(coordinator, pool_id, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> Any:
        pool = self.pool
        return self.entity_description.value_fn(pool) if pool else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        pool = self.pool
        return self.entity_description.attrs_fn(pool) if pool else None


async def async_setup_entry(
    hass: HomeAssistant, entry: RiddsConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new: list[SensorEntity] = []
        for pool_id, pool in coordinator.data.pools.items():
            for desc in POOL_SENSORS:
                uid = f"{pool_id}_{desc.key}"
                if uid not in known:
                    known.add(uid)
                    new.append(PoolSensor(coordinator, pool_id, desc))
            # A parameter appears the first time it is tested (e.g. salt
            # after a technician brings a salt meter) — no reload needed.
            for key in sorted(_chem_keys(pool)):
                uid = f"{pool_id}_chem_{key}"
                if uid not in known:
                    known.add(uid)
                    new.append(ChemistrySensor(coordinator, pool_id, CHEM_BY_KEY[key]))
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))
