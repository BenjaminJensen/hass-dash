# Capture report

Captured 2026-09-19T17:26:03+00:00 from the live Home Assistant instance by
`tools/capture_snapshot.py`. This file answers the open questions in
`INTENT.md` section 11 from the wire rather than from guesswork.

## Entities named by house.yml

Anything marked MISSING is a typo or a renamed entity, and the
dashboard will show a placeholder for it forever.

| Room | Role | Entity | Value | Unit | Name |
| --- | --- | --- | --- | --- | --- |
| Stue | humidity | `sensor.0x5cc7c1fffede1ef5_humidity_2` | 69 | % | Gulvvarme Humidity |
| Stue | climate | `climate.0x5cc7c1fffede1ef5_2` | heat |  | Gulvvarme 2 |
| Køkken | humidity | `sensor.0x5cc7c1fffede1ef5_humidity_6` | 66 | % | Køkken Danfoss |
| Køkken | climate | `climate.0x5cc7c1fffede1ef5_6` | heat |  | Gulvvarme 6 |
| Soveværelse | humidity | `sensor.0x5cc7c1fffede1ef5_humidity_1` | 72 | % | Gulvvarme Humidity |
| Soveværelse | climate | `climate.0x5cc7c1fffede1ef5_1` | heat |  | Gulvvarme 1 |
| Stort bad | humidity | `sensor.0x5cc7c1fffede1ef5_humidity_5` | 75 | % | Stort Bad Danfoss |
| Stort bad | climate | `climate.0x5cc7c1fffede1ef5_5` | heat |  | Gulvvarme 5 |
| Lille bad | humidity | `sensor.0x5cc7c1fffede1ef5_humidity_7` | 64 | % | Lille Bad Danfoss |
| Lille bad | climate | `climate.0x5cc7c1fffede1ef5_7` | heat |  | Gulvvarme 7 |
| Sune | humidity | `sensor.0x5cc7c1fffede1ef5_humidity_4` | 68 | % | Gulvvarme Humidity |
| Sune | climate | `climate.0x5cc7c1fffede1ef5_4` | heat |  | Gulvvarme 4 |
| Sophie | humidity | `sensor.0x5cc7c1fffede1ef5_humidity_8` | 69 | % | Gulvvarme Humidity |
| Sophie | climate | `climate.0x5cc7c1fffede1ef5_8` | heat |  | Gulvvarme 8 |
| Marius | humidity | `sensor.0x5cc7c1fffede1ef5_humidity_3` | 69 | % | Gulvvarme Humidity |
| Marius | climate | `climate.0x5cc7c1fffede1ef5_3` | heat |  | Marius |
| Gang | humidity | `sensor.0x5cc7c1fffede1ef5_humidity_9` | 65 | % | Gulvvarme Humidity |
| Gang | climate | `climate.0x5cc7c1fffede1ef5_9` | heat |  | Gulvvarme 9 |
| Garage | humidity | `sensor.0x5cc7c1fffede1ef5_humidity_10` | 66 | % | Gulvvarme Humidity |
| Garage | climate | `climate.0x5cc7c1fffede1ef5_10` | heat |  | Gulvvarme 10 |
| Ude | temperature | `weather.home[temperature]` | 17.7 |  | Forecast Home |
| Ude | humidity | `weather.home[humidity]` | 92 |  | Forecast Home |
| - | weather | `weather.home` | cloudy |  | Forecast Home |
| - | sun | `sun.sun` | above_horizon |  | Sun |

**0 of 24 configured entities are missing.**

## Humidity sensors on the instance

`rooms.widget.yml` pointed `sophie` and `gang` at the same sensor. Use
the names below to settle which sensor belongs to which room.

