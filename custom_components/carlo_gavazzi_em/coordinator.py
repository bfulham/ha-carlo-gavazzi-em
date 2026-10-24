"""Data update coordinator for Carlo Gavazzi EM."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CarloGavazziAPI
from .const import (
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MeterInfo,
)
from .modbus import ModbusGatewayError
from .registers import SENSOR_DESCRIPTIONS, SENSOR_DESCRIPTIONS_EM24

_LOGGER = logging.getLogger(__name__)


class CarloGavazziCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinate polling for all meters behind a gateway."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: CarloGavazziAPI,
        meters: list[MeterInfo],
    ) -> None:
        self.api = api
        self.meters = meters
        update_interval = entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=int(update_interval)),
            always_update=False,
        )

    def _enabled_keys(self) -> dict[str, frozenset[str]]:
        """Sensor keys whose entity is enabled, per meter; disabled ones are not polled.

        An entity that is not in the registry yet (first setup) counts as enabled
        when it is enabled by default.
        """
        registry = er.async_get(self.hass)
        enabled: dict[str, frozenset[str]] = {}
        for meter in self.meters:
            descriptions = (
                SENSOR_DESCRIPTIONS_EM24
                if meter.model_family == "em24"
                else SENSOR_DESCRIPTIONS
            )
            keys = set()
            for description in descriptions:
                entity_id = registry.async_get_entity_id(
                    "sensor", DOMAIN, f"{meter.unique_key}_{description.key}"
                )
                entry = registry.async_get(entity_id) if entity_id else None
                if entry is None:
                    if description.entity_registry_enabled_default:
                        keys.add(description.key)
                elif not entry.disabled:
                    keys.add(description.key)
            enabled[meter.unique_key] = frozenset(keys)
        return enabled

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            return await self.api.async_fetch_all_meter_data(
                self.meters, self._enabled_keys()
            )
        except ModbusGatewayError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Unexpected polling error: {err}") from err
