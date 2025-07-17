import streamlit as st
import pandas as pd
import folium
import openrouteservice
from folium.features import DivIcon
import numpy as np
import tempfile
import streamlit.components.v1 as components

st.set_page_config(page_title="🗺️ Rotas Automáticas")

# Lê a chave do arquivo secrets.toml
api_key = st.secrets["ors_api_key"]["key"]

@st.cache_data
def carregar_escolas(caminho_csv):
    df = pd.read_csv(caminho_csv, encoding="latin1", sep=";")
    df.columns = df.columns.str.strip().str.lower()
    df["latitude"] = df["latitude"].astype(str).str.replace(",", ".").astype(float)
    df["longitude"] = df["longitude"].astype(str).str.replace(",", ".").astype(float)
    df["exibir"] = df["codigo"].astype(str) + " - " + df["nome"]
    return df

if "mostrar_mapa" not in st.session_state:
    st.session_state["mostrar_mapa"] = False
if "mapa_html_path" not in st.session_state:
    st.session_state["mapa_html_path"] = None

escolas_df = carregar_escolas("ESCOLAS-CAPITAL.csv")

st.title("🗺️ Rotas Automáticas")

map_placeholder = st.empty()

with st.form("roteirizador"):
    partida_exibir = st.selectbox("📍 Escolha o ponto de partida", escolas_df["exibir"].tolist())
    destinos_exibir = st.multiselect("🌟 Escolas de destino", escolas_df["exibir"].tolist())
    num_carros = st.number_input("🚘 Número de carros disponíveis", min_value=1, max_value=10, value=1)
    capacidade = st.number_input("👥 Pessoas por carro (incluindo motorista)", min_value=2, max_value=10, value=4)
    gerar = st.form_submit_button("🔄 Gerar rota")

def clusterizar_sequencial(destinos_df, partida, num_carros, capacidade_util):
    if len(destinos_df) == 0:
        return []

    destinos_restantes = destinos_df.copy().reset_index(drop=True)
    grupos = []

    for carro in range(num_carros):
        grupo = []
        ponto_atual = np.array([partida["latitude"], partida["longitude"]])

        while len(destinos_restantes) > 0 and len(grupo) < capacidade_util:
            destinos_coords = destinos_restantes[["latitude", "longitude"]].values
            distancias = np.linalg.norm(destinos_coords - ponto_atual, axis=1)
            idx_mais_proximo = np.argmin(distancias)

            destino_mais_proximo = destinos_restantes.iloc[idx_mais_proximo]
            grupo.append(destino_mais_proximo)

            destinos_restantes = destinos_restantes.drop(destinos_restantes.index[idx_mais_proximo]).reset_index(drop=True)
            ponto_atual = np.array([destino_mais_proximo["latitude"], destino_mais_proximo["longitude"]])

        if grupo:
            grupos.append(pd.DataFrame(grupo))

    if len(destinos_restantes) > 0:
        st.error(
            f"❌ Faltaram carros! Ainda restam {len(destinos_restantes)} destinos sem carro suficiente "
            f"para capacidade de {capacidade_util} passageiros por carro. "
            f"Aumente o número de carros ou a capacidade."
        )
        return []

    return grupos

def gerar_rotas_com_sequencial(partida_exibir, destinos_exibir, num_carros, capacidade):
    client = openrouteservice.Client(key=api_key)

    partida_codigo = int(partida_exibir.split(" - ")[0])
    destinos_codigos = [int(item.split(" - ")[0]) for item in destinos_exibir]

    if partida_codigo in destinos_codigos:
        destinos_codigos.remove(partida_codigo)

    if len(destinos_codigos) == 0:
        st.error("❌ Selecione ao menos um destino além do ponto de partida.")
        return

    partida = escolas_df[escolas_df["codigo"] == partida_codigo].iloc[0]
    destinos_df = escolas_df[escolas_df["codigo"].isin(destinos_codigos)].copy()

    capacidade_util = capacidade # Motorista é um dos tecnicos

    grupos = clusterizar_sequencial(destinos_df, partida, num_carros, capacidade_util)

    if not grupos:
        return  # Se deu erro, não continua

    mapa = folium.Map(location=[partida["latitude"], partida["longitude"]], zoom_start=13)

    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satélite',
        overlay=False,
        control=True
    ).add_to(mapa)

    cores = [
        "blue", "green", "red", "purple", "orange", "darkred", "lightred",
        "beige", "darkblue", "darkgreen"
    ]

    for i, grupo in enumerate(grupos):
        if grupo.empty:
            continue

        rota_df = pd.concat([pd.DataFrame([partida]), grupo], ignore_index=True)
        coordenadas = list(zip(rota_df["longitude"], rota_df["latitude"]))

        try:
            rota = client.directions(
                coordenadas,
                profile='driving-car',
                format='geojson',
                optimize_waypoints=True
            )
        except Exception as e:
            st.error(f"Erro ao solicitar rota para Carro {i+1}: {e}")
            continue

        folium.GeoJson(
            rota,
            name=f"Rota Carro {i+1}",
            style_function=lambda x, cor=cores[i % len(cores)]: {
                "color": cor, "weight": 5, "opacity": 0.7
            }
        ).add_to(mapa)

        for idx, row in rota_df.iterrows():
            folium.Marker(
                location=(row["latitude"], row["longitude"]),
                icon=DivIcon(
                    icon_size=(30, 30),
                    icon_anchor=(15, 15),
                    html=f'<div style="font-size: 14pt; color: {cores[i % len(cores)]}; font-weight: bold; background: white; border-radius: 50%; width: 30px; height: 30px; text-align: center; line-height: 30px;">{idx}</div>'
                ),
                tooltip=f"Carro {i+1} - {row['nome']}"
            ).add_to(mapa)

    folium.LayerControl().add_to(mapa)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".html", dir=".") as tmpfile:
        mapa.save(tmpfile.name)
        st.session_state["mapa_html_path"] = tmpfile.name

    st.session_state["mostrar_mapa"] = True
    st.success(f"✅ Rotas geradas com sucesso! Todas as escolas foram atendidas dentro da capacidade dos carros.")

if gerar:
    if not destinos_exibir:
        st.warning("Você precisa selecionar ao menos um destino.")
    else:
        gerar_rotas_com_sequencial(partida_exibir, destinos_exibir, num_carros, capacidade)

if st.session_state["mostrar_mapa"] and st.session_state["mapa_html_path"] is not None:
    with open(st.session_state["mapa_html_path"], 'r', encoding='utf-8') as f:
        mapa_html = f.read()
    components.html(mapa_html, height=600, scrolling=True)
else:
    map_placeholder.write("O mapa aparecerá aqui após você gerar uma rota.")
