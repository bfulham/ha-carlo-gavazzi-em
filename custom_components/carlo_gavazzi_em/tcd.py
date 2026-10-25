"""How each TCD channel of an EM270/EM280 is wired, and what that does to its sensors.

Each TCD (TCDA1, TCDA2) measures either one three-phase load or three separate
single-phase lines. The config flow records which, plus a name or a linked Home
Assistant device for every line. This module turns that layout into the sensor
descriptions (name, enabled by default) and the device each sensor belongs to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .registers import RegisterSensorDescription

TCD_CHANNELS: tuple[str, ...] = ("a1", "a2")

MODE_UNUSED = "unused"
MODE_THREE_PHASE = "three_phase"
MODE_SINGLE_PHASE = "single_phase"
TCD_MODES: tuple[str, ...] = (MODE_UNUSED, MODE_THREE_PHASE, MODE_SINGLE_PHASE)

LINES_PER_MODE = {MODE_THREE_PHASE: 1, MODE_SINGLE_PHASE: 3}

_KEY = re.compile(r"tcd(a[12])_(.+)")
_PHASE = re.compile(r"_l([123])$")
_NAME_TAIL = re.compile(r" (Total|L[123])$")


def channel_label(channel: str) -> str:
    """Return the label printed on the meter, e.g. TCDA1."""
    return f"TCD{channel.upper()}"


BOARD = "board"

# Sensors switched on for a line: power and energy only. Current and voltage exist
# for every line but are off until enabled. A 3-phase load uses the totals.
_SINGLE_PHASE_FIELDS = ("w_l{n}", "kwh_l{n}")
_THREE_PHASE_FIELDS = ("w_total", "kwh_total")


@dataclass(frozen=True, slots=True)
class Placement:
    """One sensor after the layout is applied."""

    description: RegisterSensorDescription
    device_id: str | None = None
    # Set for sensors that belong to a TCD line: line_name, short_name, tcd, phase,
    # board and object_id (the part of the entity id after the board and short name).
    meta: dict[str, str | None] | None = None


def board_name(meter_layout: dict[str, Any] | None) -> str | None:
    """Return the distribution board name stored for a meter, if any."""
    return ((meter_layout or {}).get(BOARD) or {}).get("name")


def _metric(description_name: str, channel: str) -> str:
    base = description_name.removeprefix(f"{channel_label(channel)} ")
    return _NAME_TAIL.sub("", base)


def place_descriptions(
    descriptions: tuple[RegisterSensorDescription, ...],
    layout: dict[str, Any] | None,
) -> dict[str, Placement]:
    """Return every sensor of one meter by key, adjusted for its TCD layout.

    layout is {"board": {...}, "a1": {...}, "a2": {...}}; a channel maps to
    {"mode": ..., "lines": [{"name": str | None, "short_name": str | None,
    "device_id": str | None}, ...]}. A meter with no layout keeps the stock names
    and defaults. Once at least one of its TCDs is wired, the meter-wide totals are
    switched off by default: they only add unrelated lines together.
    """
    layout = layout or {}
    wired = any(
        (layout.get(channel) or {}).get("mode", MODE_UNUSED) != MODE_UNUSED
        for channel in TCD_CHANNELS
    )
    placed: dict[str, Placement] = {}
    for description in descriptions:
        match = _KEY.fullmatch(description.key)
        config = layout.get(match.group(1)) if match else None
        if match is None:
            if wired:
                description = replace(
                    description, entity_registry_enabled_default=False
                )
            placed[description.key] = Placement(description)
        elif not config:
            placed[description.key] = Placement(description)
        else:
            placed[description.key] = _place_tcd_sensor(
                description,
                match.group(1),
                match.group(2),
                config,
                board_name(layout),
            )
    return placed


def _place_tcd_sensor(
    description: RegisterSensorDescription,
    channel: str,
    field: str,
    config: dict[str, Any],
    board: str | None,
) -> Placement:
    mode = config.get("mode", MODE_UNUSED)
    lines = config.get("lines") or []
    phase = _PHASE.search(field)
    off = Placement(replace(description, entity_registry_enabled_default=False))

    if mode == MODE_THREE_PHASE and lines:
        line = lines[0]
        wanted = field in _THREE_PHASE_FIELDS
    elif mode == MODE_SINGLE_PHASE and phase and int(phase.group(1)) <= len(lines):
        line = lines[int(phase.group(1)) - 1]
        wanted = field in [f.format(n=phase.group(1)) for f in _SINGLE_PHASE_FIELDS]
    else:
        # An unused channel, or a total/demand value spanning three separate lines:
        # keep the stock name on the meter's own device, off by default.
        return off

    long_name, short_name = line.get("name"), line.get("short_name")
    label = long_name or short_name
    if not label:
        return off

    metric = _metric(description.name, channel)
    tag = f" L{phase.group(1)}" if phase and mode == MODE_THREE_PHASE else ""
    # "<long name> A"; the short name only labels a line that has no long name. The
    # board is only part of the entity ID, never of the name.
    name = f"{label} {metric}{tag}"
    return Placement(
        replace(description, name=name, entity_registry_enabled_default=wanted),
        line.get("device_id"),
        {
            "line_name": long_name,
            "short_name": short_name,
            "tcd": channel_label(channel),
            "phase": f"L{phase.group(1)}" if phase else None,
            "board": board,
            "object_id": (
                f"{short_name or long_name}_{metric}"
                + (f"_l{phase.group(1)}" if tag else "")
            ),
        },
    )


_LEGACY_METRICS = {
    "W": "Power",
    "kWh": "Energy",
    "A": "Current",
    "VA": "Apparent power",
    "VAR": "Reactive power",
    "kvarh": "Reactive energy",
    "PF": "Power factor",
}


def legacy_entity_name(
    description: RegisterSensorDescription,
    meter_layout: dict[str, Any] | None,
) -> tuple[str, str | None] | None:
    """Return (entity name, linked device id) as version 1.2.0 named a line sensor.

    1.2.0 did not set entity IDs, so Home Assistant built them from the device name
    plus this entity name. Returns None for sensors 1.2.0 did not rename.
    """
    match = _KEY.fullmatch(description.key)
    config = (meter_layout or {}).get(match.group(1)) if match else None
    if match is None or not config:
        return None
    channel, field = match.groups()
    lines = config.get("lines") or []
    phase = _PHASE.search(field)
    mode = config.get("mode")
    if mode == MODE_THREE_PHASE and lines and lines[0].get("name"):
        line, tag = lines[0], f" L{phase.group(1)}" if phase else ""
    elif mode == MODE_SINGLE_PHASE and phase and int(phase.group(1)) <= len(lines):
        line, tag = lines[int(phase.group(1)) - 1], ""
        if not line.get("name"):
            return None
    else:
        return None
    base = _NAME_TAIL.sub(
        "", description.name.removeprefix(f"{channel_label(channel)} ")
    )
    metric = _LEGACY_METRICS.get(base, base) + tag
    if line.get("short_name"):
        name = f"{line['short_name']} {metric}"
    elif line.get("device_id"):
        name = metric
    else:
        name = f"{line['name']} {metric}"
    return name, line.get("device_id")
