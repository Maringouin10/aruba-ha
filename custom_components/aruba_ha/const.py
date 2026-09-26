"""Constants for the Aruba HA (2930F / ArubaOS-Switch) integration."""
from __future__ import annotations

DOMAIN = "aruba_ha"
MANUFACTURER = "HPE Aruba Networking"

# --- Config entry keys -----------------------------------------------------

CONF_SNMP_VERSION = "snmp_version"
CONF_COMMUNITY_READ = "community_read"
CONF_COMMUNITY_WRITE = "community_write"

CONF_V3_USERNAME = "v3_username"
CONF_V3_AUTH_PROTOCOL = "v3_auth_protocol"
CONF_V3_AUTH_KEY = "v3_auth_key"
CONF_V3_PRIV_PROTOCOL = "v3_priv_protocol"
CONF_V3_PRIV_KEY = "v3_priv_key"

CONF_ENABLE_PORT_CONTROL = "enable_port_control"
CONF_ENABLE_DEVICE_TRACKER = "enable_device_tracker"

SNMP_V2C = "v2c"
SNMP_V3 = "v3"

SNMP_V3_AUTH_NONE = "none"
SNMP_V3_AUTH_MD5 = "md5"
SNMP_V3_AUTH_SHA = "sha"
SNMP_V3_AUTH_SHA224 = "sha224"
SNMP_V3_AUTH_SHA256 = "sha256"
SNMP_V3_AUTH_SHA384 = "sha384"
SNMP_V3_AUTH_SHA512 = "sha512"

SNMP_V3_PRIV_NONE = "none"
SNMP_V3_PRIV_DES = "des"
SNMP_V3_PRIV_3DES = "3des"
SNMP_V3_PRIV_AES128 = "aes128"
SNMP_V3_PRIV_AES192 = "aes192"
SNMP_V3_PRIV_AES256 = "aes256"

DEFAULT_PORT = 161
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_TIMEOUT = 5
DEFAULT_RETRIES = 1

# --- SNMP OIDs ---------------------------------------------------------
# Standard MIBs only. Kept as plain dotted strings (no MIB compilation
# needed) so this integration has zero dependency on external .mib files.

# SNMPv2-MIB / RFC1213 system group
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"
OID_SYS_LOCATION = "1.3.6.1.2.1.1.6.0"

# IF-MIB (RFC 2863) ifTable
OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
OID_IF_TYPE = "1.3.6.1.2.1.2.2.1.3"
OID_IF_PHYS_ADDRESS = "1.3.6.1.2.1.2.2.1.6"
OID_IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"

# IF-MIB ifXTable (extended / high capacity counters)
OID_IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"
OID_IF_HC_IN_OCTETS = "1.3.6.1.2.1.31.1.1.1.6"
OID_IF_HC_OUT_OCTETS = "1.3.6.1.2.1.31.1.1.1.10"
OID_IF_HIGH_SPEED = "1.3.6.1.2.1.31.1.1.1.15"  # Mbps
OID_IF_CONNECTOR_PRESENT = "1.3.6.1.2.1.31.1.1.1.17"
OID_IF_ALIAS = "1.3.6.1.2.1.31.1.1.1.18"

IF_STATUS_UP = 1
IF_STATUS_DOWN = 2
IF_STATUS_TESTING = 3

# POWER-ETHERNET-MIB (RFC 3621) - standard, present on every PoE switch
OID_PETH_PSE_PORT_ADMIN_ENABLE = "1.3.6.1.2.1.105.1.1.1.2"
OID_PETH_PSE_PORT_DETECTION_STATUS = "1.3.6.1.2.1.105.1.1.1.3"
OID_PETH_PSE_PORT_POWER_PRIORITY = "1.3.6.1.2.1.105.1.1.1.4"
OID_PETH_PSE_PORT_POWER_CLASS = "1.3.6.1.2.1.105.1.1.1.6"
OID_PETH_MAIN_PSE_OPER_STATUS = "1.3.6.1.2.1.105.1.3.1.1.3"
OID_PETH_MAIN_PSE_CONSUMPTION_POWER = "1.3.6.1.2.1.105.1.3.1.1.4"  # mW

PETH_DETECTION_DELIVERING_POWER = 3

# HP-ICF-POE-MIB - vendor extension, augments pethPsePortTable with the
# same (group, port) index. Gives actual per-port power draw in Watts.
# Not guaranteed present on every firmware; treated as best-effort.
OID_HPICF_POE_PORT_POWER = "1.3.6.1.4.1.11.2.14.11.5.1.1.1.1.2"  # Watts

# BRIDGE-MIB (RFC 1493) - forwarding database, used for device tracking
OID_DOT1D_TP_FDB_PORT = "1.3.6.1.2.1.17.4.3.1.2"
OID_DOT1D_TP_FDB_STATUS = "1.3.6.1.2.1.17.4.3.1.3"
OID_DOT1D_BASE_PORT_IF_INDEX = "1.3.6.1.2.1.17.1.4.1.2"

DOT1D_FDB_STATUS_LEARNED = 3

ATTR_PORT_NUMBER = "port_number"
ATTR_IF_INDEX = "if_index"
