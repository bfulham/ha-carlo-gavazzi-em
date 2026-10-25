"""Data update coordinator for Carlo Gavazzi EM."""

from __future__ import annotations

import logging
import math
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CarloGavazziAPI, blocks_for
from .const import (
    CONF_DELAY_BETWEEN_REQUESTS_MS,
    CONF_TCD_LAYOUT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_DELAY_BETWEEN_REQUESTS_MS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_UPDATE_INTERVAL,
    MeterInfo,
)
from .modbus import ModbusGatewayError
from .registers import SENSOR_DESCRIPTIONS, SENSOR_DESCRIPTIONS_EM24
from .tcd import Placement, board_name, place_descriptions

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
        layout = entry.data.get(CONF_TCD_LAYOUT, {})
        # Sensors per meter, named and defaulted according to how its TCDs are wired.
        self.boards: dict[str, str | None] = {
            meter.unique_key: board_name(layout.get(meter.unique_key))
            for meter in meters
        }
        self.last_poll_seconds: float | None = None
        self.placements: dict[str, dict[str, Placement]] = {
            meter.unique_key: place_descriptions(
                SENSOR_DESCRIPTIONS_EM24
                if meter.model_family == "em24"
                else SENSOR_DESCRIPTIONS,
                layout.get(meter.unique_key),
            )
            for meter in meters
        }
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

    def _is_enabled(self, meter: MeterInfo, key: str) -> bool:
        registry = er.async_get(self.hass)
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{meter.unique_key}_{key}"
        )
        entry = registry.async_get(entity_id) if entity_id else None
        if entry is None:
            return self.placements[meter.unique_key][
                key
            ].description.entity_registry_enabled_default
        return not entry.disabled

    def enabled_keys(self) -> dict[str, frozenset[str]]:
        """Sensor keys whose entity is enabled, per meter; disabled ones are not polled.

        An entity that is not in the registry yet (first setup) counts as enabled
        when it is enabled by default.
        """
        enabled: dict[str, frozenset[str]] = {}
        for meter in self.meters:
            keys = {
                key
                for key in self.placements[meter.unique_key]
                if self._is_enabled(meter, key)
            }
            # An alias (a TCD line's V) is served by the register it points at.
            enabled[meter.unique_key] = frozenset(
                self.placements[meter.unique_key][key].description.source_key or key
                for key in keys
            )
        return enabled

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        started = time.monotonic()
        try:
            data = await self.api.async_fetch_all_meter_data(
                self.meters, self.enabled_keys()
            )
            self.last_poll_seconds = time.monotonic() - started
            return data
        except ModbusGatewayError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Unexpected polling error: {err}") from err

    def poll_estimate(self) -> dict[str, float | int]:
        """Describe the polling load and the fastest interval that keeps up.

        The RS-485 bus is shared and read one request at a time, so a poll takes
        roughly the sum of its reads. Each read is modelled as its frame time at
        9600 baud (request 8 bytes + reply 5 + 2 per register, 11 bits per byte)
        plus about 60 ms for the meter's turnaround, the gateway and the network.
        Once a real poll has been timed, that measurement is used instead.
        """
        enabled = self.enabled_keys()
        reads = 0
        modelled = 0.0
        pause = (
            float(
                self.config_entry.options.get(
                    CONF_DELAY_BETWEEN_REQUESTS_MS,
                    self.config_entry.data.get(
                        CONF_DELAY_BETWEEN_REQUESTS_MS,
                        DEFAULT_DELAY_BETWEEN_REQUESTS_MS,
                    ),
                )
            )
            / 1000
        )
        for meter in self.meters:
            for block in blocks_for(meter.model_family, enabled[meter.unique_key]):
                reads += 1
                modelled += (13 + 2 * block.count) * 11 / 9600 + 0.06 + pause
        seconds = self.last_poll_seconds or modelled
        return {
            "entities": sum(
                1
                for meter in self.meters
                for key in self.placements[meter.unique_key]
                if self._is_enabled(meter, key)
            ),
            "reads": reads,
            "seconds": round(seconds, 2),
            "recommended": max(MIN_UPDATE_INTERVAL, math.ceil(seconds * 1.25)),
        }
