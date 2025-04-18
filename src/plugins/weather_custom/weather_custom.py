from plugins.base_plugin.base_plugin import BasePlugin
import requests
from datetime import datetime
import pytz
import logging

logger = logging.getLogger(__name__)

OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast?"
    "latitude={lat}&longitude={long}"
    "&current=temperature_2m,relative_humidity_2m,precipitation,rain,wind_speed_10m," 
    "wind_direction_10m,pressure_msl"
    "&daily=temperature_2m_max,temperature_2m_min,sunrise,sunset,weathercode,uv_index_max"
    "&hourly=temperature_2m,rain"
    "&timezone=auto"
)

AIR_QUALITY_URL = (
    "https://air-quality-api.open-meteo.com/v1/air-quality?"
    "latitude={lat}&longitude={long}&hourly=european_aqi&timezone=auto"
)

WEATHER_CODE_ICONS = {
    0: "01d", 1: "02d", 2: "03d", 3: "04d",
    45: "50d", 48: "50d",
    51: "09d", 53: "09d", 55: "09d", 56: "09d", 57: "09d",
    61: "10d", 63: "10d", 65: "10d",
    66: "13d", 67: "13d",
    71: "13d", 73: "13d", 75: "13d", 77: "13d",
    80: "09d", 81: "09d", 82: "09d",
    85: "13d", 86: "13d",
    95: "11d", 96: "11d", 99: "11d"
}

class Weather(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        lat = settings.get('latitude')
        long = settings.get('longitude')
        if not lat or not long:
            raise RuntimeError("Latitude and Longitude are required.")

        weather_data = self.get_weather_data(lat, long)
        air_quality_data = self.get_air_quality(lat, long)

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        timezone_str = weather_data.get("timezone", device_config.get_config("timezone", default="UTC"))
        tz = pytz.timezone(timezone_str)

        template_params = self.parse_weather_data(weather_data, air_quality_data, tz)
        template_params["plugin_settings"] = settings

        image = self.render_image(dimensions, "weather.html", "weather.css", template_params)
        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")
        return image

    def get_weather_data(self, lat, long):
        url = OPEN_METEO_URL.format(lat=lat, long=long)
        response = requests.get(url)
        if not response.ok:
            logger.error(f"Failed to fetch weather data: {response.content}")
            raise RuntimeError("Failed to fetch weather data.")
        return response.json()

    def get_air_quality(self, lat, long):
        url = AIR_QUALITY_URL.format(lat=lat, long=long)
        response = requests.get(url)
        if not response.ok:
            logger.error(f"Failed to fetch air quality data: {response.content}")
            return None
        return response.json()

    def parse_weather_data(self, data, air_quality, tz):
        current = data["current"]
        daily = data["daily"]

        dt = datetime.fromisoformat(current["time"]).astimezone(tz)
        icon_code = WEATHER_CODE_ICONS.get(daily["weathercode"][0], "01d")

        return {
            "current_date": dt.strftime("%A, %B %d"),
            "location": f"{data['latitude']:.2f}, {data['longitude']:.2f}",
            "current_temperature": str(round(current["temperature_2m"])),
            "feels_like": "–",
            "temperature_unit": "°C",
            "units": "metric",
            "current_day_icon": self.get_plugin_dir(f"icons/{icon_code}.png"),
            "forecast": self.parse_forecast(daily, tz),
            "hourly_forecast": self.parse_hourly(data["hourly"], tz),
            "data_points": self.parse_data_points(current, daily, tz, air_quality)
        }

    def parse_forecast(self, daily, tz):
        forecast = []
        for i in range(1, min(len(daily["time"]), 6)):
            dt = datetime.fromisoformat(daily["time"][i]).astimezone(tz)
            icon = WEATHER_CODE_ICONS.get(daily["weathercode"][i], "01d")
            forecast.append({
                "day": dt.strftime("%a"),
                "high": int(daily["temperature_2m_max"][i]),
                "low": int(daily["temperature_2m_min"][i]),
                "icon": self.get_plugin_dir(f"icons/{icon}.png")
            })
        return forecast

    def parse_hourly(self, hourly, tz):
        hourly_list = []
        for i in range(24):
            dt = datetime.fromisoformat(hourly["time"][i]).astimezone(tz)
            hourly_list.append({
                "time": dt.strftime("%-I %p"),
                "temperature": round(hourly["temperature_2m"][i]),
                "precipitiation": hourly["rain"][i]
            })
        return hourly_list

    def parse_data_points(self, current, daily, tz, air_quality=None):
        sunrise_dt = datetime.fromisoformat(daily["sunrise"][0]).astimezone(tz)
        sunset_dt = datetime.fromisoformat(daily["sunset"][0]).astimezone(tz)

        data_points = [
            {
                "label": "Sunrise",
                "measurement": sunrise_dt.strftime('%I:%M').lstrip("0"),
                "unit": sunrise_dt.strftime('%p'),
                "icon": self.get_plugin_dir('icons/sunrise.png')
            },
            {
                "label": "Sunset",
                "measurement": sunset_dt.strftime('%I:%M').lstrip("0"),
                "unit": sunset_dt.strftime('%p'),
                "icon": self.get_plugin_dir('icons/sunset.png')
            },
            {
                "label": "Wind",
                "measurement": round(current["wind_speed_10m"]),
                "unit": "km/h",
                "icon": self.get_plugin_dir('icons/wind.png')
            },
            {
                "label": "Humidity",
                "measurement": current["relative_humidity_2m"],
                "unit": "%",
                "icon": self.get_plugin_dir('icons/humidity.png')
            },
            {
                "label": "Pressure",
                "measurement": current["pressure_msl"],
                "unit": "hPa",
                "icon": self.get_plugin_dir('icons/pressure.png')
            },
            {
                "label": "UV Index",
                "measurement": daily["uv_index_max"][0],
                "unit": '',
                "icon": self.get_plugin_dir('icons/uvi.png')
            },
            {
                "label": "Rain",
                "measurement": current["rain"],
                "unit": "mm",
                "icon": self.get_plugin_dir('icons/rain.png')
            }
        ]

        if air_quality:
            try:
                aqi = air_quality["hourly"]["european_aqi"][0]
                aqi_label = self.get_aqi_description(aqi)
                data_points.append({
                    "label": "Air Quality",
                    "measurement": int(aqi),
                    "unit": aqi_label,
                    "icon": self.get_plugin_dir("icons/aqi.png")
                })
            except Exception as e:
                logger.warning(f"Failed to parse AQI: {e}")

        return data_points

    def get_aqi_description(self, aqi):
        if aqi <= 20:
            return "Good"
        elif aqi <= 40:
            return "Fair"
        elif aqi <= 60:
            return "Moderate"
        elif aqi <= 80:
            return "Poor"
        else:
            return "Very Poor"
