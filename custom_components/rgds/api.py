"""Client API R-GDS (portail monespace, plateforme R-groupe / Keycloak « medley »).

Module autonome : ne dépend que d'aiohttp + stdlib, donc utilisable dans Home
Assistant comme testable seul. Gère l'authentification Keycloak (direct grant
password), le rafraîchissement de token, la découverte des compteurs, la
consommation, l'historique mensuel des prix et les infos d'abonnement.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

import aiohttp

from .const import API_BASE, CLIENT_ID, TOKEN_URL

_LOGGER = logging.getLogger(__name__)
PARIS = ZoneInfo("Europe/Paris")


class RgdsError(Exception):
    """Erreur générique de l'API R-GDS."""


class RgdsAuthError(RgdsError):
    """Échec d'authentification (identifiants invalides, token refusé)."""


# --------------------------------------------------------------------------- #
# Modèles de données
# --------------------------------------------------------------------------- #
@dataclass
class GasMeter:
    """Un compteur gaz (PCE) d'un abonnement."""

    id: str
    name: str
    reference: str
    connected: bool
    city: str | None = None


@dataclass
class Subscription:
    """Un abonnement et ses compteurs."""

    id: str
    reference: str
    from_date: str | None = None  # début d'abonnement (ISO), pour le backfill complet
    meters: list[GasMeter] = field(default_factory=list)


@dataclass
class Reading:
    """Une mesure de consommation pour une journée (ou un mois agrégé).

    `generated=True` : valeur estimée/lissée par R-GDS. `generated=False` avec
    `end_index` renseigné : relevé réel. `volume_m3` est arrondi au m³ entier
    côté API (limite connue) ; l'agrégat annuel `yearly` est, lui, précis.
    """

    date: str  # "YYYY-MM-DD"
    volume_m3: float | None
    energy_kwh: float | None
    start_index: int | None
    end_index: int | None
    generated: bool


