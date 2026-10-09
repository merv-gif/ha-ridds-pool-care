"""Config flow: paste an integration key from the Ridd's Pool Care app."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import RiddsApiError, RiddsAuthError, async_fetch
from .const import CONF_API_KEY, DOMAIN, KEY_PAGE_URL, KEY_PREFIX

KEY_SCHEMA = vol.Schema(
    {vol.Required(CONF_API_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
)


class RiddsConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per key."""

    VERSION = 1

    async def _validate(self, key: str) -> tuple[dict[str, str], dict[str, Any] | None]:
        if not key.startswith(KEY_PREFIX):
            return {CONF_API_KEY: "not_a_key"}, None
        try:
            body = await async_fetch(self.hass, key)
        except RiddsAuthError:
            return {CONF_API_KEY: "invalid_auth"}, None
        except RiddsApiError:
            return {"base": "cannot_connect"}, None
        return {}, body

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_API_KEY].strip()
            errors, body = await self._validate(key)
            if not errors and body is not None:
                await self.async_set_unique_id(str(body["key_id"]))
                self._abort_if_unique_id_configured()
                pools = [p.get("name") or "Pool" for p in body["pools"]]
                title = "Ridd's Pool Care"
                if pools:
                    title += f" ({', '.join(pools)})"
                return self.async_create_entry(title=title, data={CONF_API_KEY: key})
        return self.async_show_form(
            step_id="user",
            data_schema=KEY_SCHEMA,
            errors=errors,
            description_placeholders={"key_url": KEY_PAGE_URL},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_API_KEY].strip()
            errors, body = await self._validate(key)
            if not errors and body is not None:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    unique_id=str(body["key_id"]),
                    data={CONF_API_KEY: key},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=KEY_SCHEMA,
            errors=errors,
            description_placeholders={"key_url": KEY_PAGE_URL},
        )
