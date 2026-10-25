"""Bring existing sensors' enabled state in line with the TCD layout."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import DOMAIN
from .registers import DEFAULT_ENABLED_KEYS, SENSOR_DESCRIPTIONS
from .tcd import board_name, place_descriptions

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .const import MeterInfo


def line_entity_id(
    board: str | None,
    meter: MeterInfo,
    meta: dict[str, str | None],
) -> str:
    """Return sensor.<board>_<short name or name>_<w|a|v|kwh>[_l1]."""
    return "sensor." + slugify(f"{board or meter.device_name}_{meta['object_id']}")


def sync_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    meters: list[MeterInfo],
    layout: dict[str, Any],
    old_layout: dict[str, Any] | None = None,
) -> None:
    """Apply the layout's defaults to sensors that already exist.

    A registry entry keeps its enabled state, so new defaults would otherwise only
    reach brand-new sensors. TCD sensors and the default meter-wide sensors follow
    the layout; a sensor the user disabled themselves is never switched back on.

    With old_layout (a reconfigure), a line sensor whose entity ID is still the one
    the previous layout produced is renamed to the one the new layout produces, if
    that ID is free. An ID the user changed by hand is left alone.
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
            if placement.meta and old_layout is not None:
                _rename_if_unchanged(
                    registry, meter, key, existing, placement, layout, old_layout
                )
            wanted = placement.description.entity_registry_enabled_default
            if wanted and existing.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
                registry.async_update_entity(entity_id, disabled_by=None)
            elif not wanted and not existing.disabled:
                registry.async_update_entity(
                    entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
                )


def _rename_if_unchanged(
    registry: er.EntityRegistry,
    meter: MeterInfo,
    key: str,
    existing: er.RegistryEntry,
    placement: Any,
    layout: dict[str, Any],
    old_layout: dict[str, Any],
) -> None:
    old = place_descriptions(SENSOR_DESCRIPTIONS, old_layout.get(meter.unique_key))[key]
    if not old.meta:
        return
    previous = line_entity_id(
        board_name(old_layout.get(meter.unique_key)), meter, old.meta
    )
    wanted = line_entity_id(
        board_name(layout.get(meter.unique_key)), meter, placement.meta
    )
    if (
        existing.entity_id == previous
        and wanted != previous
        and registry.async_get(wanted) is None
    ):
        registry.async_update_entity(existing.entity_id, new_entity_id=wanted)
