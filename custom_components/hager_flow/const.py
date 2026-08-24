"""Constants for the Hager flow integration."""

from datetime import timedelta

DOMAIN = "hager_flow"

DEFAULT_BASE_URL = "https://e3dc.e3dc.com"

# The official, documented API. Authentication is an OAuth 2 client credentials
# grant against Hager Energy's Keycloak realm; the API itself is versioned in
# the path, so the version stays part of the base URL.
OFFICIAL_API_BASE_URL = "https://api.hagerenergy.com/v1"
OFFICIAL_TOKEN_URL = (
    "https://auth.hagerenergy.com/realms/customer/protocol/openid-connect/token"
)

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_INSTALLATION_ID = "installation_id"

# Which backend an entry talks to. Entries created before the official API was
# supported carry no such key, so its absence means the portal.
CONF_BACKEND = "backend"
BACKEND_PORTAL = "portal"
BACKEND_OFFICIAL = "official"

# Shown to the user in the config flow; translation strings must not
# contain URLs themselves, so it is passed in as a placeholder.
PORTAL_URL = "https://flow.hager.com"
DEVELOPER_PORTAL_URL = "https://developer.hagerenergy.com"

CONF_REAUTH_TOKEN = "reauth_token"
CONF_SERIAL = "serial"

# Both backends refresh their live values every few seconds.
UPDATE_INTERVAL = timedelta(seconds=30)

# The cumulative counters advance on a 15 minute grid on either backend and lag
# real time by about 17 minutes, so polling them on every cycle would only
# repeat the same numbers.
ENERGY_UPDATE_INTERVAL = timedelta(minutes=5)

# The production forecast is a day-ahead model output. It is refreshed during
# the day as the weather firms up, but nowhere near often enough to warrant
# more than an hourly poll.
FORECAST_UPDATE_INTERVAL = timedelta(hours=1)

MANUFACTURER = "Hager Energy GmbH"
