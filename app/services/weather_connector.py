import httpx

from app.config import settings


class WeatherConnector:
    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

    def get_today(self) -> dict:
        location = self._geocode(settings.WEATHER_LOCATION)
        params = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "hourly": ",".join([
                "temperature_2m",
                "apparent_temperature",
                "precipitation_probability",
                "wind_speed_10m",
            ]),
            "current": ",".join([
                "temperature_2m",
                "apparent_temperature",
                "precipitation",
                "wind_speed_10m",
            ]),
            "timezone": "auto",
            "forecast_days": 1,
        }
        data = self._get_json(self.FORECAST_URL, params)
        data["resolved_location"] = location
        return data

    def _geocode(self, query: str) -> dict:
        data = self._get_json(
            self.GEOCODING_URL,
            {"name": query, "count": 1, "language": "es", "format": "json"},
        )
        results = data.get("results") or []

        # Open-Meteo suele resolver mejor nombres de ciudad/comuna sin el país
        # incluido en el mismo campo de búsqueda.
        if not results and "," in query:
            short_query = query.split(",", 1)[0].strip()
            data = self._get_json(
                self.GEOCODING_URL,
                {"name": short_query, "count": 1, "language": "es", "format": "json"},
            )
            results = data.get("results") or []

        if not results:
            raise RuntimeError(f"No pude encontrar la ubicación meteorológica: {query}")

        item = results[0]
        try:
            return {
                "name": item.get("name", query),
                "admin1": item.get("admin1", ""),
                "country": item.get("country", ""),
                "latitude": item["latitude"],
                "longitude": item["longitude"],
            }
        except KeyError as exc:
            raise RuntimeError("La ubicación meteorológica no entregó coordenadas.") from exc

    @staticmethod
    def _get_json(url: str, params: dict) -> dict:
        try:
            response = httpx.get(
                url,
                params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "NORA-Core/0.4.1",
                },
                timeout=10.0,
                follow_redirects=True,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise RuntimeError("El servicio meteorológico entregó una respuesta inesperada.")
            return data
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError("No pude consultar el servicio meteorológico.") from exc
