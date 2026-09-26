"""Switch entities to enable/disable Aruba ports from Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, IF_STATUS_DOWN, IF_STATUS_UP, OID_IF_ADMIN_STATUS
from .coordinator import ArubaDataUpdateCoordinator
from .entity import ArubaEntity
from .snmp import ArubaSnmpError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Aruba port control switches from a config entry."""
    coordinator: ArubaDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    if not coordinator.client.can_write:
        _LOGGER.warning(
            "Le contrôle des ports est activé mais aucun identifiant SNMP en écriture "
            "n'est configuré pour %s ; aucune entité switch ne sera créée.",
            entry.title,
        )
        return

    async_add_entities(
        ArubaPortAdminSwitch(coordinator, if_index) for if_index in coordinator.data.ports
    )


class ArubaPortAdminSwitch(ArubaEntity, SwitchEntity):
    """Enable/disable a switch port (ifAdminStatus SNMP SET)."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:ethernet"

    def __init__(self, coordinator: ArubaDataUpdateCoordinator, if_index: int) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._if_index = if_index
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{if_index}_admin"

    @property
    def _port(self):
        return self.coordinator.data.ports.get(self._if_index)

    @property
    def available(self) -> bool:
        """Return True if the port is still reported by the switch."""
        return super().available and self._port is not None

    @property
    def name(self) -> str:
        """Return the entity name."""
        port = self._port
        label = (port.alias or port.name) if port else str(self._if_index)
        return f"Port {label} activé"

    @property
    def is_on(self) -> bool | None:
        """Return True if the port is administratively enabled."""
        port = self._port
        if not port or port.admin_status is None:
            return None
        return port.admin_status == IF_STATUS_UP

    async def async_turn_on(self, **kwargs) -> None:
        """Enable the port."""
        await self._async_set_admin_status(IF_STATUS_UP)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable the port."""
        await self._async_set_admin_status(IF_STATUS_DOWN)

    async def _async_set_admin_status(self, status: int) -> None:
        oid = f"{OID_IF_ADMIN_STATUS}.{self._if_index}"
        try:
            await self.coordinator.client.async_set(oid, status)
        except ArubaSnmpError as err:
            raise HomeAssistantError(
                f"Échec de la commande SNMP SET sur le port {self._if_index}: {err}"
            ) from err
        await self.coordinator.async_request_refresh()
