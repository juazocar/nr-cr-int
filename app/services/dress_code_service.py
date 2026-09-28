from app.config import settings
from app.services.weather_connector import WeatherConnector


class DressCodeService:
    def __init__(self) -> None:
        self._weather = WeatherConnector()

    def get_recommendation(self) -> dict:
        data = self._weather.get_today()
        hourly = data.get("hourly") or {}
        times = hourly.get("time") or []
        temperatures = hourly.get("temperature_2m") or []
        apparent = hourly.get("apparent_temperature") or []
        rain = hourly.get("precipitation_probability") or []
        wind = hourly.get("wind_speed_10m") or []

        selected = []
        for i, stamp in enumerate(times):
            try:
                hour = int(stamp[11:13])
            except (ValueError, IndexError):
                continue
            if settings.DRESS_CODE_START_HOUR <= hour <= settings.DRESS_CODE_END_HOUR:
                selected.append(i)

        if not selected:
            selected = list(range(len(times)))
        if not selected:
            raise RuntimeError("El pronóstico no entregó información horaria utilizable.")

        def values(series):
            return [series[i] for i in selected if i < len(series) and series[i] is not None]

        temps = values(temperatures)
        feels = values(apparent)
        rains = values(rain)
        winds = values(wind)
        if not temps:
            raise RuntimeError("El pronóstico no entregó temperaturas utilizables.")

        low = min(temps)
        high = max(temps)
        feels_low = min(feels) if feels else low
        rain_max = max(rains) if rains else 0
        wind_max = max(winds) if winds else 0
        thermal_range = high - low

        if feels_low < 5:
            clothing = "abrigo medio y una capa interior que puedas retirar"
        elif feels_low < 10:
            clothing = "chaqueta liviana o cortaviento sobre una capa ligera"
        elif feels_low < 15:
            clothing = "polerón o chaqueta liviana fácil de quitar"
        elif feels_low < 20:
            clothing = "ropa ligera y, si sales temprano, una capa delgada opcional"
        else:
            clothing = "ropa fresca y ligera"

        notes = []
        if thermal_range >= 8:
            notes.append("Habrá una subida importante de temperatura; evita un abrigo pesado y prioriza capas removibles.")
        if rain_max >= 40:
            notes.append("Conviene llevar protección para la lluvia.")
        if wind_max >= 30:
            notes.append("Habrá viento relevante; una capa cortaviento puede ser útil.")
        if not notes:
            notes.append("No se observan factores que justifiquen agregar muchas capas.")

        location = data.get("resolved_location") or {}
        current = data.get("current") or {}
        return {
            "location": ", ".join(x for x in [location.get("name"), location.get("admin1")] if x),
            "period": f"{settings.DRESS_CODE_START_HOUR:02d}:00-{settings.DRESS_CODE_END_HOUR:02d}:00",
            "current_temperature_c": current.get("temperature_2m"),
            "current_apparent_temperature_c": current.get("apparent_temperature"),
            "minimum_temperature_c": round(low, 1),
            "maximum_temperature_c": round(high, 1),
            "minimum_apparent_temperature_c": round(feels_low, 1),
            "maximum_rain_probability_pct": round(rain_max),
            "maximum_wind_kmh": round(wind_max, 1),
            "temperature_change_c": round(thermal_range, 1),
            "clothing_base": clothing,
            "advice": " ".join(notes),
        }
