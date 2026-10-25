"""Bring existing sensors' enabled state in line with the TCD layout."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .registers import DEFAULT_ENABLED_KEYS, SENSOR_DESCRIPTIONS
from .tcd import place_descriptions

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .const import MeterInfo


def sync_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    meters: list[MeterInfo],
    layout: dict[str, Any],
) -> None:
    """Apply the layout's defaults to sensors that already exist.

    A registry entry keeps its enabled state, so new defaults would otherwise only
    reach brand-new sensors. TCD sensors and the default meter-wide sensors follow
    the layout; a sensor the user disabled themselves is never switched back on.
    """
    registry = er.async_get(hass)
    for meter in meters:
        if meter.model_family == "em24" or meter.unique_key not in layout:
            continue
        placements = place_descriptions(SENSOR_DESCRIPTIONS, layout[meter.unique_key])
        for key, placement in placements.items():
            if not key.startswith("tcd") and key not in DEFAULT_ENABLED_KEYS:
                continue
            entity_id = registry.async_get_entity_id(
                "sensor", DOMAIN, f"{meter.unique_key}_{key}"
            )
            existing = registry.async_get(entity_id) if entity_id else None
            if existing is None or existing.config_entry_id != entry.entry_id:
                continue
            wanted = placement.description.entity_registry_enabled_default
            if wanted and existing.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
                registry.async_update_entity(entity_id, disabled_by=None)
            elif not wanted and not existing.disabled:
                registry.async_update_entity(
                    entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
                )