| Entity | State | Name |
| --- | --- | --- |
| `sensor.0x00158d0001fd5ebe_humidity` | unavailable | Sune Humidity |
| `sensor.0x00158d0002024571_humidity` | unavailable | Marius Humidity |
| `sensor.0x00158d00020f601a_humidity` | unavailable | Køkken Humidity |
| `sensor.0x00158d00020ff999_humidity` | unavailable | Garage Humidity |
| `sensor.0x00158d00020ffbb9_humidity` | unavailable | Soveværelse Humidity |
| `sensor.0x00158d00025d9386_humidity` | unavailable | Sophie Humidity |
| `sensor.0x00158d000272675a_humidity` | unavailable | Bryggers Humidity |
| `sensor.0x00158d000273d218_humidity` | unavailable | Stue Humidity |
| `sensor.0x00158d0002e96dbf_humidity` | unavailable | Lille Bad Humidity |
| `sensor.0x00158d0002fb4826_humidity` | 76.56 | Stort bad Humidity |
| `sensor.0x5cc7c1fffede1ef5_humidity_1` | 72 | Gulvvarme Humidity |
| `sensor.0x5cc7c1fffede1ef5_humidity_10` | 66 | Gulvvarme Humidity |
| `sensor.0x5cc7c1fffede1ef5_humidity_11` | unknown | Gulvvarme Humidity |
| `sensor.0x5cc7c1fffede1ef5_humidity_12` | unknown | Gulvvarme Humidity |
| `sensor.0x5cc7c1fffede1ef5_humidity_13` | unknown | Gulvvarme Humidity |
| `sensor.0x5cc7c1fffede1ef5_humidity_14` | unknown | Gulvvarme Humidity |
| `sensor.0x5cc7c1fffede1ef5_humidity_15` | unknown | Gulvvarme Humidity |
| `sensor.0x5cc7c1fffede1ef5_humidity_2` | 69 | Gulvvarme Humidity |
| `sensor.0x5cc7c1fffede1ef5_humidity_3` | 69 | Gulvvarme Humidity |
| `sensor.0x5cc7c1fffede1ef5_humidity_4` | 68 | Gulvvarme Humidity |
| `sensor.0x5cc7c1fffede1ef5_humidity_5` | 75 | Stort Bad Danfoss |
| `sensor.0x5cc7c1fffede1ef5_humidity_6` | 66 | Køkken Danfoss |
| `sensor.0x5cc7c1fffede1ef5_humidity_7` | 64 | Lille Bad Danfoss |
| `sensor.0x5cc7c1fffede1ef5_humidity_8` | 69 | Gulvvarme Humidity |
| `sensor.0x5cc7c1fffede1ef5_humidity_9` | 65 | Gulvvarme Humidity |
| `sensor.abs_hum_gang` | 14.8 | Gang Air Quality |
| `sensor.abs_hum_garage` | 14.53 | Garage Air Quality |
| `sensor.abs_hum_koekken` | 14.28 | Køkken Air Quality |
| `sensor.abs_hum_lille_bad` | 14.74 | Lille bad Air Quality |
| `sensor.abs_hum_marius` | 14.59 | Marius Air Quality |
| `sensor.abs_hum_sophie` | 14.43 | Sophie Air Quality |
| `sensor.abs_hum_sovevaerelse` | 14.8 | Soveværelse Air Quality |
| `sensor.abs_hum_stort_bad` | 17.46 | Stort Bad Air Quality |
| `sensor.abs_hum_stue` | 14.43 | Stue Air Quality |
| `sensor.abs_hum_sune` | 14.14 | Sune Air Quality |
| `sensor.genvex_humidity` | unknown | Genvex Controller v.2 Genvex Humidity |
| `sensor.ude_sensor_ude_humidity` | 100.0 | Ude Sensor Ude Humidity |

## Temperature sensors the configuration does not use

If one of these is outdoors, it should back the `ude` row instead of
the weather provider.

