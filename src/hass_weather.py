from homeassistant_api import Client
from typing import Dict, Any, Optional
import re
from datetime import datetime as DateTimes

from localize import local_dt_from_utc_str

def _get_icon_for_condition(cond: Optional[str], is_night = False) -> Optional[str]:
    """Return the icon filename for a given Home Assistant condition key.

    Uses canonical HA keys and normalizes both map keys and the incoming
    condition by removing non-alphanumeric characters and lowercasing
    before doing an exact lookup.
    """

    icon_map = {
        # canonical HA keys (more specific first)
        "lightning-rainy": "weather-lightning-rainy",
        "snowy-rainy": "weather-snowy-rainy",
        "windy-variant": "weather-windy-variant",
        "clear-night": "weather-night",
        # simple canonical keys
        "lightning": "weather-lightning",
        "hail": "weather-hail",
        "pouring": "weather-pouring",
        "rainy": "weather-rainy",
        "snowy": "weather-snowy",
        "partlycloudy": "weather-partly-cloudy",
        "cloudy": "weather-cloudy",
        "fog": "weather-fog",
        "sunny": "weather-sunny",
        "windy": "weather-windy",
        "exceptional": "weather-cloudy-alert",
    }

    def _norm_alnum(s: str) -> str:
        return re.sub(r'[^a-z0-9]+', '', (s or '').lower())

    normalized_icon_map = { _norm_alnum(k): v for k, v in icon_map.items() }
    icon = normalized_icon_map.get(_norm_alnum(cond or ''))
    if icon == "weather-partly-cloudy" and is_night:
        icon = "weather-night-partly-cloudy"

    return icon

class WeatherItem:
    def __init__(self, data: Dict[str, Any], is_night: bool = False) -> None:
        self.data = data
        self.temperature: Optional[float] = None
        self.humidity: Optional[float] = None
        self.time: Optional[DateTime] = None
        self.condition: Optional[str] = None
        self.condition_icon: Optional[str] = None
        self.is_night = is_night
        self.parse_data()

    def parse_data(self):
        # Expected input example (one forecast item):
        # {
        #   "condition": "cloudy",
        #   "precipitation_probability": 6.2,
        #   "datetime": "2025-10-27T07:00:00+00:00",
        #   "wind_bearing": 240.4,
        #   "cloud_coverage": 92.9,
        #   "uv_index": 0.1,
        #   "temperature": 7.7,
        #   "wind_gust_speed": 28.8,
        #   "wind_speed": 18.0,
        #   "precipitation": 0.0,
        #   "humidity": 92
        # }

        def to_float(v):
            try:
                if v is None:
                    return None
                return float(v)
            except Exception:
                return None

                # Encapsulate mapping and normalization in an inner helper for clarity.
       
        d = self.data or {}

        # temperature / humidity
        self.temperature = to_float(d.get("temperature") or d.get("temp") or d.get("current_temperature"))
        self.humidity = to_float(d.get("humidity") or d.get("relative_humidity") or d.get("hum"))

        # time
        dt = d.get("datetime") or d.get("time") or d.get("dt")
        if isinstance(dt, str):
            try:
                self.time = local_dt_from_utc_str(dt)  # Convert to local timezone
                #print(f"Parsed datetime string '{dt}' to {self.time}")
            except Exception:
                self.time = None
        else:
            self.time = None

        # condition and a simple icon mapping
        cond = d.get("condition") or d.get("state")
        self.condition = str(cond) if cond is not None else None

        # Lookup icon using the helper
        self.condition_icon = _get_icon_for_condition(self.condition, self.is_night)

        # additional telemetry (optional)
        self.precipitation_probability = to_float(d.get("precipitation_probability"))
        self.precipitation = to_float(d.get("precipitation"))
        self.wind_speed = to_float(d.get("wind_speed"))
        self.wind_gust_speed = to_float(d.get("wind_gust_speed"))
        self.wind_bearing = to_float(d.get("wind_bearing"))
        self.cloud_coverage = to_float(d.get("cloud_coverage"))
        self.uv_index = to_float(d.get("uv_index"))

    def __repr__(self) -> str:
        # Show a compact, human readable summary: time, condition, temperature, humidity
        # Time formatted as YYYY-MM-DD HH:MM:SS ±TZ if available
        if self.time is not None:
            try:
                # Show only hour:minute in 24-hour format
                time_str = self.time.strftime("%H:%M")
            except Exception:
                time_str = str(self.time)
        else:
            time_str = "n/a"

        cond = self.condition or (self.data.get("condition") if isinstance(self.data, dict) else None) or "n/a"

        if self.temperature is not None:
            try:
                temp_str = f"{float(self.temperature):.1f}°C"
            except Exception:
                temp_str = str(self.temperature)
        else:
            temp_str = "n/a"

        if self.humidity is not None:
            try:
                hum_str = f"{int(float(self.humidity))}%"
            except Exception:
                hum_str = str(self.humidity)
        else:
            hum_str = "n/a"
        # condition_icon (filename) if available
        icon_str = self.condition_icon if self.condition_icon is not None else "n/a"

        return (
            f"WeatherItem(time={time_str}, condition={cond}, temperature={temp_str}, "
            f"humidity={hum_str}, icon={icon_str})"
        )
    
