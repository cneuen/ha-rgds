"""Coordinator R-GDS : récupère la conso et alimente les statistiques HA."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.components.recorder.util import get_instance
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import RgdsApiClient, RgdsAuthError, Reading
from .const import DOMAIN, PARIS

_LOGGER = logging.getLogger(__name__)

# Backfill initial : N années d'historique. Fenêtre de rafraîchissement (jours)
# pour capter les révisions rétroactives de R-GDS sur les mois récents.
BACKFILL_YEARS = 11
REFRESH_DAYS = 40
# Rafraîchissement toutes les heures (R-GDS publie à des heures variables dans
# la journée ; un poll horaire capte la nouvelle journée rapidement). + refresh
# au démarrage (async_config_entry_first_refresh).
UPDATE_INTERVAL = timedelta(hours=1)


class RgdsCoordinator(DataUpdateCoordinator[dict]):
    """Récupère les données R-GDS, alimente capteurs + statistiques."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: RgdsApiClient,
        subscription_id: str,
        pce_id: str,
        meter_ref: str,
        smoothing: bool = True,
        include_subscription: bool = False,
    ) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.client = client
        self._sub = subscription_id
        self._pce = pce_id
        self._smoothing = smoothing
        self._include_sub = include_subscription
        slug = meter_ref or pce_id.replace("-", "")
        self.stat_volume = f"{DOMAIN}:{slug}_volume"
        self.stat_energy = f"{DOMAIN}:{slug}_energy"
        self.stat_cost = f"{DOMAIN}:{slug}_cost"
        self._name_prefix = f"R-GDS {meter_ref}".strip()

        @callback
        def _dummy() -> None:
            pass

        # garantit que le coordinator continue de tourner même sans capteur abonné
        self.async_add_listener(_dummy)

    # ------------------------------------------------------------------ #
    async def _async_update_data(self) -> dict:
        try:
            await self.client.async_login()
        except RgdsAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err

        # données « instantanées » pour les capteurs
        tariff = await self.client.async_get_tariff(self._sub, self._pce)
        prices = await self.client.async_get_prices(self._sub, self._pce)
        year = datetime.now(PARIS).year
        yearly = await self.client.async_get_yearly(self._sub, self._pce, year)

        await self._insert_statistics(prices, tariff)

        last_reading = await self._last_real_reading()
        monthly = await self._month_totals()
        return {
            "tariff": tariff,
            "yearly": yearly,
            "last_reading": last_reading,
            "current_price": tariff.current_kwh_price_ttc,
            "monthly_volume": monthly["volume"],
            "monthly_energy": monthly["energy"],
            "monthly_cost": monthly["cost"],
        }

    async def _month_totals(self) -> dict[str, float | None]:
        """Consommation du mois en cours (delta des statistiques sur le mois)."""
        now = datetime.now(PARIS)
        start = datetime(now.year, now.month, 1, 0, 0, tzinfo=PARIS)
        stats = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period, self.hass, start, None,
            {self.stat_volume, self.stat_energy, self.stat_cost}, "month", None, {"change"},
        )

        def chg(sid: str) -> float | None:
            rows = stats.get(sid, [])
            return round(sum((r.get("change") or 0) for r in rows), 3) if rows else None

        return {
            "volume": chg(self.stat_volume),
            "energy": chg(self.stat_energy),
            "cost": chg(self.stat_cost),
        }

    # ------------------------------------------------------------------ #
    async def _last_real_reading(self) -> Reading | None:
        now = datetime.now(PARIS).replace(tzinfo=None)
        reads = await self.client.async_get_consumption(
            self._sub, self._pce, now - timedelta(days=20), now, smoothing=False
        )
        real = [r for r in reads if r.end_index is not None and not r.generated]
        return real[-1] if real else None

    def _dt(self, date_str: str) -> datetime:
        y, m, d = map(int, date_str.split("-"))
        return datetime(y, m, d, 0, 0, tzinfo=PARIS)

    async def _sum_before(self, win_start: datetime, ids: set[str]) -> dict[str, float]:
        """Cumul de chaque stat juste avant win_start (continuité du refresh)."""
        stats = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            datetime(2010, 1, 1, tzinfo=PARIS),
            win_start,
            ids,
            "day",
            None,
            {"sum"},
        )
        out: dict[str, float] = {}
        ws = win_start.timestamp()
        for sid in ids:
            rows = [r for r in stats.get(sid, []) if r["start"] < ws]
            out[sid] = float(rows[-1]["sum"]) if rows else 0.0
        return out

    async def _backfill_start(self, now: datetime) -> datetime:
        """Début du backfill = date de début d'abonnement (tout l'historique).

        Repli sur BACKFILL_YEARS si la date n'est pas disponible.
        """
        try:
            for sub in await self.client.async_get_subscriptions():
                if sub.id == self._sub and sub.from_date:
                    d = datetime.fromisoformat(sub.from_date.replace("Z", "+00:00"))
                    return datetime(d.year, d.month, 1)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("R-GDS: fromDate indisponible (%s), repli %s ans", err, BACKFILL_YEARS)
        return datetime(now.year - BACKFILL_YEARS, 1, 1)

    async def _insert_statistics(self, prices: dict[str, float], tariff) -> None:
        ids = {self.stat_volume, self.stat_energy, self.stat_cost}
        lasts: dict[str, list | None] = {}
        for sid in ids:
            st = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 1, sid, True, set()
            )
            lasts[sid] = st.get(sid) if st else None
        now = datetime.now(PARIS).replace(tzinfo=None)

        # backfill si AU MOINS une des 3 stats est absente (évite les désyncs)
        if not all(lasts.values()):
            win_start = await self._backfill_start(now)
            _LOGGER.debug("R-GDS: backfill complet depuis %s", win_start.date())
            base = {sid: 0.0 for sid in ids}
        else:
            last_ts = lasts[self.stat_volume][0]["start"]
            win_start_dt = datetime.fromtimestamp(last_ts, PARIS) - timedelta(days=REFRESH_DAYS)
            win_start = win_start_dt.replace(tzinfo=None)
            base = await self._sum_before(
                datetime(win_start.year, win_start.month, win_start.day, 0, 0, tzinfo=PARIS),
                ids,
            )

        reads = await self.client.async_get_consumption(
            self._sub, self._pce, win_start, now, smoothing=self._smoothing
        )
        if not reads:
            _LOGGER.debug("R-GDS: aucune donnée sur la fenêtre")
            return

        daily_sub = 0.0
        if self._include_sub and tariff.annual_subscription_ttc:
            daily_sub = tariff.annual_subscription_ttc / 365.0

        v_sum = base[self.stat_volume]
        e_sum = base[self.stat_energy]
        c_sum = base[self.stat_cost]
        v_stats: list[StatisticData] = []
        e_stats: list[StatisticData] = []
        c_stats: list[StatisticData] = []

        # Principe : on ne fabrique rien. Volume = ce que l'API donne en m³.
        # Énergie = uniquement si l'API fournit un vrai kWh (pas de calcul depuis m³).
        # Coût = uniquement si un prix existe pour ce mois (pas de prix par défaut).
        for r in reads:
            start = self._dt(r.date)
            if r.volume_m3 is not None:
                v_sum += r.volume_m3
                v_stats.append(StatisticData(start=start, state=r.volume_m3, sum=round(v_sum, 4)))
            ene = r.energy_kwh
            if ene:
                e_sum += ene
                e_stats.append(StatisticData(start=start, state=ene, sum=round(e_sum, 4)))
                price = prices.get(r.date[:7])
                if price is not None:
                    cost = ene * price + daily_sub
                    c_sum += cost
                    c_stats.append(StatisticData(start=start, state=cost, sum=round(c_sum, 4)))

        if v_stats:
            async_add_external_statistics(self.hass, self._meta(
                self.stat_volume, f"{self._name_prefix} volume",
                UnitOfVolume.CUBIC_METERS, "volume"), v_stats)
        if e_stats:
            async_add_external_statistics(self.hass, self._meta(
                self.stat_energy, f"{self._name_prefix} énergie",
                UnitOfEnergy.KILO_WATT_HOUR, "energy"), e_stats)
        if c_stats:
            # coût : pas d'unit_class (la monnaie n'est pas une classe convertible)
            async_add_external_statistics(self.hass, self._meta(
                self.stat_cost, f"{self._name_prefix} coût",
                CURRENCY_EURO, None), c_stats)
        _LOGGER.debug("R-GDS: importé v=%d e=%d c=%d (depuis %s)",
                      len(v_stats), len(e_stats), len(c_stats), win_start.date())

    def _meta(
        self, stat_id: str, name: str, unit: str, unit_class: str | None
    ) -> StatisticMetaData:
        return StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=name,
            source=DOMAIN,
            statistic_id=stat_id,
            unit_of_measurement=unit,
            unit_class=unit_class,
        )
