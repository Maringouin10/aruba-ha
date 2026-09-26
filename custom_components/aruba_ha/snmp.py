"""Thin async SNMP client wrapper around pysnmp for the Aruba HA integration.

Only plain numeric OIDs are used (no compiled MIB files needed), and both
SNMPv2c (community string) and SNMPv3 (USM) are supported.
"""
from __future__ import annotations

import logging
from typing import Any

from pysnmp.error import PySnmpError
from pysnmp.hlapi.v3arch.asyncio import (
    USM_AUTH_HMAC96_MD5,
    USM_AUTH_HMAC96_SHA,
    USM_AUTH_HMAC128_SHA224,
    USM_AUTH_HMAC192_SHA256,
    USM_AUTH_HMAC256_SHA384,
    USM_AUTH_HMAC384_SHA512,
    USM_AUTH_NONE,
    USM_PRIV_CBC56_DES,
    USM_PRIV_CBC168_3DES,
    USM_PRIV_CFB128_AES,
    USM_PRIV_CFB192_AES,
    USM_PRIV_CFB256_AES,
    USM_PRIV_NONE,
    CommunityData,
    ContextData,
    Integer,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    bulk_walk_cmd,
    get_cmd,
    set_cmd,
)

from .const import (
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
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
)

_LOGGER = logging.getLogger(__name__)

AUTH_PROTOCOL_MAP = {
    SNMP_V3_AUTH_NONE: USM_AUTH_NONE,
    SNMP_V3_AUTH_MD5: USM_AUTH_HMAC96_MD5,
    SNMP_V3_AUTH_SHA: USM_AUTH_HMAC96_SHA,
    SNMP_V3_AUTH_SHA224: USM_AUTH_HMAC128_SHA224,
    SNMP_V3_AUTH_SHA256: USM_AUTH_HMAC192_SHA256,
    SNMP_V3_AUTH_SHA384: USM_AUTH_HMAC256_SHA384,
    SNMP_V3_AUTH_SHA512: USM_AUTH_HMAC384_SHA512,
}

PRIV_PROTOCOL_MAP = {
    SNMP_V3_PRIV_NONE: USM_PRIV_NONE,
    SNMP_V3_PRIV_DES: USM_PRIV_CBC56_DES,
    SNMP_V3_PRIV_3DES: USM_PRIV_CBC168_3DES,
    SNMP_V3_PRIV_AES128: USM_PRIV_CFB128_AES,
    SNMP_V3_PRIV_AES192: USM_PRIV_CFB192_AES,
    SNMP_V3_PRIV_AES256: USM_PRIV_CFB256_AES,
}


class ArubaSnmpError(Exception):
    """Raised when an SNMP operation against the switch fails."""


def build_read_auth(data: dict[str, Any]):
    """Build the pysnmp auth object used for GET/WALK operations."""
    return _build_auth(data, community_key="community_read")


def build_write_auth(data: dict[str, Any]):
    """Build the pysnmp auth object used for SET operations, if configured."""
    if data.get("snmp_version") == SNMP_V2C:
        community = data.get("community_write")
        if not community:
            return None
        return _build_auth(data, community_key="community_write")
    # SNMPv3 uses a single user for both read and write access.
    return _build_auth(data, community_key="community_read")


def _build_auth(data: dict[str, Any], community_key: str):
    if data.get("snmp_version") == SNMP_V3:
        auth_protocol_key = data.get("v3_auth_protocol", SNMP_V3_AUTH_NONE)
        priv_protocol_key = data.get("v3_priv_protocol", SNMP_V3_PRIV_NONE)

        kwargs: dict[str, Any] = {}
        if auth_protocol_key != SNMP_V3_AUTH_NONE:
            kwargs["authKey"] = data["v3_auth_key"]
            kwargs["authProtocol"] = AUTH_PROTOCOL_MAP[auth_protocol_key]
            if priv_protocol_key != SNMP_V3_PRIV_NONE:
                kwargs["privKey"] = data["v3_priv_key"]
                kwargs["privProtocol"] = PRIV_PROTOCOL_MAP[priv_protocol_key]

        return UsmUserData(data["v3_username"], **kwargs)

    return CommunityData(data.get(community_key), mpModel=1)


