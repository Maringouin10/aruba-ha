"""Data update coordinator for the Aruba HA integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

import re

from .const import (
    CONF_ENABLE_DEVICE_TRACKER,
    DOT1D_FDB_STATUS_LEARNED,
    OID_DOT1D_BASE_PORT_IF_INDEX,
    OID_DOT1D_TP_FDB_PORT,
    OID_DOT1D_TP_FDB_STATUS,
    OID_HP_GLOBAL_MEM_FREE_BYTES,
    OID_HP_GLOBAL_MEM_TOTAL_BYTES,
    OID_HP_SWITCH_CPU_STAT,
    OID_HP_SYSTEM_AIR_CURRENT_TEMP,
    OID_HP_SYSTEM_AIR_NAME,
    OID_HPICF_POE_PORT_ACTUAL_POWER,
    OID_HPICF_POWER_SUPPLY_STATUS,
    OID_HPICF_SENSOR_DESCR,
    OID_HPICF_SENSOR_STATUS,
    OID_IF_ALIAS,
    OID_IF_DESCR,
    OID_IF_ADMIN_STATUS,
    OID_IF_HC_IN_OCTETS,
    OID_IF_HC_OUT_OCTETS,
    OID_IF_HIGH_SPEED,
    OID_IF_NAME,
    OID_IF_OPER_STATUS,
    OID_IF_PHYS_ADDRESS,
    OID_PETH_MAIN_PSE_CONSUMPTION_POWER,
    OID_PETH_PSE_PORT_ADMIN_ENABLE,
    OID_PETH_PSE_PORT_DETECTION_STATUS,
    OID_PETH_PSE_PORT_POWER_CLASS,
    OID_SYS_DESCR,
    OID_SYS_LOCATION,
    OID_SYS_NAME,
    OID_SYS_UPTIME,
)
from .snmp import ArubaSnmpClient, ArubaSnmpError, decode_text, format_mac

_LOGGER = logging.getLogger(__name__)


@dataclass
class PortData:
    """State of a single switch interface."""

    if_index: int
    name: str
    alias: str | None
    admin_status: int | None
    oper_status: int | None
    speed_mbps: int | None
    mac_address: str | None
    in_octets: int | None
    out_octets: int | None
    port_number: int | None = None


@dataclass
class PoePortData:
    """State of a single Power-over-Ethernet port."""

    group: int
    port: int
    admin_enable: bool
    detection_status: int | None
    power_class: int | None
    power_watts: float | None
    if_index: int | None = None


@dataclass
class FdbEntry:
    """A learned MAC address on the switch."""

    mac_address: str
    if_index: int | None


@dataclass
class HwSensorData:
    """A generic hardware sensor (typically a fan) from hpicfSensorTable."""

    index: int
    descr: str
    status: int | None


@dataclass
class PowerSupplyData:
    """A power supply unit from hpicfPowerSupplyTable."""

    slot: int
    status: int | None


@dataclass
class TemperatureSensorData:
    """A temperature probe from hpSystemAirTempTable."""

    index: int
    name: str | None
    celsius: float | None


@dataclass
class ArubaSwitchData:
    """Full snapshot of the switch, refreshed on every coordinator update."""

    sys_descr: str | None = None
    sys_name: str | None = None
    sys_location: str | None = None
    sys_uptime: int | None = None  # seconds
    ports: dict[int, PortData] = field(default_factory=dict)
    poe_ports: dict[tuple[int, int], PoePortData] = field(default_factory=dict)
    poe_total_watts: float | None = None
    fdb: list[FdbEntry] = field(default_factory=list)
    cpu_percent: int | None = None
    mem_total_bytes: int | None = None
    mem_free_bytes: int | None = None
    mem_used_percent: float | None = None
    hw_sensors: dict[int, HwSensorData] = field(default_factory=dict)
    power_supplies: dict[int, PowerSupplyData] = field(default_factory=dict)
    temperatures: dict[int, TemperatureSensorData] = field(default_factory=dict)


class ArubaDataUpdateCoordinator(DataUpdateCoordinator[ArubaSwitchData]):
    """Poll an Aruba switch over SNMP on a fixed interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ArubaSnmpClient,
        scan_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{entry.title} (Aruba SNMP)",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.entry = entry
        self.client = client
        self.enable_device_tracker = entry.options.get(
            CONF_ENABLE_DEVICE_TRACKER,
            entry.data.get(CONF_ENABLE_DEVICE_TRACKER, False),
        )

    async def _async_update_data(self) -> ArubaSwitchData:
        try:
            return await self._async_fetch()
        except ArubaSnmpError as err:
            raise UpdateFailed(f"Erreur SNMP vers {self.client.host}: {err}") from err

    async def _async_fetch(self) -> ArubaSwitchData:
        data = ArubaSwitchData()

        system = await self.client.async_get_many(
            [OID_SYS_DESCR, OID_SYS_NAME, OID_SYS_LOCATION, OID_SYS_UPTIME]
        )
        data.sys_descr = decode_text(system.get(OID_SYS_DESCR)) if system.get(OID_SYS_DESCR) is not None else None
        data.sys_name = decode_text(system.get(OID_SYS_NAME)) if system.get(OID_SYS_NAME) is not None else None
        data.sys_location = (
            decode_text(system.get(OID_SYS_LOCATION)) if system.get(OID_SYS_LOCATION) is not None else None
        )
        uptime_ticks = system.get(OID_SYS_UPTIME)
        data.sys_uptime = int(uptime_ticks / 100) if isinstance(uptime_ticks, int) else None

        await self._async_fetch_ports(data)
        await self._async_fetch_poe(data)
        await self._async_fetch_health(data)

        if self.enable_device_tracker:
            await self._async_fetch_fdb(data)

        return data

    async def _async_fetch_ports(self, data: ArubaSwitchData) -> None:
        if_descr = await self.client.async_walk(OID_IF_DESCR)
        if_admin = await self.client.async_walk(OID_IF_ADMIN_STATUS)
        if_oper = await self.client.async_walk(OID_IF_OPER_STATUS)
        if_phys = await self.client.async_walk(OID_IF_PHYS_ADDRESS)
        if_name = await self.client.async_walk(OID_IF_NAME)
        if_alias = await self.client.async_walk(OID_IF_ALIAS)
        if_speed = await self.client.async_walk(OID_IF_HIGH_SPEED)
        if_hc_in = await self.client.async_walk(OID_IF_HC_IN_OCTETS)
        if_hc_out = await self.client.async_walk(OID_IF_HC_OUT_OCTETS)

        for suffix, descr in if_descr.items():
            if_index = int(suffix)
            name = decode_text(if_name.get(suffix)) if if_name.get(suffix) is not None else decode_text(descr)
            alias = decode_text(if_alias[suffix]) if if_alias.get(suffix) else None
            mac_raw = if_phys.get(suffix)
            port_number = _port_number_from_name(name) or _port_number_from_name(decode_text(descr))

            data.ports[if_index] = PortData(
                if_index=if_index,
                name=name or decode_text(descr),
                alias=alias,
                admin_status=if_admin.get(suffix),
                oper_status=if_oper.get(suffix),
                speed_mbps=if_speed.get(suffix),
                mac_address=format_mac(mac_raw) if isinstance(mac_raw, bytes) else None,
                in_octets=if_hc_in.get(suffix),
                out_octets=if_hc_out.get(suffix),
                port_number=port_number,
            )

    async def _async_fetch_poe(self, data: ArubaSwitchData) -> None:
        admin_enable = await self.client.async_walk(OID_PETH_PSE_PORT_ADMIN_ENABLE)
        if not admin_enable:
            # PoE MIB not implemented on this device/firmware.
            return

        detection = await self.client.async_walk(OID_PETH_PSE_PORT_DETECTION_STATUS)
        power_class = await self.client.async_walk(OID_PETH_PSE_PORT_POWER_CLASS)
        actual_power_mw = await self.client.async_walk(OID_HPICF_POE_PORT_ACTUAL_POWER)

        port_by_number = {
            port.port_number: port.if_index for port in data.ports.values() if port.port_number is not None
        }

        for suffix, enabled in admin_enable.items():
            group_str, _, port_str = suffix.partition(".")
            try:
                group, port = int(group_str), int(port_str)
            except ValueError:
                continue

            watts_mw = actual_power_mw.get(suffix)
            data.poe_ports[(group, port)] = PoePortData(
                group=group,
                port=port,
                admin_enable=bool(enabled),
                detection_status=detection.get(suffix),
                power_class=power_class.get(suffix),
                power_watts=watts_mw / 1000 if isinstance(watts_mw, int) else None,
                if_index=port_by_number.get(port),
            )

        main_power = await self.client.async_get_many([OID_PETH_MAIN_PSE_CONSUMPTION_POWER])
        consumption_mw = main_power.get(OID_PETH_MAIN_PSE_CONSUMPTION_POWER)
        data.poe_total_watts = consumption_mw / 1000 if isinstance(consumption_mw, int) else None

    async def _async_fetch_health(self, data: ArubaSwitchData) -> None:
        scalars = await self.client.async_get_many([OID_HP_SWITCH_CPU_STAT])
        cpu = scalars.get(OID_HP_SWITCH_CPU_STAT)
        data.cpu_percent = cpu if isinstance(cpu, int) else None

        mem_total = await self.client.async_walk(OID_HP_GLOBAL_MEM_TOTAL_BYTES)
        mem_free = await self.client.async_walk(OID_HP_GLOBAL_MEM_FREE_BYTES)
        if mem_total:
            # Fixed/standalone switches report a single memory slot; sum in
            # case a modular chassis reports several.
            total = sum(v for v in mem_total.values() if isinstance(v, int))
            free = sum(v for v in mem_free.values() if isinstance(v, int))
            data.mem_total_bytes = total
            data.mem_free_bytes = free
            data.mem_used_percent = round((total - free) / total * 100, 1) if total else None

        sensor_descr = await self.client.async_walk(OID_HPICF_SENSOR_DESCR)
        sensor_status = await self.client.async_walk(OID_HPICF_SENSOR_STATUS)
        for suffix, descr in sensor_descr.items():
            try:
                index = int(suffix)
            except ValueError:
                continue
            data.hw_sensors[index] = HwSensorData(
                index=index,
                descr=decode_text(descr) or f"Capteur {index}",
                status=sensor_status.get(suffix),
            )

        psu_status = await self.client.async_walk(OID_HPICF_POWER_SUPPLY_STATUS)
        for suffix, status in psu_status.items():
            try:
                slot = int(suffix)
            except ValueError:
                continue
            data.power_supplies[slot] = PowerSupplyData(slot=slot, status=status)

        temp_name = await self.client.async_walk(OID_HP_SYSTEM_AIR_NAME)
        temp_current = await self.client.async_walk(OID_HP_SYSTEM_AIR_CURRENT_TEMP)
        for suffix, raw_temp in temp_current.items():
            try:
                index = int(suffix)
            except ValueError:
                continue
            data.temperatures[index] = TemperatureSensorData(
                index=index,
                name=decode_text(temp_name[suffix]) if temp_name.get(suffix) else None,
                celsius=_parse_temperature(raw_temp),
            )

    async def _async_fetch_fdb(self, data: ArubaSwitchData) -> None:
        fdb_port = await self.client.async_walk(OID_DOT1D_TP_FDB_PORT)
        fdb_status = await self.client.async_walk(OID_DOT1D_TP_FDB_STATUS)
        base_port_if_index = await self.client.async_walk(OID_DOT1D_BASE_PORT_IF_INDEX)

        for suffix, bridge_port in fdb_port.items():
            if fdb_status.get(suffix) != DOT1D_FDB_STATUS_LEARNED:
                continue
            if not bridge_port:
                continue
            mac_bytes = _mac_from_oid_suffix(suffix)
            if mac_bytes is None:
                continue
            if_index = base_port_if_index.get(str(bridge_port))
            data.fdb.append(
                FdbEntry(
                    mac_address=format_mac(mac_bytes) or "",
                    if_index=int(if_index) if if_index is not None else None,
                )
            )


_TEMPERATURE_RE = re.compile(r"-?\d+(\.\d+)?")


def _parse_temperature(raw: Any) -> float | None:
    """Parse hpSystemAirCurrentTemp, an OCTET STRING like b'43C'."""
    if raw is None:
        return None
    text = decode_text(raw) if isinstance(raw, bytes) else str(raw)
    match = _TEMPERATURE_RE.search(text)
    return float(match.group()) if match else None


def _mac_from_oid_suffix(suffix: str) -> bytes | None:
    try:
        parts = [int(p) for p in suffix.split(".")]
    except ValueError:
        return None
    if len(parts) != 6 or any(p < 0 or p > 255 for p in parts):
        return None
    return bytes(parts)


def _port_number_from_name(name: str | None) -> int | None:
    if not name:
        return None
    name = name.strip()
    if name.isdigit():
        return int(name)
    return None