@dataclass
class TariffInfo:
    """Infos tarifaires courantes."""

    annual_subscription_ttc: float | None
    current_kwh_price_ttc: float | None


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
class RgdsApiClient:
    """Client asynchrone pour l'API interne du portail monespace R-GDS."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._access_exp: float = 0.0
        self._refresh_exp: float = 0.0

    # ---- Authentification ------------------------------------------------- #
    async def _token_request(self, data: dict[str, str]) -> dict:
        try:
            async with self._session.post(TOKEN_URL, data=data) as resp:
                body = await resp.text()
                if resp.status != 200:
                    raise RgdsAuthError(f"Token {resp.status}: {body[:200]}")
                return await resp.json()
        except aiohttp.ClientError as err:
            raise RgdsError(f"Erreur réseau (token): {err}") from err

    def _store_tokens(self, tok: dict) -> None:
        now = time.time()
        self._access_token = tok["access_token"]
        self._refresh_token = tok.get("refresh_token")
        # marges de sécurité (30 s) pour éviter d'utiliser un token expirant
        self._access_exp = now + int(tok.get("expires_in", 300)) - 30
        self._refresh_exp = now + int(tok.get("refresh_expires_in", 1800)) - 30

    async def async_login(self) -> None:
        """Authentification initiale (direct grant password)."""
        tok = await self._token_request(
            {
                "grant_type": "password",
                "client_id": CLIENT_ID,
                "username": self._username,
                "password": self._password,
                "scope": "openid",
            }
        )
        self._store_tokens(tok)
        _LOGGER.debug("R-GDS: authentification réussie")

    async def _ensure_token(self) -> None:
        """Garantit un access_token valide (refresh ou ré-login si besoin)."""
        now = time.time()
        if self._access_token and now < self._access_exp:
            return
        if self._refresh_token and now < self._refresh_exp:
            try:
                tok = await self._token_request(
                    {
                        "grant_type": "refresh_token",
                        "client_id": CLIENT_ID,
                        "refresh_token": self._refresh_token,
                    }
                )
                self._store_tokens(tok)
                return
            except RgdsAuthError:
                _LOGGER.debug("R-GDS: refresh refusé, ré-login")
        await self.async_login()

    async def _get(self, path: str) -> any:
        await self._ensure_token()
        try:
            async with self._session.get(
                f"{API_BASE}{path}",
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Accept": "application/json",
                },
            ) as resp:
                if resp.status == 401:
                    raise RgdsAuthError("401 (token rejeté)")
                body = await resp.text()
                if resp.status != 200:
                    raise RgdsError(f"GET {path} -> {resp.status}: {body[:200]}")
                return await resp.json()
        except aiohttp.ClientError as err:
            raise RgdsError(f"Erreur réseau ({path}): {err}") from err

    # ---- Découverte ------------------------------------------------------- #
    async def async_get_subscriptions(self) -> list[Subscription]:
        """Liste les abonnements et leurs compteurs (pour le config flow)."""
        data = await self._get("/api/subscription/mine?update=false")
        subs: list[Subscription] = []
        for s in data or []:
            meters = [
                GasMeter(
                    id=m["id"],
                    name=m.get("name") or m.get("reference") or m["id"],
                    reference=str(m.get("reference") or ""),
                    connected=bool(m.get("connected")),
                    city=(m.get("address") or {}).get("city"),
                )
                for m in (s.get("gasMeters") or [])
            ]
            subs.append(
                Subscription(
                    id=s["id"],
                    reference=str(s.get("reference") or ""),
                    from_date=s.get("fromDate"),
                    meters=meters,
                )
            )
        return subs

    # ---- Consommation ----------------------------------------------------- #
    @staticmethod
    def _day_bounds(d: datetime) -> tuple[str, str]:
        start = datetime(d.year, d.month, d.day, 0, 0, tzinfo=PARIS)
        end = datetime(d.year, d.month, d.day, 23, 59, 59, 999000, tzinfo=PARIS)
        return start.isoformat(timespec="milliseconds"), end.isoformat(
            timespec="milliseconds"
        )

    @staticmethod
    def _month_chunks(dfrom: datetime, dto: datetime):
        """Découpe la plage en tranches mensuelles -> granularité DAILY garantie."""
        cur = datetime(dfrom.year, dfrom.month, dfrom.day)
        while cur <= dto:
            nxt = (
                datetime(cur.year + 1, 1, 1)
                if cur.month == 12
                else datetime(cur.year, cur.month + 1, 1)
            )
            yield cur, min(dto, nxt - timedelta(days=1))
            cur = nxt

    async def async_get_consumption(
        self,
        subscription_id: str,
        pce_id: str,
        dfrom: datetime,
        dto: datetime,
        smoothing: bool = False,
    ) -> list[Reading]:
        """Consommation jour par jour entre deux dates (découpe par mois pour
        forcer la granularité journalière)."""
        out: dict[str, Reading] = {}
        for a, b in self._month_chunks(dfrom, dto):
            f, _ = self._day_bounds(a)
            _, t = self._day_bounds(b)
            path = (
                f"/api/subscription/{subscription_id}/pce/{pce_id}/consumptionData"
                f"?fromDate={quote(f)}&toDate={quote(t)}"
                f"&dataSmoothing={'true' if smoothing else 'false'}"
            )
            data = await self._get(path)
            for c in (data or {}).get("consumptions", []):
                if not c.get("startDate"):
                    continue
                out[c["startDate"]] = Reading(
                    date=c["startDate"],
                    volume_m3=c.get("consumptionM3"),
                    energy_kwh=c.get("consumption"),
                    start_index=c.get("startIndex"),
                    end_index=c.get("endIndex"),
                    generated=bool(c.get("generated")),
                )
        return [out[k] for k in sorted(out)]

    async def async_get_yearly(
        self, subscription_id: str, pce_id: str, year: int
    ) -> Reading | None:
        """Agrégat annuel (champ `yearlyConsumption`), précis (décimales)."""
        f = datetime(year, 1, 1, tzinfo=PARIS).isoformat(timespec="milliseconds")
        t = datetime(year, 1, 15, 23, 59, 59, tzinfo=PARIS).isoformat(
            timespec="milliseconds"
        )
        path = (
            f"/api/subscription/{subscription_id}/pce/{pce_id}/consumptionData"
            f"?fromDate={quote(f)}&toDate={quote(t)}&dataSmoothing=false"
        )
        y = (await self._get(path) or {}).get("yearlyConsumption")
        if not y:
            return None
        return Reading(
            date=y.get("startDate"),
            volume_m3=y.get("consumptionM3"),
            energy_kwh=y.get("consumption"),
            start_index=y.get("startIndex"),
            end_index=y.get("endIndex"),
            generated=bool(y.get("generated")),
        )

    # ---- Prix / abonnement ------------------------------------------------ #
    async def async_get_prices(
        self, subscription_id: str, pce_id: str
    ) -> dict[str, float]:
        """Historique MENSUEL du prix €/kWh TTC : { 'YYYY-MM': prix }."""
        data = await self._get(
            f"/api/subscription/{subscription_id}/pce/{pce_id}/marker-price"
        )
        prices: dict[str, float] = {}
        for r in data or []:
            if r.get("startDate") and r.get("kwhPriceTTC") is not None:
                prices[r["startDate"][:7]] = float(r["kwhPriceTTC"])
        return prices

    async def async_get_tariff(
        self, subscription_id: str, pce_id: str
    ) -> TariffInfo:
        """Prix kWh courant + abonnement annuel (endpoint /infos)."""
        data = await self._get(
            f"/api/subscription/{subscription_id}/pce/{pce_id}/infos"
        )
        return TariffInfo(
            annual_subscription_ttc=(data or {}).get("currentAnnualSubscriptionPriceTTC"),
            current_kwh_price_ttc=(data or {}).get("currentKwhPriceTTC"),
        )
