"""Capteurs de l'intégration R-GDS."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_METER_NAME, CONF_PCE_ID, DOMAIN, PARIS
from .coordinator import RgdsCoordinator


@dataclass(frozen=True, kw_only=True)
class RgdsSensorDescription(SensorEntityDescription):
    """Description d'un capteur R-GDS avec sa fonction de valeur."""

    value_fn: Callable[[dict], object]


def _last_reading_date(data: dict) -> datetime | None:
    r = data.get("last_reading")
    if not r or not r.date:
        return None
    y, m, d = map(int, r.date.split("-"))
    return datetime(y, m, d, tzinfo=PARIS)


SENSORS: tuple[RgdsSensorDescription, ...] = (
    RgdsSensorDescription(
        key="current_price",
        name="Prix du kWh",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("current_price"),
    ),
    RgdsSensorDescription(
        key="subscription",
        name="Abonnement annuel",
        native_unit_of_measurement=f"{CURRENCY_EURO}/an",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: getattr(d.get("tariff"), "annual_subscription_ttc", None),
    ),
    RgdsSensorDescription(
        key="meter_index",
        name="Index compteur",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: getattr(d.get("last_reading"), "end_index", None),
    ),
    RgdsSensorDescription(
        key="last_reading_date",
        name="Dernier relevé",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_reading_date,
    ),
    RgdsSensorDescription(
        key="yearly_volume",
        name="Consommation annuelle",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: getattr(d.get("yearly"), "volume_m3", None),
    ),
    RgdsSensorDescription(
        key="yearly_energy",
        name="Énergie annuelle",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: getattr(d.get("yearly"), "energy_kwh", None),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Met en place les capteurs."""
    coordinator: RgdsCoordinator = hass.data[DOMAIN][entry.entry_id]
    pce_id = entry.data[CONF_PCE_ID]
    device = DeviceInfo(
        identifiers={(DOMAIN, pce_id)},
        name=entry.data.get(CONF_METER_NAME) or "R-GDS",
        manufacturer="R-GDS",
        model="Compteur gaz communicant",
    )
    async_add_entities(
        RgdsSensor(coordinator, device, pce_id, desc) for desc in SENSORS
    )


class RgdsSensor(CoordinatorEntity[RgdsCoordinator], SensorEntity):
    """Capteur R-GDS générique."""

    entity_description: RgdsSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RgdsCoordinator,
        device: DeviceInfo,
        pce_id: str,
        description: RgdsSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{pce_id}_{description.key}"
        self._attr_device_info = device

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data or {})
