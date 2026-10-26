# Publishing

Release steps for maintainers are in [docs/development.md](docs/development.md#releasing). In short: update `CHANGELOG.md` and the `manifest.json` version, make sure the **Lint** and **Validate** workflows pass on `main`, then push an annotated `vX.Y.Z` tag; the **Release** workflow attaches `carlo_gavazzi_em.zip` and `SHA256SUMS.txt` to the GitHub release.

## HACS topics

```bash
gh repo edit bfulham/ha-carlo-gavazzi-em --add-topic home-assistant --add-topic hacs --add-topic integration --add-topic modbus --add-topic modbus-tcp --add-topic carlo-gavazzi --add-topic em270 --add-topic em280
```

## Installing a release cleanly in Home Assistant

1. Remove the integration from HACS if present, and delete `/config/custom_components/carlo_gavazzi_em` if it remains.
2. Restart Home Assistant.
3. Add the repository to HACS as a custom **Integration** repository, install the tag, and restart again.
