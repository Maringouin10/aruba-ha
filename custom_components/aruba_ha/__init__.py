"""The Aruba HA (2930F / ArubaOS-Switch) integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.const import Platform

from .const import CONF_ENABLE_DEVICE_TRACKER, CONF_ENABLE_PORT_CONTROL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import ArubaDataUpdateCoordinator
from .snmp import ArubaSnmpClient, ArubaSnmpError, build_read_auth, build_write_auth

_LOGGER = logging.getLogger(__name__)

PLATFORMS_BASE = [Platform.SENSOR, Platform.BINARY_SENSOR]


def _platforms_for_entry(entry: ConfigEntry) -> list[Platform]:
    platforms = list(PLATFORMS_BASE)
    if entry.options.get(CONF_ENABLE_PORT_CONTROL, entry.data.get(CONF_ENABLE_PORT_CONTROL, False)):
        platforms.append(Platform.SWITCH)
    if entry.options.get(CONF_ENABLE_DEVICE_TRACKER, entry.data.get(CONF_ENABLE_DEVICE_TRACKER, False)):
        platforms.append(Platform.DEVICE_TRACKER)
    return platforms


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Aruba HA from a config entry."""
    data = entry.data

    read_auth = build_read_auth(data)
    write_auth = (
        build_write_auth(data)
        if entry.options.get(CONF_ENABLE_PORT_CONTROL, data.get(CONF_ENABLE_PORT_CONTROL, False))
        else None
    )
    client = ArubaSnmpClient(data["host"], data["port"], read_auth, write_auth)

    scan_interval = entry.options.get("scan_interval", data.get("scan_interval", DEFAULT_SCAN_INTERVAL))
    coordinator = ArubaDataUpdateCoordinator(hass, entry, client, scan_interval)

    try:
        await coordinator.async_config_entry_first_refresh()
    except ArubaSnmpError as err:
        raise ConfigEntryNotReady(f"Impossible de joindre le switch Aruba {data['host']}: {err}") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, _platforms_for_entry(entry))
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _platforms_for_entry(entry))
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
