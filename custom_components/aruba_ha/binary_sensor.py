"""Binary sensors for the Aruba HA integration."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_IF_INDEX,
    ATTR_PORT_NUMBER,
    DOMAIN,
    IF_STATUS_UP,
    PETH_DETECTION_DELIVERING_POWER,
)
from .coordinator import ArubaDataUpdateCoordinator
from .entity import ArubaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Aruba binary sensors from a config entry."""
    coordinator: ArubaDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[BinarySensorEntity] = [
        ArubaPortLinkBinarySensor(coordinator, if_index) for if_index in coordinator.data.ports
    ]
    entities.extend(ArubaPoeDeliveringBinarySensor(coordinator, key) for key in coordinator.data.poe_ports)

    async_add_entities(entities)


class ArubaPortLinkBinarySensor(ArubaEntity, BinarySensorEntity):
    """Whether a port's link is up (ifOperStatus)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: ArubaDataUpdateCoordinator, if_index: int) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._if_index = if_index
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{if_index}_link"

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
        return f"Port {label} lien"

    @property
    def is_on(self) -> bool | None:
        """Return True if the link is up."""
        port = self._port
        if not port or port.oper_status is None:
            return None
        return port.oper_status == IF_STATUS_UP

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra port attributes."""
        port = self._port
        if not port:
            return {}
        return {
            ATTR_IF_INDEX: port.if_index,
            ATTR_PORT_NUMBER: port.port_number,
            "admin_status_up": port.admin_status == IF_STATUS_UP,
            "mac_address": port.mac_address,
            "alias": port.alias,
        }


class ArubaPoeDeliveringBinarySensor(ArubaEntity, BinarySensorEntity):
    """Whether a PoE port is currently delivering power."""

    _attr_device_class = BinarySensorDeviceClass.POWER
    _attr_icon = "mdi:power-plug"

    def __init__(self, coordinator: ArubaDataUpdateCoordinator, key: tuple[int, int]) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        group, port = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_poe_{group}_{port}_delivering"

    @property
    def _poe(self):
        return self.coordinator.data.poe_ports.get(self._key)

    @property
    def available(self) -> bool:
        """Return True if this PoE port is still reported by the switch."""
        return super().available and self._poe is not None

    @property
    def name(self) -> str:
        """Return the entity name."""
        poe = self._poe
        port = self.coordinator.data.ports.get(poe.if_index) if poe else None
        label = (port.alias or port.name) if port else f"{self._key[0]}.{self._key[1]}"
        return f"PoE {label} alimentation active"

    @property
    def is_on(self) -> bool | None:
        """Return True if the port is delivering PoE power."""
        poe = self._poe
        if not poe or poe.detection_status is None:
            return None
        return poe.detection_status == PETH_DETECTION_DELIVERING_POWER

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra PoE attributes."""
        poe = self._poe
        if not poe:
            return {}
        return {
            "admin_enable": poe.admin_enable,
            "power_class": poe.power_class,
        }
