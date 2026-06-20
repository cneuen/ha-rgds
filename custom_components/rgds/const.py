"""Constantes de l'intégration R-GDS."""
from __future__ import annotations

from zoneinfo import ZoneInfo

DOMAIN = "rgds"
PARIS = ZoneInfo("Europe/Paris")

# Plateforme R-groupe / Keycloak « medley » (partagée par les portails monespace).
TOKEN_URL = "https://r-auth-e.r-groupe.fr/auth/realms/medley/protocol/openid-connect/token"
CLIENT_ID = "medley-web"
API_BASE = "https://monespace.r-gds.fr"

# Clés de configuration (entry.data)
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SUBSCRIPTION_ID = "subscription_id"
CONF_PCE_ID = "pce_id"
CONF_METER_REF = "meter_ref"
CONF_METER_NAME = "meter_name"

# Options (entry.options)
CONF_INCLUDE_SUBSCRIPTION = "include_subscription"  # intégrer l'abonnement au coût
DEFAULT_INCLUDE_SUBSCRIPTION = False
CONF_SMOOTHING = "smoothing"  # données lissées (True) ou réelles/index (False)
DEFAULT_SMOOTHING = True

# Préfixe des statistiques externes (statistic_id = "rgds:<...>")
STAT_PREFIX = DOMAIN
