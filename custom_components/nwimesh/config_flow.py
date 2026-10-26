"""Config and options flow for NWI Mesh."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BROKER_NAME,
    CONF_CHANNELS,
    CONF_HISTORY,
    CONF_HOPWATCH_URL,
    CONF_ROOT_TOPIC,
    CONF_TLS,
    DEFAULT_BROKER_NAME,
    DEFAULT_CHANNELS,
    DEFAULT_HISTORY,
    DEFAULT_HOPWATCH_URL,
    DEFAULT_HOST,
    DEFAULT_NAME,
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_ROOT_TOPIC,
    DEFAULT_USERNAME,
    DOMAIN,
)
from .coordinator import fetch_stats
from .mesh import parse_channels, test_connect

TEXT = selector.TextSelector()
PASSWORD = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))
URL = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.URL))


def _schema(d: dict, with_name: bool) -> vol.Schema:
    fields: dict = {}
    if with_name:
        fields[vol.Required(CONF_NAME, default=d.get(CONF_NAME, DEFAULT_NAME))] = TEXT
    fields.update({
        vol.Optional(CONF_HOPWATCH_URL, description={"suggested_value": d.get(CONF_HOPWATCH_URL, DEFAULT_HOPWATCH_URL)}): URL,
        vol.Optional(CONF_HOST, description={"suggested_value": d.get(CONF_HOST, DEFAULT_HOST)}): TEXT,
        vol.Required(CONF_PORT, default=d.get(CONF_PORT, DEFAULT_PORT)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=65535, mode=selector.NumberSelectorMode.BOX)
        ),
        vol.Optional(CONF_USERNAME, description={"suggested_value": d.get(CONF_USERNAME, DEFAULT_USERNAME)}): TEXT,
        vol.Optional(CONF_PASSWORD, description={"suggested_value": d.get(CONF_PASSWORD, DEFAULT_PASSWORD)}): PASSWORD,
        vol.Required(CONF_TLS, default=d.get(CONF_TLS, False)): selector.BooleanSelector(),
        vol.Required(CONF_ROOT_TOPIC, default=d.get(CONF_ROOT_TOPIC, DEFAULT_ROOT_TOPIC)): TEXT,
        vol.Required(CONF_CHANNELS, default=d.get(CONF_CHANNELS, DEFAULT_CHANNELS)): TEXT,
        vol.Required(CONF_HISTORY, default=d.get(CONF_HISTORY, DEFAULT_HISTORY)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=5, max=200, mode=selector.NumberSelectorMode.BOX)
        ),
        vol.Optional(CONF_BROKER_NAME, description={"suggested_value": d.get(CONF_BROKER_NAME, DEFAULT_BROKER_NAME)}): TEXT,
    })
    return vol.Schema(fields)


async def _validate(hass, user_input: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    user_input[CONF_PORT] = int(user_input[CONF_PORT])
    user_input[CONF_HISTORY] = int(user_input[CONF_HISTORY])
    for key in (CONF_HOPWATCH_URL, CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_BROKER_NAME):
        user_input[key] = (user_input.get(key) or "").strip()
    if not user_input[CONF_HOPWATCH_URL] and not user_input[CONF_HOST]:
        errors["base"] = "nothing_enabled"
        return errors
    try:
        parse_channels(user_input[CONF_CHANNELS])
    except ValueError:
        errors[CONF_CHANNELS] = "bad_channels"
    if user_input[CONF_HOPWATCH_URL]:
        try:
            await fetch_stats(hass, user_input[CONF_HOPWATCH_URL])
        except Exception:  # noqa: BLE001 - any failure means "can't use this URL"
            errors[CONF_HOPWATCH_URL] = "cannot_reach_hopwatch"
    if user_input[CONF_HOST] and not errors:
        try:
            await hass.async_add_executor_job(
                test_connect,
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                user_input[CONF_TLS],
            )
        except Exception:  # noqa: BLE001
            errors[CONF_HOST] = "cannot_connect_mqtt"
    return errors


class NWIMeshConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}|{user_input[CONF_ROOT_TOPIC]}|{user_input[CONF_HOPWATCH_URL]}"
                )
                self._abort_if_unique_id_configured()
                name = user_input.pop(CONF_NAME)
                return self.async_create_entry(title=name, data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}, True), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return NWIMeshOptionsFlow()


class NWIMeshOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(data=user_input)
        current = user_input or {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(current, False), errors=errors)
