"""Device tracking based on the switch's MAC address (FDB) table."""
from __future__ import annotations

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ArubaDataUpdateCoordinator
from .entity import ArubaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up device trackers for MAC addresses learned by the switch."""
    coordinator: ArubaDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_macs: set[str] = set()

    @callback
    def _add_new_devices() -> None:
        new_macs = {e.mac_address for e in coordinator.data.fdb if e.mac_address} - known_macs
        if not new_macs:
            return
        known_macs.update(new_macs)
        async_add_entities(ArubaDeviceTracker(coordinator, mac) for mac in new_macs)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_devices))
    _add_new_devices()


class ArubaDeviceTracker(ArubaEntity, ScannerEntity):
    """Represents a MAC address seen on one of the switch's ports."""

    _attr_source_type = SourceType.ROUTER

    def __init__(self, coordinator: ArubaDataUpdateCoordinator, mac_address: str) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator)
        self._mac = mac_address
        self._attr_unique_id = f"{coordinator.entry.entry_id}_client_{mac_address.replace(':', '')}"

    @property
    def _fdb_entry(self):
        for entry in self.coordinator.data.fdb:
            if entry.mac_address == self._mac:
                return entry
        return None

    @property
    def name(self) -> str:
        """Return the entity name."""
        return self._mac

    @property
    def is_connected(self) -> bool:
        """Return True if the MAC is currently present in the FDB."""
        return self._fdb_entry is not None

    @property
    def mac_address(self) -> str:
        """Return the MAC address."""
        return self._mac

    @property
    def extra_state_attributes(self) -> dict:
        """Return the switch port this device is connected to."""
        entry = self._fdb_entry
        if not entry or entry.if_index is None:
            return {}
        port = self.coordinator.data.ports.get(entry.if_index)
        if not port:
            return {"if_index": entry.if_index}
        return {
            "if_index": entry.if_index,
            "port": port.alias or port.name,
        }
