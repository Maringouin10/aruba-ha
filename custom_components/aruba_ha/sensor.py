"""Sensors for the Aruba HA integration."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfInformation,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

try:
    from homeassistant.const import UnitOfDataRate

    _HAS_DATA_RATE_UNIT = True
except ImportError:  # older HA core
    _HAS_DATA_RATE_UNIT = False

from .const import DOMAIN
from .coordinator import ArubaDataUpdateCoordinator
from .entity import ArubaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Aruba sensors from a config entry."""
    coordinator: ArubaDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [ArubaUptimeSensor(coordinator)]

    for if_index in coordinator.data.ports:
        entities.append(ArubaPortTrafficInSensor(coordinator, if_index))
        entities.append(ArubaPortTrafficOutSensor(coordinator, if_index))
        entities.append(ArubaPortSpeedSensor(coordinator, if_index))

    if any(p.power_watts is not None for p in coordinator.data.poe_ports.values()):
        for key in coordinator.data.poe_ports:
            entities.append(ArubaPoePortPowerSensor(coordinator, key))

    if coordinator.data.poe_total_watts is not None:
        entities.append(ArubaPoeTotalPowerSensor(coordinator))

    if coordinator.data.cpu_percent is not None:
        entities.append(ArubaCpuSensor(coordinator))

    if coordinator.data.mem_used_percent is not None:
        entities.append(ArubaMemorySensor(coordinator))

    for index in coordinator.data.temperatures:
        entities.append(ArubaTemperatureSensor(coordinator, index))

    async_add_entities(entities)


class ArubaUptimeSensor(ArubaEntity, SensorEntity):
    """Switch uptime."""

    _attr_name = "Temps de fonctionnement"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: ArubaDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_uptime"

    @property
    def native_value(self) -> int | None:
        """Return the switch uptime in seconds."""
        return self.coordinator.data.sys_uptime


class ArubaPortSensorBase(ArubaEntity, SensorEntity):
    """Base class for a per-port sensor."""

    def __init__(self, coordinator: ArubaDataUpdateCoordinator, if_index: int, key: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._if_index = if_index
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{if_index}_{key}"

    @property
    def _port(self):
        return self.coordinator.data.ports.get(self._if_index)

    @property
    def available(self) -> bool:
        """Return True if the port is still reported by the switch."""
        return super().available and self._port is not None

    def _port_label(self) -> str:
        port = self._port
        return port.alias or port.name if port else str(self._if_index)


class ArubaPortTrafficInSensor(ArubaPortSensorBase):
    """Bytes received on a port (ifHCInOctets)."""

    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.BYTES
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:download-network-outline"

    def __init__(self, coordinator: ArubaDataUpdateCoordinator, if_index: int) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, if_index, "in_octets")

    @property
    def name(self) -> str:
        """Return the entity name."""
        return f"Port {self._port_label()} octets reçus"

    @property
    def native_value(self) -> int | None:
        """Return the received byte counter."""
        return self._port.in_octets if self._port else None


class ArubaPortTrafficOutSensor(ArubaPortSensorBase):
    """Bytes sent on a port (ifHCOutOctets)."""

    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.BYTES
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:upload-network-outline"

    def __init__(self, coordinator: ArubaDataUpdateCoordinator, if_index: int) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, if_index, "out_octets")

    @property
    def name(self) -> str:
        """Return the entity name."""
        return f"Port {self._port_label()} octets envoyés"

    @property
    def native_value(self) -> int | None:
        """Return the sent byte counter."""
        return self._port.out_octets if self._port else None


class ArubaPortSpeedSensor(ArubaPortSensorBase):
    """Negotiated link speed of a port."""

    _attr_icon = "mdi:speedometer"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ArubaDataUpdateCoordinator, if_index: int) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, if_index, "speed")
        if _HAS_DATA_RATE_UNIT:
            self._attr_device_class = SensorDeviceClass.DATA_RATE
            self._attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
        else:
            self._attr_native_unit_of_measurement = "Mbit/s"

    @property
    def name(self) -> str:
        """Return the entity name."""
        return f"Port {self._port_label()} vitesse"

    @property
    def native_value(self) -> int | None:
        """Return the link speed in Mbps, or None if the port is down."""
        port = self._port
        if not port or not port.speed_mbps:
            return None
        return port.speed_mbps


class ArubaPoePortPowerSensor(ArubaEntity, SensorEntity):
    """Actual power draw of a PoE port (vendor MIB, best-effort)."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:flash"

    def __init__(self, coordinator: ArubaDataUpdateCoordinator, key: tuple[int, int]) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        group, port = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_poe_{group}_{port}_power"

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
        label = port.alias or port.name if port else f"{self._key[0]}.{self._key[1]}"
        return f"PoE {label} puissance"

    @property
    def native_value(self) -> float | None:
        """Return the actual power draw in Watts."""
        return self._poe.power_watts if self._poe else None


class ArubaPoeTotalPowerSensor(ArubaEntity, SensorEntity):
    """Total PoE power consumption of the switch."""

    _attr_name = "Puissance PoE totale"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:flash-outline"

    def __init__(self, coordinator: ArubaDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_poe_total_power"

    @property
    def native_value(self) -> float | None:
        """Return the total PoE power consumption in Watts."""
        return self.coordinator.data.poe_total_watts


class ArubaCpuSensor(ArubaEntity, SensorEntity):
    """CPU utilization of the switch (hpSwitchCpuStat)."""

    _attr_name = "Utilisation CPU"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator: ArubaDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_cpu"

    @property
    def native_value(self) -> int | None:
        """Return the CPU utilization in percent."""
        return self.coordinator.data.cpu_percent


class ArubaMemorySensor(ArubaEntity, SensorEntity):
    """Memory utilization of the switch (hpGlobalMemTable)."""

    _attr_name = "Utilisation mémoire"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:memory"

    def __init__(self, coordinator: ArubaDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_memory"

    @property
    def native_value(self) -> float | None:
        """Return the memory utilization in percent."""
        return self.coordinator.data.mem_used_percent

    @property
    def extra_state_attributes(self) -> dict:
        """Return raw byte counts."""
        data = self.coordinator.data
        return {
            "total_bytes": data.mem_total_bytes,
            "free_bytes": data.mem_free_bytes,
        }


class ArubaTemperatureSensor(ArubaEntity, SensorEntity):
    """A temperature probe (hpSystemAirTempTable)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ArubaDataUpdateCoordinator, index: int) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._index = index
        self._attr_unique_id = f"{coordinator.entry.entry_id}_temp_{index}"

    @property
    def _temp(self):
        return self.coordinator.data.temperatures.get(self._index)

    @property
    def available(self) -> bool:
        """Return True if this temperature probe is still reported."""
        return super().available and self._temp is not None

    @property
    def name(self) -> str:
        """Return the entity name."""
        temp = self._temp
        label = (temp.name if temp else None) or f"Capteur {self._index}"
        return f"Température {label}"

    @property
    def native_value(self) -> float | None:
        """Return the temperature in Celsius."""
        return self._temp.celsius if self._temp else None
