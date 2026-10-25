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
_METRIC_NAMES = {
    "W": "Power",
    "kWh": "Energy",
    "A": "Current",
    "VA": "Apparent power",
    "VAR": "Reactive power",
    "kvarh": "Reactive energy",
    "PF": "Power factor",
}


def channel_label(channel: str) -> str:
    """Return the label printed on the meter, e.g. TCDA1."""
    return f"TCD{channel.upper()}"


@dataclass(frozen=True, slots=True)
class Placement:
    """One sensor after the layout is applied."""

    description: RegisterSensorDescription
    device_id: str | None = None


def _metric(description_name: str, channel: str) -> str:
    base = description_name.removeprefix(f"{channel_label(channel)} ")
    base = _NAME_TAIL.sub("", base)
    return _METRIC_NAMES.get(base, base)


def place_descriptions(
    descriptions: tuple[RegisterSensorDescription, ...],
    layout: dict[str, Any] | None,
) -> dict[str, Placement]:
    """Return every sensor of one meter by key, adjusted for its TCD layout.

    layout maps a channel ("a1", "a2") to {"mode": ..., "lines": [{"name": str | None,
    "short_name": str | None, "device_id": str | None}, ...]}. A channel that is
    missing from the layout (or a meter with no layout at all) keeps the stock names
    and defaults.
    """
    layout = layout or {}
    placed: dict[str, Placement] = {}
    for description in descriptions:
        match = _KEY.fullmatch(description.key)
        config = layout.get(match.group(1)) if match else None
        if match is None or not config:
            placed[description.key] = Placement(description)
            continue
        placed[description.key] = _place_tcd_sensor(
            description, match.group(1), match.group(2), config
        )
    return placed


def _place_tcd_sensor(
    description: RegisterSensorDescription,
    channel: str,
    field: str,
    config: dict[str, Any],
) -> Placement:
    mode = config.get("mode", MODE_UNUSED)
    lines = config.get("lines") or []
    phase = _PHASE.search(field)

    if mode == MODE_THREE_PHASE and lines and lines[0].get("name"):
        line = lines[0]
        enabled = field in ("w_total", "kwh_total")
        suffix = f" L{phase.group(1)}" if phase else ""
    elif mode == MODE_SINGLE_PHASE and phase and int(phase.group(1)) <= len(lines):
        line = lines[int(phase.group(1)) - 1]
        enabled = field in (f"w_l{phase.group(1)}", f"kwh_l{phase.group(1)}")
        suffix = ""
        if not line.get("name"):
            return Placement(
                replace(description, entity_registry_enabled_default=False)
            )
    else:
        # An unused channel, or a total/demand value spanning three separate lines:
        # keep the stock name on the meter's own device, off by default.
        return Placement(replace(description, entity_registry_enabled_default=False))

    metric = _metric(description.name, channel) + suffix
    # A short name (R1, W1, ...) leads the entity name. Without one, a linked device
    # already supplies the prefix (has_entity_name) and a bare name has to carry it.
    short = line.get("short_name")
    if short:
        name = f"{short} {metric}"
    else:
        name = metric if line.get("device_id") else f"{line['name']} {metric}"
    return Placement(
        replace(description, name=name, entity_registry_enabled_default=enabled),
        line.get("device_id"),
    )
