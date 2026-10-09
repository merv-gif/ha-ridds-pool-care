"""Ridd's Pool Care — your pool's chemistry, details and service history in Home Assistant."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import CARD_URL, DOMAIN, PLATFORMS
from .coordinator import RiddsConfigEntry, RiddsCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CARD_FILE = Path(__file__).parent / "frontend" / "ridds-pool-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the Ridd's Pool card so it is in the card picker with no extra install."""
    await _async_register_card(hass)
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    if hass.http is None or "frontend" not in hass.config.components:
        return
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    try:
        # Content hash as the cache-buster: an update is picked up on the next
        # page load, never stuck behind a cached old card.
        digest = await hass.async_add_executor_job(
            lambda: hashlib.sha256(CARD_FILE.read_bytes()).hexdigest()[:10]
        )
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(CARD_FILE), True)]
        )
    except (OSError, RuntimeError) as err:  # RuntimeError: path already registered
        _LOGGER.debug("Ridd's Pool card not registered: %s", err)
        return
    add_extra_js_url(hass, f"{CARD_URL}?v={digest}")


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
