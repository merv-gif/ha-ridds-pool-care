"""Constants for the Ridd's Pool Care integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "ridds_pool_care"

# The one HTTP endpoint the integration talks to. It trades an integration key
# for a read-only snapshot of the owner's pools.
API_URL: Final = "https://exrxtndnwmfkrmiyyhnt.supabase.co/functions/v1/ha-connect"
APP_URL: Final = "https://pool.riddsaqua.co.za"
KEY_PAGE_URL: Final = f"{APP_URL}/customer/home-assistant"

CONF_API_KEY: Final = "api_key"
KEY_PREFIX: Final = "ridds_ha_"

DEFAULT_REFRESH_SECONDS: Final = 900
MIN_REFRESH_SECONDS: Final = 300

MANUFACTURER: Final = "Ridd's Aqua Centre"

# Fired once for every new test, visit or maintenance log that appears.
EVENT_NEW_RECORD: Final = f"{DOMAIN}_new_record"

POOL_MODELS: Final = {
    "pool": "Swimming pool",
    "spa": "Spa",
    "koi_pond": "Koi pond",
}

PLATFORMS: Final = ["binary_sensor", "sensor"]