| Entity | State | Name |
| --- | --- | --- |
| `sensor.0x00158d0001fd5ebe_temperature` | unavailable | Sune Temperature |
| `sensor.0x00158d0002024571_temperature` | unavailable | Marius Temperature |
| `sensor.0x00158d00020f601a_temperature` | unavailable | Køkken Temperature |
| `sensor.0x00158d00020ff999_temperature` | unavailable | Garage Temperature |
| `sensor.0x00158d00020ffbb9_temperature` | unavailable | Soveværelse Temperature |
| `sensor.0x00158d00025d9386_temperature` | unavailable | Sophie Temperature |
| `sensor.0x00158d000272675a_temperature` | unavailable | Bryggers Temperature |
| `sensor.0x00158d000273d218_temperature` | unavailable | Stue Temperature |
| `sensor.0x00158d0002e96dbf_temperature` | unavailable | Lille Bad Temperature |
| `sensor.0x00158d0002fb4826_temperature` | 25.22 | Stort bad Temperature |
| `sensor.0x5cc7c1fffede1ef5_temperature_1` | unknown | Gulvvarme Temperature |
| `sensor.0x5cc7c1fffede1ef5_temperature_10` | unknown | Gulvvarme Temperature |
| `sensor.0x5cc7c1fffede1ef5_temperature_11` | unknown | Gulvvarme Temperature |
| `sensor.0x5cc7c1fffede1ef5_temperature_12` | unknown | Gulvvarme Temperature |
| `sensor.0x5cc7c1fffede1ef5_temperature_13` | unknown | Gulvvarme Temperature |
| `sensor.0x5cc7c1fffede1ef5_temperature_14` | unknown | Gulvvarme Temperature |
| `sensor.0x5cc7c1fffede1ef5_temperature_15` | unknown | Gulvvarme Temperature |
| `sensor.0x5cc7c1fffede1ef5_temperature_2` | unknown | Gulvvarme Temperature |
| `sensor.0x5cc7c1fffede1ef5_temperature_3` | unknown | Gulvvarme Temperature |
| `sensor.0x5cc7c1fffede1ef5_temperature_4` | unknown | Gulvvarme Temperature |
| `sensor.0x5cc7c1fffede1ef5_temperature_5` | 25.39 | Stort Bad Gulv |
| `sensor.0x5cc7c1fffede1ef5_temperature_6` | unknown | Gulvvarme Temperature |
| `sensor.0x5cc7c1fffede1ef5_temperature_7` | 27.32 | Lille Bad Gulv |
| `sensor.0x5cc7c1fffede1ef5_temperature_8` | unknown | Gulvvarme Temperature |
| `sensor.0x5cc7c1fffede1ef5_temperature_9` | unknown | Gulvvarme Temperature |
| `sensor.genvex_temperature` | unknown | Genvex Controller v.2 Genvex Temperature |
| `sensor.ude_sensor_ude_temperature` | 23.2337112426758 | Ude Sensor Ude Temperature |

## Weather depth on `weather.home`

| Attribute | Present | Value |
| --- | --- | --- |
| `temperature` | yes | 17.7 |
| `apparent_temperature` | **no** |  |
| `humidity` | yes | 92 |
| `pressure` | yes | 1009.5 |
| `wind_speed` | yes | 23.0 |
| `wind_bearing` | yes | 237.0 |
| `precipitation_unit` | yes | mm |

Other attributes present: `attribution`, `cloud_coverage`, `dew_point`, `friendly_name`, `pressure_unit`, `supported_features`, `temperature_unit`, `uv_index`, `visibility_unit`, `wind_gust_speed`, `wind_speed_unit`.

## Hourly forecast

48 entries. Keys across all entries: `cloud_coverage`, `condition`, `datetime`, `humidity`, `precipitation`, `precipitation_probability`, `temperature`, `uv_index`, `wind_bearing`, `wind_gust_speed`, `wind_speed`

First entry:

```json
{
  "condition": "cloudy",
  "precipitation_probability": 20.6,
  "datetime": "2026-09-19T18:00:00+00:00",
  "wind_bearing": 230.0,
  "cloud_coverage": 99.9,
  "uv_index": 0.0,
  "temperature": 17.5,
  "wind_gust_speed": 36.7,
  "wind_speed": 22.0,
  "precipitation": 0.0,
  "humidity": 93
}
```

## Daily forecast

6 entries. Keys across all entries: `condition`, `datetime`, `humidity`, `precipitation`, `precipitation_probability`, `temperature`, `templow`, `uv_index`, `wind_bearing`, `wind_gust_speed`, `wind_speed`

First entry:

```json
{
  "condition": "cloudy",
  "precipitation_probability": 31.9,
  "datetime": "2026-09-19T10:00:00+00:00",
  "wind_bearing": 237.0,
  "uv_index": 0.0,
  "temperature": 17.7,
  "templow": 16.7,
  "wind_gust_speed": 44.3,
  "wind_speed": 26.3,
  "precipitation": 0.0,
  "humidity": 92
}
```