class HassWeather:
    """Simple wrapper for a weather entity similar to HassRoom.

    The class exposes attributes populated by `update()`:
      - temperature: Optional[float]
      - humidity: Optional[float]
      - forecast: Optional[Any]


    The weather API returns:
    {
        "temperature": 9.0,
        "dew_point": 6.9,
        "temperature_unit": "\u00b0C",
        "humidity": 86,
        "cloud_coverage": 99.9,
        "uv_index": 0.0,
        "pressure": 988.7,
        "pressure_unit": "hPa",
        "wind_bearing": 197.1,
        "wind_gust_speed": 52.2,
        "wind_speed": 31.7,
        "wind_speed_unit": "km/h",
        "visibility_unit": "km",
        "precipitation_unit": "mm",
        "attribution": "Weather forecast from met.no, delivered by the Norwegian Meteorological Institute.",
        "friendly_name": "Forecast Home",
        "supported_features": 3
    }
    """

    def __init__(self, client: Client, is_night: bool = False) -> None:
        self.client = client
        self.is_night = is_night

        # runtime values
        self.temperature: Optional[float] = None
        self.humidity: Optional[float] = None
        self.forecast: Optional[list] = None

    def convert_to_float(self, value: Any) -> Optional[float]:
        """Convert a value to float if possible, otherwise return None."""
        try:
            if value is None:
                return None
            elif isinstance(value, (int, float, str)):
                return float(value)
            else:
                # Unknown type (e.g. dict), return None
                return None
        except (ValueError, TypeError):
            return None
    
    def update_forecast(self) -> None:
        """Fetch forecast data and populate the forecast field."""
        with self.client:
            w = self.client.get_domain("weather")
            if w is None:
                raise RuntimeError("Weather domain not found")
            fc = w.get_forecasts(device_id="c8e8bb619ae918a8ed095ab1889f5a07", type="hourly") # type: ignore
            forecast_list = fc[1]['weather.home']['forecast'] # type: ignore
            if not isinstance(forecast_list, list):
                raise RuntimeError("Forecast data is not a list")
            self.forecast = []
            for item_data in forecast_list:
                weather_item = WeatherItem(item_data, self.is_night) # type: ignore  
                #print(f"Parsed forecast item: {weather_item}")              
                self.forecast.append(weather_item)

    def update_weather(self) -> None:
        """Fetch weather entity attributes and populate fields."""
        with self.client:
            weather = self.client.get_entity(entity_id="weather.home")
            if weather is None:
                raise RuntimeError("Weather entity not found")
            state = weather.get_state()  # Because requests are cached we reduce bandwidth usage :D

            if state is None:
                raise RuntimeError("Weather state is None")
            
            # Safely convert temperature attribute to float if possible
            temp_val = state.attributes.get("temperature")
            self.temperature = self.convert_to_float(temp_val)
            hum_val = state.attributes.get("humidity")
            self.humidity = self.convert_to_float(hum_val)
            self.condition_icon = _get_icon_for_condition(state.state, self.is_night)
            self.update_forecast()

    def update(self) -> None:
        """Perform all updates (weather entity first, then optional sensor)."""
        self.update_weather()

    def get_forecast(self) -> Optional[list]:
        """Return the forecast data."""
        if self.forecast is None:
            return None
        else:
            return self.forecast[1::2][:5]

    def __repr__(self) -> str:
        parts = []
        if self.temperature is not None:
            parts.append(f"temperature={self.temperature}")
        if self.humidity is not None:
            parts.append(f"humidity={self.humidity}")
        if self.forecast is not None:
            parts.append(f"forecast_len={len(self.forecast) if hasattr(self.forecast, '__len__') else '1'}")
        return f"HassWeather({', '.join(parts)})"
