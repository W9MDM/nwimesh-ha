"""Constants for the NWI Mesh integration."""

DOMAIN = "nwimesh"

CONF_HOPWATCH_URL = "hopwatch_url"
CONF_ROOT_TOPIC = "root_topic"
CONF_CHANNELS = "channels"
CONF_TLS = "tls"
CONF_HISTORY = "history"
CONF_BROKER_NAME = "broker_name"

DEFAULT_NAME = "NWI Mesh"
DEFAULT_HOPWATCH_URL = "https://hopwatch.nwimesh.net"
DEFAULT_HOST = "mqtt.nwimesh.net"
DEFAULT_PORT = 1883
# Public community credentials published on nwimesh.net/mqtt-settings
DEFAULT_USERNAME = "meshdev"
DEFAULT_PASSWORD = "large4cats"
DEFAULT_ROOT_TOPIC = "msh/US/IN/NWI"
DEFAULT_CHANNELS = "LongFast=AQ==, LongTurbo=AQ=="
DEFAULT_HISTORY = 50
DEFAULT_BROKER_NAME = "NWIMesh"

STATS_PATH = "/api/v1/stats"
STATS_INTERVAL = 300  # seconds; please be kind to the community server

EVENT_MESSAGE = f"{DOMAIN}_message"
# HopWatch republishes decoded public-channel text here (under the root topic)
HOPWATCH_TEXT_TOPIC = "hopwatch/v1/text"
STORAGE_VERSION = 1
MAX_NODES = 3000
