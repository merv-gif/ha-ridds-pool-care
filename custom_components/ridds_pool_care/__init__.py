"""Ridd's Pool Care — your pool's chemistry, details and service history in Home Assistant."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, PLATFORMS
from .coordinator import RiddsConfigEntry, RiddsCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: RiddsConfigEntry) -> bool:
    """Fetch once, then hand the snapshot to the platforms."""
    coordinator = RiddsCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RiddsConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: RiddsConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing a pool that is no longer on the account."""
    pools = entry.runtime_data.data.pools if entry.runtime_data.data else {}
    return not any(ident[0] == DOMAIN and ident[1] in pools for ident in device.identifiers)
