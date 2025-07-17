import streamlit as st
import pandas as pd
import folium
import openrouteservice
from folium.features import DivIcon
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

def gerar_rotas_com_optimization_api(partida_exibir, destinos_exibir, num_carros, capacidade):
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

    # Configura veículos
    vehicles = []
    for i in range(num_carros):
        vehicles.append({
            "id": i + 1,
            "profile": "driving-car",
            "start": [partida["longitude"], partida["latitude"]],
            "end": [partida["longitude"], partida["latitude"]],
            "capacity": [capacidade - 1]  # Motorista ocupa 1 lugar
        })

    # Configura jobs (destinos)
    jobs = []
    for idx, row in destinos_df.iterrows():
        jobs.append({
            "id": int(row["codigo"]),
            "location": [row["longitude"], row["latitude"]],
            "service": 300,  # tempo de parada (opcional)
            "amount": [1]    # ocupa 1 unidade de capacidade
        })

    try:
        result = client.optimization(
            jobs=jobs,
            vehicles=vehicles
        )
    except Exception as e:
        st.error(f"Erro na otimização: {e}")
        return

    # Cria mapa
    mapa = folium.Map(location=[partida["latitude"], partida["longitude"]], zoom_start=13)

    # Camada de satélite
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

    for i, route in enumerate(result["routes"]):
        steps = route["steps"]

        coords = []
        nomes = []
        for step in steps:
            if step["type"] == "start":
                coords.append(vehicles[i]["start"])
                nomes.append("Partida")
            elif step["type"] == "job":
                job_id = step["id"]
                job = next(j for j in jobs if j["id"] == job_id)
                coords.append(job["location"])
                nome_escola = escolas_df[escolas_df["codigo"] == job_id]["nome"].values[0]
                nomes.append(nome_escola)
            elif step["type"] == "end":
                coords.append(vehicles[i]["end"])
                nomes.append("Retorno")

        # Solicita direções para cada rota individual para ter a geometria
        try:
            rota_geojson = client.directions(
                coords,
                profile="driving-car",
                format="geojson"
            )
        except Exception as e:
            st.error(f"Erro ao obter rota detalhada para Carro {i+1}: {e}")
            continue

        folium.GeoJson(
            rota_geojson,
            name=f"Rota Carro {i+1}",
            style_function=lambda x, cor=cores[i % len(cores)]: {
                "color": cor, "weight": 5, "opacity": 0.7
            }
        ).add_to(mapa)

        for idx, coord in enumerate(coords):
            folium.Marker(
                location=(coord[1], coord[0]),
                icon=DivIcon(
                    icon_size=(30, 30),
                    icon_anchor=(15, 15),
                    html=f'<div style="font-size: 14pt; color: {cores[i % len(cores)]}; font-weight: bold; background: white; border-radius: 50%; width: 30px; height: 30px; text-align: center; line-height: 30px;">{idx}</div>'
                ),
                tooltip=f"Carro {i+1} - {nomes[idx]}"
            ).add_to(mapa)

    folium.LayerControl().add_to(mapa)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".html", dir=".") as tmpfile:
        mapa.save(tmpfile.name)
        st.session_state["mapa_html_path"] = tmpfile.name

    st.session_state["mostrar_mapa"] = True
    st.success(f"✅ Rotas otimizadas geradas com a Vehicle Optimization API!")

if gerar:
    if not destinos_exibir:
        st.warning("Você precisa selecionar ao menos um destino.")
    else:
        gerar_rotas_com_optimization_api(partida_exibir, destinos_exibir, num_carros, capacidade)

if st.session_state["mostrar_mapa"] and st.session_state["mapa_html_path"] is not None:
    with open(st.session_state["mapa_html_path"], 'r', encoding='utf-8') as f:
        mapa_html = f.read()
    components.html(mapa_html, height=600, scrolling=True)
else:
    map_placeholder.write("O mapa aparecerá aqui após você gerar uma rota.")
