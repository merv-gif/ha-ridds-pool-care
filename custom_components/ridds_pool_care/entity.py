"""One Home Assistant device per pool."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import APP_URL, DOMAIN, MANUFACTURER, POOL_MODELS
from .coordinator import RiddsCoordinator


class RiddsPoolEntity(CoordinatorEntity[RiddsCoordinator]):
    """Base for everything that belongs to one pool."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RiddsCoordinator, pool_id: str, key: str) -> None:
        super().__init__(coordinator)
        self.pool_id = pool_id
        self._attr_unique_id = f"{pool_id}_{key}"
        pool = self.pool or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pool_id)},
            name=pool.get("name") or "Pool",
            manufacturer=MANUFACTURER,
            model=POOL_MODELS.get(pool.get("type") or "pool", "Pool"),
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=APP_URL,
        )

    @property
    def pool(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        return data.pools.get(self.pool_id) if data else None

    @property
    def available(self) -> bool:
        return super().available and self.pool is not None
