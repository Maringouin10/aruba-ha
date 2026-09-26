"""Common base entity for the Aruba HA integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import ArubaDataUpdateCoordinator


class ArubaEntity(CoordinatorEntity[ArubaDataUpdateCoordinator]):
    """Base entity tied to the switch device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ArubaDataUpdateCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.entry
        sys_name = coordinator.data.sys_name if coordinator.data else None
        sys_descr = coordinator.data.sys_descr if coordinator.data else None

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=sys_name or entry.title,
            manufacturer=MANUFACTURER,
            model=_extract_model(sys_descr) or "Aruba 2930F",
            configuration_url=f"http://{entry.data['host']}/",
        )


def _extract_model(sys_descr: str | None) -> str | None:
    """Best-effort model extraction from sysDescr (e.g. 'JL260A')."""
    if not sys_descr:
        return None
    for token in sys_descr.replace(",", " ").split():
        if token.upper().startswith("JL") and len(token) >= 6:
            return token
    return None