def _pythonize(value: Any) -> Any:
    """Convert a pysnmp value into a plain Python int/bytes/str/None."""
    from pysnmp.proto.rfc1905 import NoSuchInstance, NoSuchObject
    from pysnmp.proto.rfc1902 import OctetString

    if isinstance(value, (NoSuchObject, NoSuchInstance)):
        return None
    if isinstance(value, OctetString):
        return bytes(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def format_mac(raw: bytes) -> str | None:
    """Format a 6-byte physical address as aa:bb:cc:dd:ee:ff."""
    if not raw or len(raw) != 6:
        return None
    return ":".join(f"{b:02x}" for b in raw)


def decode_text(value: Any) -> str:
    """Decode an OctetString-derived value into a display string."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip("\x00").strip()
    return str(value)


class ArubaSnmpClient:
    """Async SNMP client for a single Aruba switch."""

    def __init__(
        self,
        host: str,
        port: int,
        read_auth,
        write_auth,
        timeout: int = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ) -> None:
        """Initialize the client."""
        self._host = host
        self._port = port
        self._read_auth = read_auth
        self._write_auth = write_auth
        self._timeout = timeout
        self._retries = retries
        self._engine = SnmpEngine()
        self._context = ContextData()
        self._transport_target = None

    @property
    def can_write(self) -> bool:
        """Return True if write (SET) credentials are configured."""
        return self._write_auth is not None

    @property
    def host(self) -> str:
        """Return the switch's configured host/IP."""
        return self._host

    async def _get_transport(self):
        if self._transport_target is None:
            try:
                self._transport_target = await UdpTransportTarget.create(
                    (self._host, self._port),
                    timeout=self._timeout,
                    retries=self._retries,
                )
            except PySnmpError as err:
                raise ArubaSnmpError(f"Cannot resolve/reach {self._host}: {err}") from err
        return self._transport_target

    async def async_get(self, oid: str) -> Any:
        """Perform a single SNMP GET and return the decoded value."""
        target = await self._get_transport()
        try:
            error_indication, error_status, error_index, var_binds = await get_cmd(
                self._engine,
                self._read_auth,
                target,
                self._context,
                ObjectType(ObjectIdentity(oid)),
            )
        except PySnmpError as err:
            raise ArubaSnmpError(str(err)) from err

        if error_indication:
            raise ArubaSnmpError(str(error_indication))
        if error_status:
            raise ArubaSnmpError(
                f"{error_status.prettyPrint()} at "
                f"{var_binds[int(error_index) - 1][0] if error_index else '?'}"
            )

        _, value = var_binds[0]
        return _pythonize(value)

    async def async_get_many(self, oids: list[str]) -> dict[str, Any]:
        """Perform a single SNMP GET for several scalar OIDs at once."""
        target = await self._get_transport()
        try:
            error_indication, error_status, error_index, var_binds = await get_cmd(
                self._engine,
                self._read_auth,
                target,
                self._context,
                *(ObjectType(ObjectIdentity(oid)) for oid in oids),
            )
        except PySnmpError as err:
            raise ArubaSnmpError(str(err)) from err

        if error_indication:
            raise ArubaSnmpError(str(error_indication))

        return {oid: _pythonize(value) for oid, (_, value) in zip(oids, var_binds)}

    async def async_walk(self, oid_prefix: str) -> dict[str, Any]:
        """Walk a MIB subtree and return {index_suffix: value}."""
        target = await self._get_transport()
        result: dict[str, Any] = {}
        try:
            async for (
                error_indication,
                error_status,
                error_index,
                var_binds,
            ) in bulk_walk_cmd(
                self._engine,
                self._read_auth,
                target,
                self._context,
                0,
                25,
                ObjectType(ObjectIdentity(oid_prefix)),
                lexicographicMode=False,
            ):
                if error_indication:
                    raise ArubaSnmpError(str(error_indication))
                if error_status:
                    # noSuchName on the very first row means the table/OID
                    # is simply not implemented on this device; treat as empty.
                    break
                for name, value in var_binds:
                    oid_str = str(name)
                    if not oid_str.startswith(oid_prefix + "."):
                        continue
                    suffix = oid_str[len(oid_prefix) + 1 :]
                    result[suffix] = _pythonize(value)
        except PySnmpError as err:
            raise ArubaSnmpError(str(err)) from err
        return result

    async def async_set(self, oid: str, value: int) -> None:
        """Perform an SNMP SET of an INTEGER value."""
        if self._write_auth is None:
            raise ArubaSnmpError("No write (RW) SNMP credentials configured")

        target = await self._get_transport()
        try:
            error_indication, error_status, error_index, var_binds = await set_cmd(
                self._engine,
                self._write_auth,
                target,
                self._context,
                ObjectType(ObjectIdentity(oid), Integer(value)),
            )
        except PySnmpError as err:
            raise ArubaSnmpError(str(err)) from err

        if error_indication:
            raise ArubaSnmpError(str(error_indication))
        if error_status:
            raise ArubaSnmpError(
                f"{error_status.prettyPrint()} at "
                f"{var_binds[int(error_index) - 1][0] if error_index else '?'}"
            )
