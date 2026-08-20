"""Constants for the Hager flow integration."""

from datetime import timedelta

DOMAIN = "hager_flow"

DEFAULT_BASE_URL = "https://e3dc.e3dc.com"

# Shown to the user in the config flow; translation strings must not
# contain URLs themselves, so it is passed in as a placeholder.
PORTAL_URL = "https://flow.hager.com"

CONF_REAUTH_TOKEN = "reauth_token"
CONF_SERIAL = "serial"

# Live values update every few seconds on the portal side.
UPDATE_INTERVAL = timedelta(seconds=30)

# Energy counters only advance on a 15 minute grid, so polling them on every
# cycle would be wasted requests.
ENERGY_UPDATE_INTERVAL = timedelta(minutes=5)

MANUFACTURER = "Hager Energy GmbH"
