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

**This capture has not been run yet.** Until it has, the tests that depend on it
skip, and the three humidity entity ids and the whole `ude` row in `house.yml`
are a guess (see `INTENT.md` section 11).

`sets/` holds the recordings a live capture cannot give you: `hostile/`, which
is every unpleasant shape at once — an absent entity, `unavailable`, `unknown`,
a string where a float belongs, an empty forecast — and `nominal/`, which is
**synthetic** and stands in until the real capture lands. See `sets/README.md`.

Re-record with:

```bash
python3 tools/capture_snapshot.py
```
