"""Config flow de l'intégration R-GDS."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client

from .api import RgdsApiClient, RgdsAuthError, RgdsError
from .const import (
    CONF_INCLUDE_SUBSCRIPTION,
    CONF_METER_NAME,
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

_LOGGER = logging.getLogger(__name__)


class RgdsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Gère l'ajout d'une intégration R-GDS."""

    VERSION = 1

    def __init__(self) -> None:
        self._username: str | None = None
        self._password: str | None = None
        self._meters: dict[str, dict[str, str]] = {}  # pce_id -> infos

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape 1 : identifiants."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = RgdsApiClient(
                aiohttp_client.async_get_clientsession(self.hass),
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                await client.async_login()
                subs = await client.async_get_subscriptions()
            except RgdsAuthError:
                errors["base"] = "invalid_auth"
            except RgdsError:
                errors["base"] = "cannot_connect"
            else:
                self._username = user_input[CONF_USERNAME]
                self._password = user_input[CONF_PASSWORD]
                for sub in subs:
                    for m in sub.meters:
                        label = m.name
                        if m.city:
                            label += f" ({m.city})"
                        label += f" — {m.reference}"
                        self._meters[m.id] = {
                            CONF_SUBSCRIPTION_ID: sub.id,
                            CONF_PCE_ID: m.id,
                            CONF_METER_REF: m.reference,
                            CONF_METER_NAME: m.name,
                            "label": label,
                        }
                if not self._meters:
                    errors["base"] = "no_meters"
                else:
                    return await self.async_step_meter()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_meter(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape 2 : choix du compteur (auto si un seul)."""
        if len(self._meters) == 1:
            pce_id = next(iter(self._meters))
            return await self._create(pce_id)

        if user_input is not None:
            return await self._create(user_input[CONF_PCE_ID])

        return self.async_show_form(
            step_id="meter",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PCE_ID): vol.In(
                        {pid: m["label"] for pid, m in self._meters.items()}
                    )
                }
            ),
        )

    async def _create(self, pce_id: str) -> ConfigFlowResult:
        meter = self._meters[pce_id]
        await self.async_set_unique_id(pce_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=meter["label"],
            data={
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_SUBSCRIPTION_ID: meter[CONF_SUBSCRIPTION_ID],
                CONF_PCE_ID: pce_id,
                CONF_METER_REF: meter[CONF_METER_REF],
                CONF_METER_NAME: meter[CONF_METER_NAME],
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return RgdsOptionsFlow()


class RgdsOptionsFlow(OptionsFlow):
    """Options : lissage des données, intégration de l'abonnement."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SMOOTHING,
                        default=opts.get(CONF_SMOOTHING, DEFAULT_SMOOTHING),
                    ): bool,
                    vol.Required(
                        CONF_INCLUDE_SUBSCRIPTION,
                        default=opts.get(
                            CONF_INCLUDE_SUBSCRIPTION, DEFAULT_INCLUDE_SUBSCRIPTION
                        ),
                    ): bool,
                }
            ),
        )
