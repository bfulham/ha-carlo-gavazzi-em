"""Bring existing sensors' enabled state in line with the TCD layout."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import DOMAIN
from .registers import DEFAULT_ENABLED_KEYS, SENSOR_DESCRIPTIONS
from .tcd import board_name, legacy_entity_name, place_descriptions

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
    """Apply the layout's defaults and entity IDs to sensors that already exist.

    A registry entry keeps its enabled state, so new defaults would otherwise only
    reach brand-new sensors. TCD sensors and the default meter-wide sensors follow
    the layout; a sensor the user disabled themselves is never switched back on.

    A line sensor is also renamed to the entity ID the layout produces when its
    current ID is one the integration generated: the ID the previous layout gave it
    (old_layout), or the one 1.2.0 gave it. An ID the user changed is left alone, and
    so is one whose replacement is already taken.
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
            if placement.meta:
                entity_id = _rename_if_generated(
                    hass, registry, meter, existing, placement, layout, old_layout
                )
            wanted = placement.description.entity_registry_enabled_default
            if wanted and existing.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
                registry.async_update_entity(entity_id, disabled_by=None)
            elif not wanted and not existing.disabled:
                registry.async_update_entity(
                    entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
                )


def _base(entity_id: str) -> str:
    """Strip the _2, _3 suffix Home Assistant adds to a clashing entity ID."""
    return re.sub(r"_\d+$", "", entity_id)


def _rename_if_generated(
    hass: HomeAssistant,
    registry: er.EntityRegistry,
    meter: MeterInfo,
    existing: er.RegistryEntry,
    placement: Any,
    layout: dict[str, Any],
    old_layout: dict[str, Any] | None,
) -> str:
    """Rename the sensor if its ID was generated; return its (new) entity ID."""
    key = placement.description.key
    wanted = line_entity_id(
        board_name(layout.get(meter.unique_key)), meter, placement.meta
    )
    if existing.entity_id == wanted:
        return existing.entity_id

    generated = set()
    if old_layout is not None:
        old = place_descriptions(SENSOR_DESCRIPTIONS, old_layout.get(meter.unique_key))
        if old[key].meta:
            generated.add(
                line_entity_id(
                    board_name(old_layout.get(meter.unique_key)), meter, old[key].meta
                )
            )
    stock = next(item for item in SENSOR_DESCRIPTIONS if item.key == key)
    legacy = legacy_entity_name(stock, (old_layout or layout).get(meter.unique_key))
    if legacy is not None:
        name, device_id = legacy
        device = dr.async_get(hass).async_get(device_id) if device_id else None
        device_name = (
            (device.name_by_user or device.name) if device else meter.device_name
        )
        generated.add("sensor." + slugify(f"{device_name} {name}"))

    if _base(existing.entity_id) in {_base(item) for item in generated} and (
        registry.async_get(wanted) is None
    ):
        registry.async_update_entity(existing.entity_id, new_entity_id=wanted)
        return wanted
    return existing.entity_id
