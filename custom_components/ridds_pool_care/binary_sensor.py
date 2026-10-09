"""Binary sensors: does the water need attention, is a service due."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import RiddsConfigEntry, RiddsCoordinator
from .entity import RiddsPoolEntity


def _attention(pool: dict[str, Any]) -> bool | None:
    overall = (pool.get("latest_chemistry") or {}).get("overall")
    if overall in (None, "unknown"):
        return None
    return overall == "attention"


def _attention_attrs(pool: dict[str, Any]) -> dict[str, Any]:
    readings = pool.get("readings") or {}
    off = {
        r.get("label") or k: r.get("status")
        for k, r in readings.items()
        if isinstance(r, dict) and r.get("verdict") in ("low", "high")
    }
    rec = pool.get("latest_chemistry") or {}
    return {"out_of_range": off, "summary": rec.get("summary"), "tested_on": rec.get("date")}


def _service_due(pool: dict[str, Any]) -> bool | None:
    raw = (pool.get("details") or {}).get("next_service_date")
    if not raw:
        return False
    d = dt_util.parse_date(str(raw)[:10])
    return None if d is None else d <= dt_util.now().date()


@dataclass(frozen=True, kw_only=True)
class PoolBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any] | None] = lambda _p: None


BINARY_SENSORS: tuple[PoolBinaryDescription, ...] = (
    PoolBinaryDescription(
        key="needs_attention",
        translation_key="needs_attention",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_attention,
        attrs_fn=_attention_attrs,
    ),
    PoolBinaryDescription(
        key="service_due",
        translation_key="service_due",
        icon="mdi:calendar-alert",
        value_fn=_service_due,
        attrs_fn=lambda p: {"next_service_date": (p.get("details") or {}).get("next_service_date")},
    ),
)


class PoolBinarySensor(RiddsPoolEntity, BinarySensorEntity):
    entity_description: PoolBinaryDescription

    def __init__(self, coordinator: RiddsCoordinator, pool_id: str, desc: PoolBinaryDescription) -> None:
        super().__init__(coordinator, pool_id, desc.key)
        self.entity_description = desc

    @property
    def is_on(self) -> bool | None:
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
        new = []
        for pool_id in coordinator.data.pools:
            for desc in BINARY_SENSORS:
                uid = f"{pool_id}_{desc.key}"
                if uid not in known:
                    known.add(uid)
                    new.append(PoolBinarySensor(coordinator, pool_id, desc))
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))
