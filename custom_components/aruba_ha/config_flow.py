"""Config flow for the Aruba HA (2930F) integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_COMMUNITY_READ,
    CONF_COMMUNITY_WRITE,
    CONF_ENABLE_DEVICE_TRACKER,
    CONF_ENABLE_PORT_CONTROL,
    CONF_SNMP_VERSION,
    CONF_V3_AUTH_KEY,
    CONF_V3_AUTH_PROTOCOL,
    CONF_V3_PRIV_KEY,
    CONF_V3_PRIV_PROTOCOL,
    CONF_V3_USERNAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SNMP_V2C,
    SNMP_V3,
    SNMP_V3_AUTH_MD5,
    SNMP_V3_AUTH_NONE,
    SNMP_V3_AUTH_SHA,
    SNMP_V3_AUTH_SHA224,
    SNMP_V3_AUTH_SHA256,
    SNMP_V3_AUTH_SHA384,
    SNMP_V3_AUTH_SHA512,
    SNMP_V3_PRIV_3DES,
    SNMP_V3_PRIV_AES128,
    SNMP_V3_PRIV_AES192,
    SNMP_V3_PRIV_AES256,
    SNMP_V3_PRIV_DES,
    SNMP_V3_PRIV_NONE,
    OID_SYS_DESCR,
)
from .snmp import ArubaSnmpClient, ArubaSnmpError, build_read_auth, build_write_auth

_LOGGER = logging.getLogger(__name__)

AUTH_PROTOCOL_OPTIONS = [
    selector.SelectOptionDict(value=SNMP_V3_AUTH_NONE, label="Aucune (noAuth)"),
    selector.SelectOptionDict(value=SNMP_V3_AUTH_MD5, label="MD5"),
    selector.SelectOptionDict(value=SNMP_V3_AUTH_SHA, label="SHA-1"),
    selector.SelectOptionDict(value=SNMP_V3_AUTH_SHA224, label="SHA-224"),
    selector.SelectOptionDict(value=SNMP_V3_AUTH_SHA256, label="SHA-256"),
    selector.SelectOptionDict(value=SNMP_V3_AUTH_SHA384, label="SHA-384"),
    selector.SelectOptionDict(value=SNMP_V3_AUTH_SHA512, label="SHA-512"),
]

PRIV_PROTOCOL_OPTIONS = [
    selector.SelectOptionDict(value=SNMP_V3_PRIV_NONE, label="Aucune (noPriv)"),
    selector.SelectOptionDict(value=SNMP_V3_PRIV_DES, label="DES"),
    selector.SelectOptionDict(value=SNMP_V3_PRIV_3DES, label="3DES"),
    selector.SelectOptionDict(value=SNMP_V3_PRIV_AES128, label="AES-128"),
    selector.SelectOptionDict(value=SNMP_V3_PRIV_AES192, label="AES-192"),
    selector.SelectOptionDict(value=SNMP_V3_PRIV_AES256, label="AES-256"),
]


async def _validate_connection(data: dict[str, Any]) -> None:
    """Try to reach the switch with the given credentials, or raise."""
    read_auth = build_read_auth(data)
    write_auth = build_write_auth(data) if data.get(CONF_ENABLE_PORT_CONTROL) else None
    client = ArubaSnmpClient(data["host"], data["port"], read_auth, write_auth)

    await client.async_get(OID_SYS_DESCR)

    if data.get(CONF_ENABLE_PORT_CONTROL) and data.get(CONF_SNMP_VERSION) == SNMP_V2C and write_auth is not None:
        # A GET using the write (RW) community confirms the agent accepts it,
        # without ever issuing a SET against the live switch.
        write_client = ArubaSnmpClient(data["host"], data["port"], write_auth, None)
        await write_client.async_get(OID_SYS_DESCR)


class ArubaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Aruba HA integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ArubaOptionsFlow:
        """Get the options flow for this handler."""
        return ArubaOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """First step: host/port and SNMP version choice."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data.update(user_input)
            if user_input[CONF_SNMP_VERSION] == SNMP_V3:
                return await self.async_step_v3()
            return await self.async_step_v2c()

        schema = vol.Schema(
            {
                vol.Required("host"): str,
                vol.Required("port", default=DEFAULT_PORT): int,
                vol.Required(CONF_SNMP_VERSION, default=SNMP_V2C): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=SNMP_V2C, label="SNMPv2c (community string)"),
                            selector.SelectOptionDict(value=SNMP_V3, label="SNMPv3 (utilisateur/auth/priv)"),
                        ]
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_v2c(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Collect SNMPv2c community strings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_options()

        schema = vol.Schema(
            {
                vol.Required(CONF_COMMUNITY_READ, default="public"): str,
                vol.Optional(CONF_COMMUNITY_WRITE): str,
            }
        )
        return self.async_show_form(step_id="v2c", data_schema=schema, errors=errors)

    async def async_step_v3(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Collect SNMPv3 USM credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_V3_AUTH_PROTOCOL] != SNMP_V3_AUTH_NONE and not user_input.get(CONF_V3_AUTH_KEY):
                errors[CONF_V3_AUTH_KEY] = "auth_key_required"
            elif (
                user_input[CONF_V3_PRIV_PROTOCOL] != SNMP_V3_PRIV_NONE
                and not user_input.get(CONF_V3_PRIV_KEY)
            ):
                errors[CONF_V3_PRIV_KEY] = "priv_key_required"
            elif (
                user_input[CONF_V3_PRIV_PROTOCOL] != SNMP_V3_PRIV_NONE
                and user_input[CONF_V3_AUTH_PROTOCOL] == SNMP_V3_AUTH_NONE
            ):
                errors[CONF_V3_PRIV_PROTOCOL] = "priv_requires_auth"
            else:
                self._data.update(user_input)
                return await self.async_step_options()

        schema = vol.Schema(
            {
                vol.Required(CONF_V3_USERNAME): str,
                vol.Required(CONF_V3_AUTH_PROTOCOL, default=SNMP_V3_AUTH_SHA): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=AUTH_PROTOCOL_OPTIONS)
                ),
                vol.Optional(CONF_V3_AUTH_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_V3_PRIV_PROTOCOL, default=SNMP_V3_PRIV_AES128): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=PRIV_PROTOCOL_OPTIONS)
                ),
                vol.Optional(CONF_V3_PRIV_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(step_id="v3", data_schema=schema, errors=errors)

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Collect the common behaviour options and validate connectivity."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data.update(user_input)

            if (
                self._data.get(CONF_ENABLE_PORT_CONTROL)
                and self._data[CONF_SNMP_VERSION] == SNMP_V2C
                and not self._data.get(CONF_COMMUNITY_WRITE)
            ):
                errors[CONF_ENABLE_PORT_CONTROL] = "write_community_required"
            else:
                try:
                    await _validate_connection(self._data)
                except ArubaSnmpError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unexpected error validating the Aruba switch connection")
                    errors["base"] = "unknown"

            if not errors:
                await self.async_set_unique_id(f"{self._data['host']}:{self._data['port']}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=self._data.get("host", "Switch Aruba"), data=self._data
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_ENABLE_PORT_CONTROL, default=True): selector.BooleanSelector(),
                vol.Required(CONF_ENABLE_DEVICE_TRACKER, default=True): selector.BooleanSelector(),
                vol.Required("scan_interval", default=DEFAULT_SCAN_INTERVAL): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=10, max=3600, unit_of_measurement="s")
                ),
            }
        )
        return self.async_show_form(step_id="options", data_schema=schema, errors=errors)


class ArubaOptionsFlow(OptionsFlow):
    """Allow reconfiguring the behaviour options after setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options or self._config_entry.data
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_PORT_CONTROL,
                    default=current.get(CONF_ENABLE_PORT_CONTROL, True),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_ENABLE_DEVICE_TRACKER,
                    default=current.get(CONF_ENABLE_DEVICE_TRACKER, True),
                ): selector.BooleanSelector(),
                vol.Required(
                    "scan_interval",
                    default=current.get("scan_interval", DEFAULT_SCAN_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=10, max=3600, unit_of_measurement="s")
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
