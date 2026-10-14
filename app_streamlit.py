"""
Esempio di app Streamlit che usa il server MCP (server.py) come sorgente dati.

Avvio:  streamlit run app_streamlit.py
Servono: pip install streamlit "mcp[cli]" httpx pandas
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Il client avvia server.py come sottoprocesso (trasporto stdio).
# Percorso assoluto: non dipende dalla cartella di lavoro (utile su Streamlit Cloud)
SERVER = StdioServerParameters(
    command=sys.executable,
    args=[str(Path(__file__).parent / "server.py")],
)

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def data_leggibile(iso: str) -> str:
    """'2026-10-14T12:00' -> 'mercoledì 14 ottobre, 12:00'"""
    d = datetime.fromisoformat(iso)
    return f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}, {d:%H:%M}"


async def _chiama(strumento: str, argomenti: dict):
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as sessione:
            await sessione.initialize()
            risultato = await sessione.call_tool(strumento, argomenti)
            # I risultati arrivano come blocchi di testo JSON
            testi = [b.text for b in risultato.content if b.type == "text"]
            dati = [json.loads(t) for t in testi]
            return dati[0] if len(dati) == 1 else dati


def chiama(strumento: str, argomenti: dict | None = None):
    return asyncio.run(_chiama(strumento, argomenti or {}))


@st.cache_data(ttl=600)  # cache di 10 minuti
def meteo_attuale():
    return chiama("meteo_attuale")


@st.cache_data(ttl=1800)  # cache di 30 minuti
def previsioni(giorni: int):
    return chiama("previsioni", {"giorni": giorni})


st.title("Meteo Monterotondo")

ora = meteo_attuale()
col1, col2, col3 = st.columns(3)
col1.metric("Temperatura", f"{ora['temperatura_c']} °C", f"percepita {ora['percepita_c']} °C")
col2.metric("Umidità", f"{ora['umidita_pct']} %")
col3.metric("Vento", f"{ora['vento_kmh']} km/h", f"raffiche {ora['raffiche_kmh']}")
st.caption(f"{ora['condizioni']} · aggiornato {data_leggibile(ora['ora_locale'])}")

giorni = st.slider("Giorni di previsione", 1, 16, 7)
df = pd.DataFrame(previsioni(giorni)).set_index("data")
st.line_chart(df[["min_c", "max_c"]])
st.dataframe(df)
