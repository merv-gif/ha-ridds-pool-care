"""Diagnostics download — never includes the key or signed report links."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY
from .coordinator import RiddsConfigEntry

TO_REDACT = {CONF_API_KEY, "report_url", "owner", "name", "by", "observations", "work_carried_out"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RiddsConfigEntry
) -> dict[str, Any]:
    data = entry.runtime_data.data
    return async_redact_data(
        {
            "entry": dict(entry.data),
            "key_id": data.key_id if data else None,
            "generated_at": data.generated_at if data else None,
            "pools": list(data.pools.values()) if data else [],
        },
        TO_REDACT,
    )
