import streamlit as st
import pandas as pd
import folium
import openrouteservice
from folium.features import DivIcon
from folium.plugins import PolyLineTextPath
import tempfile
import streamlit.components.v1 as components

st.set_page_config(page_title="🗺️ Rotas Automáticas")

# Lê a chave da API do secrets com seção [ors_api_key]
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
    capacidade = st.number_input("👥 Pessoas por carro (incluindo motorista)", min_value=1, max_value=10, value=4)
    gerar = st.form_submit_button("🔄 Gerar rota")

def dividir_destinos(destinos, n):
    grupos = [[] for _ in range(n)]
    for i, destino in enumerate(destinos):
        grupos[i % n].append(destino)
    return grupos

def gerar_rotas_multicarro(partida_exibir, destinos_exibir, num_carros, capacidade):
    client = openrouteservice.Client(key=api_key)

    partida_codigo = int(partida_exibir.split(" - ")[0])
    destinos_codigos = [int(item.split(" - ")[0]) for item in destinos_exibir]

    if partida_codigo in destinos_codigos:
        destinos_codigos.remove(partida_codigo)

    if len(destinos_codigos) == 0:
        st.error("❌ Selecione ao menos um destino além do ponto de partida.")
        return

    destinos_por_carro = dividir_destinos(destinos_codigos, num_carros)

    partida_lng = escolas_df.loc[escolas_df["codigo"] == partida_codigo, "longitude"].values[0]
    partida_lat = escolas_df.loc[escolas_df["codigo"] == partida_codigo, "latitude"].values[0]
    mapa = folium.Map(location=[partida_lat, partida_lng], zoom_start=13)

    # Camada Satélite Esri
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

    for i, destinos_carro in enumerate(destinos_por_carro):
        if not destinos_carro:
            continue

        rota_codigos = [partida_codigo] + destinos_carro
        rota_df = escolas_df[escolas_df["codigo"].isin(rota_codigos)].copy().reset_index(drop=True)

        rota_df.sort_values(by="codigo", key=lambda x: x == partida_codigo, ascending=False, inplace=True)
        rota_df.reset_index(drop=True, inplace=True)

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

        linha = folium.GeoJson(
            rota,
            name=f"Rota Carro {i+1}",
            style_function=lambda x, cor=cores[i % len(cores)]: {"color": cor, "weight": 5, "opacity": 0.7}
        ).add_to(mapa)

        # Extrai coordenadas e adiciona setas
        coords = rota['features'][0]['geometry']['coordinates']
        coords_latlng = [(lat, lng) for lng, lat in coords]

        PolyLineTextPath(
            linha,
            '▶',
            repeat=True,
            spacing=40,  # espaçamento maior entre setas
            offset=6,
            attributes={
                'fill': cores[i % len(cores)],
                'font-weight': 'bold',
                'font-size': '14'
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
    st.success(f"✅ Rotas geradas com sucesso para {num_carros} carro(s)!")

if gerar:
    if not destinos_exibir:
        st.warning("Você precisa selecionar ao menos um destino.")
    else:
        gerar_rotas_multicarro(partida_exibir, destinos_exibir, num_carros, capacidade)

if st.session_state["mostrar_mapa"] and st.session_state["mapa_html_path"] is not None:
    with open(st.session_state["mapa_html_path"], 'r', encoding='utf-8') as f:
        mapa_html = f.read()
    components.html(mapa_html, height=600, scrolling=True)
else:
    map_placeholder.write("O mapa aparecerá aqui após você gerar uma rota.")
