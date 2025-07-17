import streamlit as st
import pandas as pd
import folium
import openrouteservice
from folium.features import DivIcon
from sklearn.cluster import KMeans
import tempfile
import streamlit.components.v1 as components

st.set_page_config(page_title="🗺️ Rotas Automáticas")

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

    tipos_de_veiculos = st.number_input("🚘 Quantos tipos de veículos deseja usar?", min_value=1, max_value=10, value=1)

    veiculos = []
    for i in range(tipos_de_veiculos):
        with st.expander(f"🚗 Configurar Veículo {i + 1}"):
            tipo = st.text_input(f"Tipo do Veículo {i + 1}", value=f"Veículo {i + 1}")
            qtd = st.number_input(f"Quantidade de '{tipo}'", min_value=1, max_value=10, value=1, key=f"qtd_{i}")
            capacidade = st.number_input(f"👥 Capacidade (incluindo motorista)", min_value=2, max_value=20, value=4, key=f"cap_{i}")
            veiculos.append({
                "tipo": tipo,
                "quantidade": qtd,
                "capacidade": capacidade - 1
            })

    gerar = st.form_submit_button("🔄 Gerar rota")

def clusterizar_por_capacidades(destinos_df, veiculos):
    if destinos_df.empty:
        return []

    total_slots = sum(v["quantidade"] * v["capacidade"] for v in veiculos)
    if total_slots < len(destinos_df):
        st.warning(f"⚠️ A capacidade total de transporte ({total_slots}) é menor que o número de destinos ({len(destinos_df)}). Alguns destinos ficarão de fora.")

    grupos_finais = []
    total_carros = sum(v["quantidade"] for v in veiculos)
    kmeans = KMeans(n_clusters=min(total_carros, len(destinos_df)), random_state=1000, n_init=1000)
    destinos_df["cluster"] = kmeans.fit_predict(destinos_df[["latitude", "longitude"]])

    grupos_por_cluster = []
    for _, grupo in destinos_df.groupby("cluster"):
        grupo = grupo.reset_index(drop=True)
        grupos_por_cluster.append(grupo)

    veiculos_expandido = []
    for v in veiculos:
        veiculos_expandido.extend([v] * v["quantidade"])

    idx_veiculo = 0
    for grupo in grupos_por_cluster:
        for i in range(0, len(grupo), veiculos_expandido[idx_veiculo]["capacidade"]):
            parte = grupo.iloc[i:i + veiculos_expandido[idx_veiculo]["capacidade"]]
            grupos_finais.append((parte, veiculos_expandido[idx_veiculo]))
            idx_veiculo = (idx_veiculo + 1) % len(veiculos_expandido)

    return grupos_finais

def gerar_rotas_com_veiculos(partida_exibir, destinos_exibir, veiculos):
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

    grupos = clusterizar_por_capacidades(destinos_df, veiculos)

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

    for i, (grupo, veiculo) in enumerate(grupos):
        if grupo.empty:
            continue

        rota_df = pd.concat([pd.DataFrame([partida]), grupo], ignore_index=True)
        coordenadas = list(zip(rota_df["longitude"], rota_df["latitude"]))

        try:
            if len(coordenadas) >= 4:
                rota = client.directions(
                    coordenadas,
                    profile='driving-car',
                    format='geojson',
                    optimize_waypoints=True
                )
            else:
                rota = client.directions(
                    coordenadas,
                    profile='driving-car',
                    format='geojson'
                )
        except Exception as e:
            st.error(f"Erro ao solicitar rota para {veiculo['tipo']} {i+1}: {e}")
            continue

        folium.GeoJson(
            rota,
            name=f"Rota {veiculo['tipo']} {i+1}",
            style_function=lambda x, cor=cores[i % len(cores)]: {
                "color": cor, "weight": 5, "opacity": 0.7
            }
        ).add_to(mapa)

try:
    way_points_order = rota['features'][0]['properties'].get('way_points', list(range(len(rota_df))))
except Exception:
    way_points_order = list(range(len(rota_df)))

for step_num, idx in enumerate(way_points_order):
    if idx >= len(rota_df):
        continue  # Evita índice fora do intervalo
    row = rota_df.iloc[idx]

    folium.Marker(
        location=(row["latitude"], row["longitude"]),
        icon=DivIcon(
            icon_size=(30, 30),
            icon_anchor=(15, 15),
            html=f'<div style="font-size: 14pt; color: {cores[i % len(cores)]}; font-weight: bold; background: white; border-radius: 50%; width: 30px; height: 30px; text-align: center; line-height: 30px;">{step_num}</div>'
        ),
        tooltip=f"{veiculo['tipo']} {i+1} - {row['nome']}"
    ).add_to(mapa)


    folium.LayerControl().add_to(mapa)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".html", dir=".") as tmpfile:
        mapa.save(tmpfile.name)
        st.session_state["mapa_html_path"] = tmpfile.name

    st.session_state["mostrar_mapa"] = True
    st.success("✅ Rotas otimizadas geradas com sucesso!")

if gerar:
    if not destinos_exibir:
        st.warning("Você precisa selecionar ao menos um destino.")
    else:
        gerar_rotas_com_veiculos(partida_exibir, destinos_exibir, veiculos)

if st.session_state["mostrar_mapa"] and st.session_state["mapa_html_path"] is not None:
    with open(st.session_state["mapa_html_path"], 'r', encoding='utf-8') as f:
        mapa_html = f.read()
    components.html(mapa_html, height=600, scrolling=True)
else:
    map_placeholder.write("O mapa aparecerá aqui após você gerar uma rota.")
