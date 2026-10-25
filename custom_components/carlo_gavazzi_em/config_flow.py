"""Config flow for Carlo Gavazzi EM270/EM280/EM24."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    DeviceSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_DELAY_BETWEEN_REQUESTS_MS,
    CONF_DETECTED_TRANSPORT_MODE,
    CONF_DISCOVERY_PASSES,
    CONF_HOST,
    CONF_METERS,
    CONF_PORT,
    CONF_REQUEST_RETRIES,
    CONF_SCAN_END,
    CONF_SCAN_START,
    CONF_TCD_LAYOUT,
    CONF_TIMEOUT,
    CONF_TRANSPORT_MODE,
    CONF_UPDATE_INTERVAL,
    CT_PRIMARY_2_ADDRESS,
    CT_PRIMARY_ADDRESS,
    DEFAULT_DELAY_BETWEEN_REQUESTS_MS,
    DEFAULT_DISCOVERY_PASSES,
    DEFAULT_PORT,
    DEFAULT_REQUEST_RETRIES,
    DEFAULT_SCAN_END,
    DEFAULT_SCAN_START,
    DEFAULT_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    GATEWAY_TITLE_PREFIX,
    MIN_UPDATE_INTERVAL,
    MeterInfo,
    TransportMode,
)
from .tcd import (
    LINES_PER_MODE,
    MODE_THREE_PHASE,
    MODE_UNUSED,
    TCD_CHANNELS,
    TCD_MODES,
    channel_label,
    place_descriptions,
)

if TYPE_CHECKING:
    from .api import CarloGavazziAPI

_LOGGER = logging.getLogger(__name__)

CONF_ADVANCED_SETTINGS = "advanced_settings"
CONF_LIMIT_SCAN_RANGE = "limit_scan_range"


def _number(
    minimum: float,
    maximum: float,
    *,
    step: float = 1,
    unit: str | None = None,
) -> NumberSelector:
    """Create a box-style number selector."""
    config = NumberSelectorConfig(
        min=minimum,
        max=maximum,
        step=step,
        mode=NumberSelectorMode.BOX,
    )
    if unit is not None:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


def _normalize_host(host: str) -> str:
    """Normalize a host for storage and duplicate detection."""
    return host.strip().lower()


def _user_schema(current: dict[str, Any]) -> vol.Schema:
    """Build the first config-flow form."""
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=current.get(CONF_HOST, "")): str,
            vol.Optional(
                CONF_PORT,
                default=current.get(CONF_PORT, DEFAULT_PORT),
            ): _number(1, 65535),
            vol.Optional(
                CONF_UPDATE_INTERVAL,
                default=current.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): _number(MIN_UPDATE_INTERVAL, 3600, unit="s"),
            vol.Optional(CONF_ADVANCED_SETTINGS, default=False): bool,
            vol.Optional(
                CONF_LIMIT_SCAN_RANGE,
                default=(
                    current.get(CONF_SCAN_START, DEFAULT_SCAN_START)
                    != DEFAULT_SCAN_START
                    or current.get(CONF_SCAN_END, DEFAULT_SCAN_END) != DEFAULT_SCAN_END
                ),
            ): bool,
        }
    )


def _advanced_schema(current: dict[str, Any]) -> vol.Schema:
    """Build advanced transport settings."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_TIMEOUT,
                default=current.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
            ): _number(0.1, 10, step=0.05, unit="s"),
            vol.Optional(
                CONF_REQUEST_RETRIES,
                default=current.get(CONF_REQUEST_RETRIES, DEFAULT_REQUEST_RETRIES),
            ): _number(0, 5),
            vol.Optional(
                CONF_DELAY_BETWEEN_REQUESTS_MS,
                default=current.get(
                    CONF_DELAY_BETWEEN_REQUESTS_MS,
                    DEFAULT_DELAY_BETWEEN_REQUESTS_MS,
                ),
            ): _number(0, 500, unit="ms"),
            vol.Optional(
                CONF_TRANSPORT_MODE,
                default=current.get(CONF_TRANSPORT_MODE, TransportMode.AUTO.value),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[mode.value for mode in TransportMode],
                    translation_key="transport_mode",
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _scan_range_schema(current: dict[str, Any]) -> vol.Schema:
    """Build the optional restricted address range form."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_SCAN_START,
                default=current.get(CONF_SCAN_START, DEFAULT_SCAN_START),
            ): _number(1, 247),
            vol.Optional(
                CONF_SCAN_END,
                default=current.get(CONF_SCAN_END, DEFAULT_SCAN_END),
            ): _number(1, 247),
        }
    )


class CarloGavazziConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure one RTU-to-TCP gateway and discover its meters."""

    VERSION = 3

    def __init__(self) -> None:
        """Initialize the flow state."""
        self._input: dict[str, Any] = {}
        self._api: CarloGavazziAPI | None = None
        self._discovery_task: asyncio.Task[list[MeterInfo]] | None = None
        self._progress_placeholders = {
            "pass": "1",
            "passes": str(DEFAULT_DISCOVERY_PASSES),
            "address": "1",
            "transport": "Modbus TCP",
            "found": "0",
        }
        self._last_notified_found = -1
        self._meters: list[MeterInfo] = []
        self._detected_transport = TransportMode.AUTO.value
        self._tcd_present: dict[str, dict[str, bool]] = {}
        self._layout: dict[str, dict[str, Any]] = {}
        self._tcd_queue: list[tuple[MeterInfo, str]] = []

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Collect gateway and basic polling settings."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=_user_schema(self._current_values()),
            )

        host = _normalize_host(user_input[CONF_HOST])
        port = int(user_input[CONF_PORT])
        await self.async_set_unique_id(f"{host}:{port}")

        if self.source == SOURCE_RECONFIGURE:
            existing = self.hass.config_entries.async_entry_for_domain_unique_id(
                DOMAIN,
                self.unique_id,
            )
            if (
                existing is not None
                and existing.entry_id != self._get_reconfigure_entry().entry_id
            ):
                return self.async_abort(reason="already_configured")
        else:
            self._abort_if_unique_id_configured()

        self._input.update(user_input)
        self._input[CONF_HOST] = host
        self._input[CONF_PORT] = port

        if not user_input[CONF_LIMIT_SCAN_RANGE]:
            self._input[CONF_SCAN_START] = DEFAULT_SCAN_START
            self._input[CONF_SCAN_END] = DEFAULT_SCAN_END

        if user_input[CONF_ADVANCED_SETTINGS]:
            return await self.async_step_advanced()
        if user_input[CONF_LIMIT_SCAN_RANGE]:
            return await self.async_step_scan_range()
        return await self.async_step_discover()

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Change gateway settings and rescan the RTU bus."""
        if not self._input:
            entry = self._get_reconfigure_entry()
            self._input = {**entry.data, **entry.options}
        return await self.async_step_user(user_input)

    async def async_step_advanced(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Collect transport, timeout, retry, and pacing settings."""
        if user_input is None:
            return self.async_show_form(
                step_id="advanced",
                data_schema=_advanced_schema(self._current_values()),
            )

        self._input.update(user_input)
        if self._input.get(CONF_LIMIT_SCAN_RANGE):
            return await self.async_step_scan_range()
        return await self.async_step_discover()

    async def async_step_scan_range(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Collect an optional restricted Modbus slave-ID range."""
        errors: dict[str, str] = {}
        if user_input is not None:
            start = int(user_input[CONF_SCAN_START])
            end = int(user_input[CONF_SCAN_END])
            if start <= end:
                self._input.update(user_input)
                return await self.async_step_discover()
            errors["base"] = "invalid_range"

        current = {**self._current_values(), **(user_input or {})}
        return self.async_show_form(
            step_id="scan_range",
            data_schema=_scan_range_schema(current),
            errors=errors,
        )

    async def async_step_discover(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show live progress while scanning the RTU bus."""
        del user_input

        if self._discovery_task is None:
            self._discovery_task = self.hass.async_create_task(
                self._async_discover(),
                "carlo_gavazzi_em_discovery",
            )

        if not self._discovery_task.done():
            return self.async_show_progress(
                step_id="discover",
                progress_action="discover_devices",
                progress_task=self._discovery_task,
                description_placeholders=self._progress_placeholders,
            )

        # Home Assistant only allows a progress step to be followed by another
        # progress step or progress_done, so hand over to the summary form via
        # progress_done rather than returning the form directly.
        return self.async_show_progress_done(next_step_id="finish")

    async def _async_discover(self) -> list[MeterInfo]:
        """Create the API lazily and run the discovery scan."""
        from .api import CarloGavazziAPI

        self._api = CarloGavazziAPI(self._build_config())

        async def progress_callback(
            current_pass: int,
            total_passes: int,
            slave_id: int,
            total_addresses: int,
            transport: str,
            found: int,
        ) -> None:
            scan_start = int(self._input.get(CONF_SCAN_START, DEFAULT_SCAN_START))
            completed = (current_pass - 1) * total_addresses + (
                slave_id - scan_start + 1
            )
            total = max(1, total_passes * total_addresses)
            transport_name = (
                "Modbus TCP"
                if transport == TransportMode.SOCKET.value
                else "RTU over TCP"
            )
            self._progress_placeholders.update(
                {
                    "pass": str(current_pass),
                    "passes": str(total_passes),
                    "address": str(slave_id),
                    "transport": transport_name,
                    "found": str(found),
                }
            )
            self.async_update_progress(min(completed / total, 0.99))

            scan_end = int(self._input.get(CONF_SCAN_END, DEFAULT_SCAN_END))
            if (
                slave_id in {scan_start, scan_end}
                or (slave_id - scan_start) % 10 == 0
                or found != self._last_notified_found
            ):
                self._last_notified_found = found
                self.async_notify_flow_changed()

        return await self._api.async_discover_meters(progress_callback)

    async def async_step_finish(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Collect the scan result, then ask how each meter's TCDs are wired."""
        del user_input
        assert self._discovery_task is not None

        try:
            meters = self._discovery_task.result()
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Gateway discovery failed: %s", err)
            if self._api is not None:
                await self._api.async_close()
            self._reset_discovery()
            return self.async_show_form(
                step_id="user",
                data_schema=_user_schema(self._current_values()),
                errors={"base": "cannot_connect"},
            )

        assert self._api is not None
        self._detected_transport = self._api.detected_transport_mode
        self._tcd_present = await self._async_probe_tcds(meters)
        await self._api.async_close()

        if not meters:
            self._reset_discovery()
            return self.async_show_form(
                step_id="user",
                data_schema=_user_schema(self._current_values()),
                errors={"base": "no_devices_found"},
            )

        self._meters = sorted(meters, key=lambda meter: meter.slave_id)
        if not any(meter.model_family != "em24" for meter in self._meters):
            return self._async_finish_entry()
        return await self.async_step_tcd_layout()

    async def _async_probe_tcds(
        self,
        meters: list[MeterInfo],
    ) -> dict[str, dict[str, bool]]:
        """Guess which TCD channels are connected, to pre-fill the next form.

        The EM280 reports "No TCD detected" in its CT primary registers. Other
        models cannot say, so assume TCDA1 is fitted and TCDA2 is not.
        """
        assert self._api is not None
        present: dict[str, dict[str, bool]] = {}
        for meter in meters:
            guess = {"a1": True, "a2": False}
            if meter.model_family == "em280":
                for channel, address in (
                    ("a1", CT_PRIMARY_ADDRESS),
                    ("a2", CT_PRIMARY_2_ADDRESS),
                ):
                    try:
                        registers = await self._api.client.async_read_holding_registers(
                            meter.slave_id, address, 1, attempts=2
                        )
                    except Exception:  # noqa: BLE001
                        registers = None
                    if registers:
                        guess[channel] = registers[0] != 4
            present[meter.unique_key] = guess
        return present

    def _stored_layout(self, meter: MeterInfo, channel: str) -> dict[str, Any]:
        """Return the layout saved for this TCD when reconfiguring, else {}."""
        if self.source != SOURCE_RECONFIGURE:
            return {}
        stored = self._get_reconfigure_entry().data.get(CONF_TCD_LAYOUT, {})
        return stored.get(meter.unique_key, {}).get(channel, {})

    def _tcd_label(self, meter: MeterInfo, channel: str) -> str:
        return f"{meter.device_name} - {channel_label(channel)}"

    async def async_step_tcd_layout(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Ask, for every TCD, whether it measures one 3-phase load or 3 lines."""
        tcd_meters = [meter for meter in self._meters if meter.model_family != "em24"]
        fields = {
            self._tcd_label(meter, channel): (meter, channel)
            for meter in tcd_meters
            for channel in TCD_CHANNELS
        }

        if user_input is not None:
            self._layout = {}
            self._tcd_queue = []
            for label, (meter, channel) in fields.items():
                mode = user_input.get(label, MODE_UNUSED)
                self._layout.setdefault(meter.unique_key, {})[channel] = {
                    "mode": mode,
                    "lines": [],
                }
                if mode != MODE_UNUSED:
                    self._tcd_queue.append((meter, channel))
            return await self.async_step_tcd_names()

        def default_mode(meter: MeterInfo, channel: str) -> str:
            stored = self._stored_layout(meter, channel).get("mode")
            if stored in TCD_MODES:
                return stored
            if self._tcd_present.get(meter.unique_key, {}).get(channel):
                return MODE_THREE_PHASE
            return MODE_UNUSED

        schema = vol.Schema(
            {
                vol.Optional(label, default=default_mode(meter, channel)): (
                    SelectSelector(
                        SelectSelectorConfig(
                            options=list(TCD_MODES),
                            translation_key="tcd_mode",
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                )
                for label, (meter, channel) in fields.items()
            }
        )
        return self.async_show_form(
            step_id="tcd_layout",
            data_schema=schema,
            description_placeholders={"found": str(len(self._meters))},
        )

    async def async_step_tcd_names(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Name each line of the next TCD, or link it to an existing device."""
        if not self._tcd_queue:
            return self._async_finish_entry()
        meter, channel = self._tcd_queue[0]
        mode = self._layout[meter.unique_key][channel]["mode"]
        line_count = LINES_PER_MODE[mode]
        names = ["name"] if line_count == 1 else [f"name_{n}" for n in range(1, 4)]
        devices = (
            ["device"] if line_count == 1 else [f"device_{n}" for n in range(1, 4)]
        )
        errors: dict[str, str] = {}

        if user_input is not None:
            device_registry = dr.async_get(self.hass)
            lines = []
            for name_key, device_key in zip(names, devices, strict=True):
                device = device_registry.async_get(user_input.get(device_key) or "")
                name = (user_input.get(name_key) or "").strip()
                if device is not None:
                    # A linked device names the line, whatever was typed.
                    name = device.name_by_user or device.name or ""
                lines.append(
                    {
                        "name": name or None,
                        "device_id": device.id if device is not None else None,
                    }
                )
            if not any(line["name"] for line in lines):
                errors["base"] = "name_required"
            else:
                self._layout[meter.unique_key][channel]["lines"] = lines
                self._tcd_queue.pop(0)
                return await self.async_step_tcd_names()

        stored = self._stored_layout(meter, channel)
        stored_lines = stored.get("lines", []) if stored.get("mode") == mode else []
        fields: dict[Any, Any] = {}
        for index, (name_key, device_key) in enumerate(
            zip(names, devices, strict=True)
        ):
            line = stored_lines[index] if index < len(stored_lines) else {}
            suggested = user_input or {}
            fields[
                vol.Optional(
                    name_key,
                    description={
                        "suggested_value": suggested.get(name_key, line.get("name"))
                    },
                )
            ] = str
            fields[
                vol.Optional(
                    device_key,
                    description={
                        "suggested_value": suggested.get(
                            device_key, line.get("device_id")
                        )
                    },
                )
            ] = DeviceSelector()
        return self.async_show_form(
            step_id="tcd_names",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders={
                "meter": meter.device_name,
                "tcd": channel_label(channel),
                "mode": "3-phase load" if line_count == 1 else "3 single-phase lines",
            },
        )

    def _async_finish_entry(self) -> ConfigFlowResult:
        """Create the entry, or update it when reconfiguring."""
        data = {
            **self._build_config(),
            CONF_DETECTED_TRANSPORT_MODE: self._detected_transport,
            CONF_METERS: [asdict(meter) for meter in self._meters],
            CONF_TCD_LAYOUT: self._layout,
        }
        title = f"{GATEWAY_TITLE_PREFIX} {data[CONF_HOST]}"

        if self.source == SOURCE_RECONFIGURE:
            self._sync_tcd_entities()
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                data=data,
                options={},
                title=title,
                unique_id=self.unique_id,
            )
        return self.async_create_entry(title=title, data=data)

    def _sync_tcd_entities(self) -> None:
        """Apply the new layout to TCD sensors that already exist.

        A registry entry keeps its enabled state across a reload, so the new
        defaults would otherwise only reach brand-new entities. Sensors the user
        switched off themselves stay off.
        """
        from .registers import SENSOR_DESCRIPTIONS

        registry = er.async_get(self.hass)
        entry = self._get_reconfigure_entry()
        for meter in self._meters:
            if meter.model_family == "em24":
                continue
            placements = place_descriptions(
                SENSOR_DESCRIPTIONS, self._layout.get(meter.unique_key)
            )
            for key, placement in placements.items():
                if not key.startswith("tcd"):
                    continue
                entity_id = registry.async_get_entity_id(
                    "sensor", DOMAIN, f"{meter.unique_key}_{key}"
                )
                existing = registry.async_get(entity_id) if entity_id else None
                if existing is None or existing.config_entry_id != entry.entry_id:
                    continue
                wanted = placement.description.entity_registry_enabled_default
                if (
                    wanted
                    and existing.disabled_by is er.RegistryEntryDisabler.INTEGRATION
                ):
                    registry.async_update_entity(entity_id, disabled_by=None)
                elif not wanted and not existing.disabled:
                    registry.async_update_entity(
                        entity_id,
                        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
                    )

    def _reset_discovery(self) -> None:
        """Clear discovery state so the user can retry within the same flow."""
        self._api = None
        self._discovery_task = None
        self._last_notified_found = -1
        self._progress_placeholders.update(
            {
                "pass": "1",
                "passes": str(DEFAULT_DISCOVERY_PASSES),
                "address": str(self._input.get(CONF_SCAN_START, DEFAULT_SCAN_START)),
                "transport": "Modbus TCP",
                "found": "0",
            }
        )

    def _build_config(self) -> dict[str, Any]:
        """Return normalized configuration values for the API and entry."""
        return {
            CONF_HOST: _normalize_host(self._input[CONF_HOST]),
            CONF_PORT: int(self._input.get(CONF_PORT, DEFAULT_PORT)),
            CONF_UPDATE_INTERVAL: int(
                self._input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            ),
            CONF_TIMEOUT: float(self._input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)),
            CONF_REQUEST_RETRIES: int(
                self._input.get(CONF_REQUEST_RETRIES, DEFAULT_REQUEST_RETRIES)
            ),
            CONF_DELAY_BETWEEN_REQUESTS_MS: int(
                self._input.get(
                    CONF_DELAY_BETWEEN_REQUESTS_MS,
                    DEFAULT_DELAY_BETWEEN_REQUESTS_MS,
                )
            ),
            CONF_DISCOVERY_PASSES: DEFAULT_DISCOVERY_PASSES,
            CONF_TRANSPORT_MODE: str(
                self._input.get(CONF_TRANSPORT_MODE, TransportMode.AUTO.value)
            ),
            CONF_SCAN_START: int(self._input.get(CONF_SCAN_START, DEFAULT_SCAN_START)),
            CONF_SCAN_END: int(self._input.get(CONF_SCAN_END, DEFAULT_SCAN_END)),
        }

    def _current_values(self) -> dict[str, Any]:
        """Return values already entered or stored for reconfiguration."""
        if self._input:
            return self._input
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            return {**entry.data, **entry.options}
        return {}

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> CarloGavazziOptionsFlow:
        """Return the options flow."""
        del config_entry
        return CarloGavazziOptionsFlow()


class CarloGavazziOptionsFlow(OptionsFlowWithReload):
    """Change polling behavior without rescanning the bus."""

    def __init__(self) -> None:
        """Initialize option values."""
        self._input: dict[str, Any] = {}

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Set update interval and optionally show advanced polling options."""
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is None:
            schema = vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=current.get(
                            CONF_UPDATE_INTERVAL,
                            DEFAULT_UPDATE_INTERVAL,
                        ),
                    ): _number(MIN_UPDATE_INTERVAL, 3600, unit="s"),
                    vol.Optional(CONF_ADVANCED_SETTINGS, default=False): bool,
                }
            )
            return self.async_show_form(step_id="init", data_schema=schema)

        self._input.update(user_input)
        if user_input[CONF_ADVANCED_SETTINGS]:
            return await self.async_step_advanced()
        return self._save_options(current)

    async def async_step_advanced(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Set timeout, retry count, and request pacing."""
        current = {
            **self.config_entry.data,
            **self.config_entry.options,
            **self._input,
        }
        if user_input is None:
            schema = vol.Schema(
                {
                    vol.Optional(
                        CONF_TIMEOUT,
                        default=current.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                    ): _number(0.1, 10, step=0.05, unit="s"),
                    vol.Optional(
                        CONF_REQUEST_RETRIES,
                        default=current.get(
                            CONF_REQUEST_RETRIES,
                            DEFAULT_REQUEST_RETRIES,
                        ),
                    ): _number(0, 5),
                    vol.Optional(
                        CONF_DELAY_BETWEEN_REQUESTS_MS,
                        default=current.get(
                            CONF_DELAY_BETWEEN_REQUESTS_MS,
                            DEFAULT_DELAY_BETWEEN_REQUESTS_MS,
                        ),
                    ): _number(0, 500, unit="ms"),
                }
            )
            return self.async_show_form(step_id="advanced", data_schema=schema)

        self._input.update(user_input)
        return self._save_options(current)

    def _save_options(self, current: dict[str, Any]) -> ConfigFlowResult:
        """Save normalized options and trigger the automatic reload."""
        return self.async_create_entry(
            title="",
            data={
                CONF_UPDATE_INTERVAL: int(
                    self._input.get(
                        CONF_UPDATE_INTERVAL,
                        current.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                    )
                ),
                CONF_TIMEOUT: float(
                    self._input.get(
                        CONF_TIMEOUT,
                        current.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                    )
                ),
                CONF_REQUEST_RETRIES: int(
                    self._input.get(
                        CONF_REQUEST_RETRIES,
                        current.get(CONF_REQUEST_RETRIES, DEFAULT_REQUEST_RETRIES),
                    )
                ),
                CONF_DELAY_BETWEEN_REQUESTS_MS: int(
                    self._input.get(
                        CONF_DELAY_BETWEEN_REQUESTS_MS,
                        current.get(
                            CONF_DELAY_BETWEEN_REQUESTS_MS,
                            DEFAULT_DELAY_BETWEEN_REQUESTS_MS,
                        ),
                    )
                ),
            },
        )
