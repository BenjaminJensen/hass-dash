# Fixtures

Recorded Home Assistant payloads, produced by `tools/capture_snapshot.py` run
against the live instance from outside the container:

- `states.json` — the climate-relevant entities, keyed by entity id
- `forecast_hourly.json` / `forecast_daily.json` — what `weather.get_forecasts`
  returned
- `capture_report.md` — the audit of `house.yml` against the instance, and the
  answers to the open questions in `INTENT.md` section 11

These are committed on purpose. `sources.fixture.FixtureSource` replays them so
the dashboard can be developed and tested against real data.

**Captured 2026-09-19.** All 24 configured entities resolved; the three
`UNCONFIRMED` humidity ids and the `ude` row in `house.yml` were all guessed
correctly. `capture_report.md` holds the audit and the answers to `INTENT.md`
section 11; `PLAN.md` records what those answers changed.

`sets/` holds the recordings a live capture cannot give you: `hostile/`, which
is every unpleasant shape at once — an absent entity, `unavailable`, `unknown`,
a string where a float belongs, an empty forecast — and `nominal/`, which is
**synthetic** and stands in until the real capture lands. See `sets/README.md`.

Re-record with:

```bash
python3 tools/capture_snapshot.py
```
