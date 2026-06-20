"""Intégration R-GDS (Gaz de Strasbourg) pour Home Assistant."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.event import async_track_time_change

from .api import RgdsApiClient
from .const import (
    CONF_INCLUDE_SUBSCRIPTION,
    CONF_METER_REF,
    CONF_PASSWORD,
    CONF_PCE_ID,
    CONF_SMOOTHING,
    CONF_SUBSCRIPTION_ID,
    CONF_USERNAME,
    DEFAULT_INCLUDE_SUBSCRIPTION,
    DEFAULT_SMOOTHING,
    DOMAIN,
)
from .coordinator import REFRESH_HOUR, RgdsCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Met en place une entrée de configuration."""
    client = RgdsApiClient(
        aiohttp_client.async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = RgdsCoordinator(
        hass,
        client,
        entry.data[CONF_SUBSCRIPTION_ID],
        entry.data[CONF_PCE_ID],
        entry.data.get(CONF_METER_REF, ""),
        smoothing=entry.options.get(CONF_SMOOTHING, DEFAULT_SMOOTHING),
        include_subscription=entry.options.get(
            CONF_INCLUDE_SUBSCRIPTION, DEFAULT_INCLUDE_SUBSCRIPTION
        ),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Rafraîchissement quotidien à 23h (après la publication R-GDS du soir),
    # en plus du refresh au démarrage (async_config_entry_first_refresh ci-dessus).
    async def _scheduled_refresh(now) -> None:
        await coordinator.async_request_refresh()

    entry.async_on_unload(
        async_track_time_change(
            hass, _scheduled_refresh, hour=REFRESH_HOUR, minute=0, second=0
        )
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recharge l'intégration quand les options changent."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge une entrée de configuration."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
