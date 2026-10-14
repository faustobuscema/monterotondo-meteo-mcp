"""
Server MCP di esempio per dati meteorologici e previsioni.

Usa Open-Meteo (gratuito, senza chiave API) e di default punta a Fonte di Papa - Monterotondo RM.
Strumenti esposti:
  - cerca_localita:   da nome a coordinate
  - meteo_attuale:    condizioni in questo momento
  - previsioni:       previsioni giornaliere (1-16 giorni)

Le risposte di meteo_attuale e previsioni includono un blocco "coordinate" con
le coordinate richieste e quelle effettivamente usate da Open-Meteo (che
"aggancia" il punto alla cella del modello meteo piu' vicina).

Avvio locale (stdio):          python server.py
Avvio come servizio HTTP:      python server.py --http
"""
import sys

import httpx
from mcp.server.fastmcp import FastMCP

# Fonte di Papa - Monterotondo (RM) come localita' predefinita
LAT_DEFAULT = 42.0527
LON_DEFAULT = 12.6160

mcp = FastMCP("meteo", host="0.0.0.0", port=8000)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Codici WMO restituiti da Open-Meteo -> descrizione in italiano
WMO = {
    0: "Sereno", 1: "Prevalentemente sereno", 2: "Parzialmente nuvoloso",
    3: "Coperto", 45: "Nebbia", 48: "Nebbia con brina",
    51: "Pioviggine leggera", 53: "Pioviggine", 55: "Pioviggine intensa",
    61: "Pioggia debole", 63: "Pioggia moderata", 65: "Pioggia forte",
    71: "Neve debole", 73: "Neve moderata", 75: "Neve forte",
    80: "Rovesci deboli", 81: "Rovesci moderati", 82: "Rovesci violenti",
    95: "Temporale", 96: "Temporale con grandine", 99: "Temporale con forte grandine",
}


def _descrizione(codice: int) -> str:
    return WMO.get(codice, f"Codice meteo {codice}")


def _coordinate(lat: float, lon: float, dati: dict) -> dict:
    """Coordinate ricevute dal client e coordinate usate da Open-Meteo."""
    return {
        "richieste": {"latitudine": lat, "longitudine": lon},
        "usate": {"latitudine": dati["latitude"], "longitudine": dati["longitude"]},
        "altitudine_m": dati.get("elevation"),
        "fuso_orario": dati.get("timezone"),
    }


async def _get(url: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def cerca_localita(nome: str, max_risultati: int = 5) -> dict:
    """Cerca una localita' per nome e restituisce nome, regione, latitudine e longitudine."""
    dati = await _get(
        GEOCODING_URL,
        {"name": nome, "count": max_risultati, "language": "it", "format": "json"},
    )
    return {
        "ricerca": nome,
        "risultati": [
            {
                "nome": r["name"],
                "regione": r.get("admin1"),
                "paese": r.get("country"),
                "latitudine": r["latitude"],
                "longitudine": r["longitude"],
            }
            for r in dati.get("results", [])
        ],
    }


@mcp.tool()
async def meteo_attuale(
    latitudine: float = LAT_DEFAULT, longitudine: float = LON_DEFAULT
) -> dict:
    """Condizioni meteo attuali per le coordinate indicate (default: Monterotondo)."""
    dati = await _get(
        FORECAST_URL,
        {
            "latitude": latitudine,
            "longitude": longitudine,
            "current": (
                "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "precipitation,weather_code,wind_speed_10m,wind_gusts_10m,"
                "pressure_msl"
            ),
            "wind_speed_unit": "kmh",
            "timezone": "Europe/Rome",
        },
    )
    c = dati["current"]
    return {
        "coordinate": _coordinate(latitudine, longitudine, dati),
        "ora_locale": c["time"],
        "condizioni": _descrizione(c["weather_code"]),
        "temperatura_c": c["temperature_2m"],
        "percepita_c": c["apparent_temperature"],
        "umidita_pct": c["relative_humidity_2m"],
        "precipitazioni_mm": c["precipitation"],
        "vento_kmh": c["wind_speed_10m"],
        "raffiche_kmh": c["wind_gusts_10m"],
        "pressione_hpa": c["pressure_msl"],
    }


@mcp.tool()
async def previsioni(
    giorni: int = 7,
    latitudine: float = LAT_DEFAULT,
    longitudine: float = LON_DEFAULT,
) -> dict:
    """Previsioni giornaliere (da 1 a 16 giorni): minime, massime, pioggia, vento."""
    giorni = max(1, min(giorni, 16))
    dati = await _get(
        FORECAST_URL,
        {
            "latitude": latitudine,
            "longitude": longitudine,
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_sum,precipitation_probability_max,"
                "wind_speed_10m_max"
            ),
            "wind_speed_unit": "kmh",
            "forecast_days": giorni,
            "timezone": "Europe/Rome",
        },
    )
    d = dati["daily"]
    return {
        "coordinate": _coordinate(latitudine, longitudine, dati),
        "giorni": [
            {
                "data": d["time"][i],
                "condizioni": _descrizione(d["weather_code"][i]),
                "min_c": d["temperature_2m_min"][i],
                "max_c": d["temperature_2m_max"][i],
                "pioggia_mm": d["precipitation_sum"][i],
                "probabilita_pioggia_pct": d["precipitation_probability_max"][i],
                "vento_max_kmh": d["wind_speed_10m_max"][i],
            }
            for i in range(len(d["time"]))
        ],
    }


if __name__ == "__main__":
    if "--http" in sys.argv:
        # Servizio remoto: endpoint su http://host:8000/mcp
        mcp.run(transport="streamable-http")
    else:
        # Uso locale: il client avvia il server come sottoprocesso
        mcp.run(transport="stdio")
