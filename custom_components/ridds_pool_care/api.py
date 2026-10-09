"""The one HTTP call: trade an integration key for a snapshot of the owner's pools."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_URL


class RiddsApiError(Exception):
    """Ridd's Pool Care could not be reached or answered badly."""


class RiddsAuthError(RiddsApiError):
    """The key is unknown, revoked, or no longer belongs to a pool owner."""


async def async_fetch(hass: HomeAssistant, api_key: str, url: str = API_URL) -> dict[str, Any]:
    """Call ha-connect. Raises RiddsAuthError on a bad key, RiddsApiError otherwise."""
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(30):
            resp = await session.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={},
            )
            if resp.status == 401:
                raise RiddsAuthError("integration key rejected")
            if resp.status != 200:
                raise RiddsApiError(f"ha-connect returned HTTP {resp.status}")
            body = await resp.json()
    except RiddsApiError:
        raise
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise RiddsApiError(f"could not reach Ridd's Pool Care: {err}") from err

    if not isinstance(body, dict) or not body.get("key_id") or not isinstance(body.get("pools"), list):
        raise RiddsApiError("unexpected response from ha-connect")
    return body
