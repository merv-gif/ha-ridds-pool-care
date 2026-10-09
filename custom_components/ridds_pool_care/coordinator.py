"""Polls Ridd's Pool Care and announces new tests and visits."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RiddsApiError, RiddsAuthError, async_fetch
from .const import (
    CONF_API_KEY,
    DEFAULT_REFRESH_SECONDS,
    DOMAIN,
    EVENT_NEW_RECORD,
    MIN_REFRESH_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class RiddsData:
    """One snapshot, pools keyed by id."""

    key_id: str
    label: str
    owner: str | None
    pools: dict[str, dict[str, Any]]
    generated_at: str | None


type RiddsConfigEntry = ConfigEntry[RiddsCoordinator]


class RiddsCoordinator(DataUpdateCoordinator[RiddsData]):
    """Fetches the owner's pools every refresh_seconds (server-chosen)."""

    config_entry: RiddsConfigEntry

    def __init__(self, hass: HomeAssistant, entry: RiddsConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_REFRESH_SECONDS),
        )
        self._seen: set[str] | None = None

    async def _async_update_data(self) -> RiddsData:
        try:
            body = await async_fetch(self.hass, self.config_entry.data[CONF_API_KEY])
        except RiddsAuthError as err:
            raise ConfigEntryAuthFailed(
                "The Ridd's Pool Care key was revoked or no longer works"
            ) from err
        except RiddsApiError as err:
            raise UpdateFailed(str(err)) from err

        # The server decides how often to come back, within a sane floor.
        seconds = max(int(body.get("refresh_seconds") or DEFAULT_REFRESH_SECONDS), MIN_REFRESH_SECONDS)
        self.update_interval = timedelta(seconds=seconds)

        pools = {str(p["id"]): p for p in body.get("pools", []) if p.get("id")}
        self._announce(pools)

        return RiddsData(
            key_id=str(body["key_id"]),
            label=str(body.get("label") or "Home Assistant"),
            owner=(body.get("owner") or {}).get("name"),
            pools=pools,
            generated_at=body.get("generated_at"),
        )

    def _announce(self, pools: dict[str, dict[str, Any]]) -> None:
        """Fire one event per record we have not seen before.

        The first fetch only learns what exists — nobody wants twenty events
        the moment the integration is added.
        """
        current: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        for pool in pools.values():
            for rec in pool.get("history") or []:
                if rec.get("id"):
                    current[str(rec["id"])] = (pool, rec)

        if self._seen is None:
            self._seen = set(current)
            return

        new = [current[i] for i in current if i not in self._seen]
        self._seen |= set(current)
        # Oldest first, so automations see them in the order they happened.
        for pool, rec in sorted(new, key=lambda pr: (pr[1].get("date") or "")):
            self.hass.bus.async_fire(
                EVENT_NEW_RECORD,
                {
                    "pool_id": pool["id"],
                    "pool_name": pool.get("name"),
                    "record_id": rec["id"],
                    "kind": rec.get("kind"),
                    "date": rec.get("date"),
                    "by": rec.get("by"),
                    "overall": rec.get("overall"),
                    "summary": rec.get("summary"),
                },
            )
