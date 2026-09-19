# Fixtures

Recorded Home Assistant payloads, produced by `tools/capture_snapshot.py` run
against the live instance from outside the container:

- `states.json` — the climate-relevant entities, keyed by entity id
- `forecast_hourly.json` / `forecast_daily.json` — what `weather.get_forecasts`
  returned
- `capture_report.md` — the audit of `house.yml` against the instance, and the
  answers to the open questions in `INTENT.md` section 11

These are committed on purpose. The fixture source replays them so the
dashboard can be developed and tested against real data, including the
unpleasant shapes — an absent entity, `unavailable`, a string where a float was
expected, an empty forecast.

Re-record with:

```bash
python3 tools/capture_snapshot.py
```
