# Development

## Rules of the project

- **Read-only.** Do not add Modbus writes, resets or programming commands unless there is a clear safety review and an explicit confirmation step for every write.
- Keep `strings.json` and `translations/en.json` identical.
- The integration code targets Python 3.13+ (`pyproject.toml`: `target-version = "py313"`); `contrib/` scripts run on the gateways under Python 2.7 and 3 and are excluded from ruff.

## Set up and check

```bash
python -m pip install -r requirements-dev.txt     # ruff
ruff format --check .                              # formatting (line length 88)
ruff check .                                       # lint: ASYNC, B, E, F, I, UP
python -m compileall -q custom_components/carlo_gavazzi_em scripts
```

`ruff format .` fixes formatting. These are exactly the three steps of the **Lint** workflow.

## What CI runs

| Workflow | Trigger | Does |
|---|---|---|
| **Lint** (`lint.yml`) | push to `main`, pull requests | `ruff format --check`, `ruff check`, `compileall`. |
| **Validate** (`validate.yml`) | push to `main`, pull requests | Home Assistant **hassfest**; **HACS** validation; a **config-flow smoke test** on Home Assistant 2026.2.3 (Python 3.13) and 2026.6.1 (Python 3.14). |
| **Release** (`release.yml`) | a pushed tag `v*.*.*` | Zips `custom_components/carlo_gavazzi_em` to `carlo_gavazzi_em.zip`, writes `SHA256SUMS.txt`, and creates a GitHub release with generated notes. |

`scripts/smoke_import.py` is the smoke test: it starts the integration through Home Assistant's real flow manager, walks the first forms and checks imports, schemas and helper functions. It needs `homeassistant` and `pymodbus` installed, so run it in a throw-away virtual environment:

```bash
python -m venv .venv && . .venv/bin/activate
pip install "homeassistant==2026.2.3" "pymodbus==3.11.2"
python scripts/smoke_import.py
```

## Testing without a meter

The pure logic (`tcd.py`, the read-block builder, the decoders) can be exercised without Home Assistant by stubbing the few Home Assistant modules it imports. The entity-registry behaviour (`layout_sync.py`, migrations) and the real sensor platform setup need a Home Assistant test harness; they were only checked with stand-in objects while this was written, so **test changes to those parts in a real Home Assistant** (or add `pytest-homeassistant-custom-component` tests). A mistake in the sensor platform once left every entity unavailable (1.3.0), because nothing imported `sensor.py`.

The gateway proxy can be tested against real hardware with `--probe` and `--scan`, or from any PC with `contrib/scan_slaves.py`.

## Adding or changing a sensor

1. Add or edit its `RegisterSensorDescription` in `registers.py` (key, `name`, `address`, `words`, `scale`, `signed`, unit, device/state class, `entity_category` for diagnostics). Keep the EM270/EM280 and EM24 tables separate; the register addresses differ.
2. If it should be on by default for an unwired meter, add its key to `DEFAULT_ENABLED_KEYS`. Otherwise do nothing: it is created off and not polled.
3. If the raw value is a code with names, add the mapping and a branch in `map_option`.
4. If it is a TCD field (`tcdaN_...`) check the naming/defaults in `tcd.py` still produce what you expect (`_THREE_PHASE_FIELDS`, `_SINGLE_PHASE_FIELDS`).
5. Update [sensors.md](sensors.md) and the changelog.

Changing which sensors are on by default for existing installs needs a **config entry version bump and a migration** in `__init__.py` (plus the `VERSION` in `config_flow.py`), because existing registry entries keep their enabled state.

## Releasing

1. Update `CHANGELOG.md` and the `version` in `custom_components/carlo_gavazzi_em/manifest.json` (they must match the tag).
2. Make sure Lint and Validate pass on `main`.
3. Tag and push:

   ```bash
   git tag -a vX.Y.Z -m "Carlo Gavazzi EM vX.Y.Z"
   git push origin vX.Y.Z
   ```

4. The Release workflow publishes the ZIP and checksum. HACS users update to the new tag.

## Repository map

```text
custom_components/carlo_gavazzi_em/   the integration
contrib/                              gateway-side scripts (proxy, installer, deploy, scan)
scripts/smoke_import.py               CI smoke test
docs/                                 this documentation
.github/                              workflows and issue templates
hacs.json, pyproject.toml, requirements-dev.txt
```
