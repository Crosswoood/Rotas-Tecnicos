import streamlit as st
import pandas as pd
import folium
import openrouteservice
from folium.features import DivIcon
from folium.plugins import PolyLineTextPath
from geopy.distance import geodesic
import tempfile
import streamlit.components.v1 as components

st.set_page_config(page_title="🗺️ Rotas Automáticas")

# Lê chave da API do secrets
api_key = st.secrets["ors_api_key"]["key"]

@st.cache_data
def carregar_escolas(caminho_csv):
    df = pd.read_csv(caminho_csv, encoding="latin1", sep=";")
    df.columns = df.columns.str.strip().str.lower()
    df["latitude"] = df["latitude"].astype(str).str.replace(",", ".").astype(float)
    df["longitude"] = df["longitude"].astype(str).str.replace(",", ".").astype(float)
    df["exibir"] = df["codigo"].astype(str) + " - " + df["nome"]
    return df

def calcular_distancia(coord1, coord2):
    return geodesic(coord1, coord2).kilometers

def distribuir_destinos_otimizado(partida, destinos_df, num_carros, capacidade):
    destinos_restantes = destinos_df.copy()
    carros_destinos = []

    for _ in range(num_carros):
        if destinos_restantes.empty:
            break

        # Calcula distância de cada destino à partida
        destinos_restantes["distancia"] = destinos_restantes.apply(
            lambda row: calcular_distancia((partida["latitude"], partida["longitude"]),
                                           (row["latitude"], row["longitude"])), axis=1
        )

        # Seleciona os mais próximos
        selecionados = destinos_restantes.nsmallest(capacidade - 1, "distancia")
        carros_destinos.append(selecionados.copy())
        destinos_restantes = destinos_restantes.drop(selecionados.index)

    return carros_destinos

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

def gerar_rotas_otimizadas(partida_exibir, destinos_exibir, num_carros, capacidade):
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

    destinos_por_carro = distribuir_destinos_otimizado(partida, destinos_df, num_carros, capacidade)

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

    for i, destinos_carro_df in enumerate(destinos_por_carro):
        if destinos_carro_df.empty:
            continue

        rota_df = pd.concat([pd.DataFrame([partida]), destinos_carro_df], ignore_index=True)
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

        coords = rota['features'][0]['geometry']['coordinates']
        coords_latlng = [(lat, lng) for lng, lat in coords]

        PolyLineTextPath(
            linha,
            '▶',
            repeat=True,
            spacing=40,  # espaçamento entre setas
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
    st.success(f"✅ Rotas otimizadas geradas com sucesso para {num_carros} carro(s)!")

if gerar:
    if not destinos_exibir:
        st.warning("Você precisa selecionar ao menos um destino.")
    else:
        gerar_rotas_otimizadas(partida_exibir, destinos_exibir, num_carros, capacidade)

if st.session_state["mostrar_mapa"] and st.session_state["mapa_html_path"] is not None:
    with open(st.session_state["mapa_html_path"], 'r', encoding='utf-8') as f:
        mapa_html = f.read()
    components.html(mapa_html, height=600, scrolling=True)
else:
    map_placeholder.write("O mapa aparecerá aqui após você gerar uma rota.")
