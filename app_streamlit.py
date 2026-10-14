"""
Esempio di app Streamlit che usa il server MCP (server.py) come sorgente dati.
Cerca una citta', mostra il meteo e le coordinate scambiate con il server MCP.

Avvio:  streamlit run app_streamlit.py
Servono: pip install -r requirements.txt
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
            if risultato.isError:
                raise RuntimeError(testi[0] if testi else "Errore dal server MCP")
            return json.loads(testi[0])


def chiama(strumento: str, argomenti: dict):
    return asyncio.run(_chiama(strumento, argomenti))


@st.cache_data(ttl=3600)  # cache di 1 ora
def cerca(nome: str):
    return chiama("cerca_localita", {"nome": nome})


@st.cache_data(ttl=600)  # cache di 10 minuti
def meteo_attuale(lat: float, lon: float):
    return chiama("meteo_attuale", {"latitudine": lat, "longitudine": lon})


@st.cache_data(ttl=1800)  # cache di 30 minuti
def previsioni(giorni: int, lat: float, lon: float):
    return chiama("previsioni", {"giorni": giorni, "latitudine": lat, "longitudine": lon})


# ---------- Ricerca della citta' ----------
st.title("Meteo")
nome = st.text_input("Cerca una città", value="Monterotondo")

if not nome.strip():
    st.info("Scrivi il nome di una città per iniziare.")
    st.stop()

try:
    ricerca = cerca(nome.strip())
except Exception as e:
    st.error(f"Errore nella ricerca: {e}")
    st.stop()

risultati = ricerca["risultati"]
if not risultati:
    st.warning(f"Nessuna località trovata per «{nome}».")
    st.stop()


def etichetta(r: dict) -> str:
    zona = ", ".join(x for x in (r["regione"], r["paese"]) if x)
    return f"{r['nome']} ({zona})  ·  {r['latitudine']:.4f}, {r['longitudine']:.4f}"


scelta = st.selectbox("Località", risultati, format_func=etichetta)
lat, lon = scelta["latitudine"], scelta["longitudine"]

# ---------- Meteo attuale ----------
st.header(scelta["nome"])
try:
    ora = meteo_attuale(lat, lon)
except Exception as e:
    st.error(f"Errore nel recupero del meteo: {e}")
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Temperatura", f"{ora['temperatura_c']} °C", f"percepita {ora['percepita_c']} °C")
col2.metric("Umidità", f"{ora['umidita_pct']} %")
col3.metric("Vento", f"{ora['vento_kmh']} km/h", f"raffiche {ora['raffiche_kmh']}")
st.caption(f"{ora['condizioni']} · aggiornato {data_leggibile(ora['ora_locale'])}")

# ---------- Previsioni ----------
giorni = st.slider("Giorni di previsione", 1, 16, 7)
prev = previsioni(giorni, lat, lon)
df = pd.DataFrame(prev["giorni"]).set_index("data")
st.line_chart(df[["min_c", "max_c"]])
st.dataframe(df)

# ---------- Coordinate e chiamate MCP ----------
with st.expander("Coordinate e chiamate al server MCP", expanded=True):
    st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}), zoom=9)

    usate = ora["coordinate"]["usate"]
    confronto = pd.DataFrame(
        {
            "latitudine": [lat, usate["latitudine"]],
            "longitudine": [lon, usate["longitudine"]],
        },
        index=["Inviate dall'app (da cerca_localita)", "Usate da Open-Meteo (cella del modello)"],
    )
    st.dataframe(confronto)
    st.caption(
        f"Altitudine del punto: {ora['coordinate']['altitudine_m']} m · "
        f"fuso orario: {ora['coordinate']['fuso_orario']}. "
        "Open-Meteo aggancia il punto richiesto alla cella del modello più vicina, "
        "per questo le coordinate possono differire leggermente."
    )

    st.markdown("**1 · `cerca_localita`**")
    c1, c2 = st.columns(2)
    c1.caption("Argomenti inviati")
    c1.json({"nome": nome.strip()})
    c2.caption("Risposta del server")
    c2.json(ricerca, expanded=1)

    st.markdown("**2 · `meteo_attuale`**")
    c1, c2 = st.columns(2)
    c1.caption("Argomenti inviati")
    c1.json({"latitudine": lat, "longitudine": lon})
    c2.caption("Blocco `coordinate` della risposta")
    c2.json(ora["coordinate"])

    st.markdown("**3 · `previsioni`**")
    c1, c2 = st.columns(2)
    c1.caption("Argomenti inviati")
    c1.json({"giorni": giorni, "latitudine": lat, "longitudine": lon})
    c2.caption("Blocco `coordinate` della risposta")
    c2.json(prev["coordinate"])
