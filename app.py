import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from openrouteservice import Client
from sklearn.cluster import KMeans
from math import radians, cos, sin, sqrt, atan2

# CONFIGURAÇÕES INICIAIS
st.set_page_config(page_title="🗺️ Rotas Automáticas", layout="wide")

# CHAVE DA API ORS
api_key = st.secrets["ors_api_key"]["key"]
cliente_direcoes = Client(key=api_key)

# FUNÇÃO DE DISTÂNCIA GEOGRÁFICA
def distancia_geografica(p1, p2):
    R = 6371.0
    lat1, lon1 = radians(p1[0]), radians(p1[1])
    lat2, lon2 = radians(p2[0]), radians(p2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))

# INTERFACE
st.title("📍 Roteirização Otimizada de Escolas")

arquivo = st.file_uploader("Faça upload da planilha com as escolas", type=["csv", "xlsx"])
num_carros = st.number_input("Número de carros", min_value=1, step=1, value=2)
capacidade_por_carro = st.text_input("Capacidade dos carros (separado por vírgulas)", value="10,10")

if arquivo:
    # LEITURA DOS DADOS
    if arquivo.name.endswith(".csv"):
        df = pd.read_csv(arquivo)
    else:
        df = pd.read_excel(arquivo)

    df.columns = df.columns.str.lower().str.strip()
    obrigatorias = {"nome", "lat", "lng", "qtd_pessoas"}
    if not obrigatorias.issubset(df.columns):
        st.error(f"A planilha deve conter as colunas: {', '.join(obrigatorias)}")
        st.stop()

    capacidade = list(map(int, capacidade_por_carro.split(",")))
    if len(capacidade) != num_carros:
        st.error("Número de capacidades deve ser igual ao número de carros")
        st.stop()

    df = df.copy()
    df["lat"] = df["lat"].astype(float)
    df["lng"] = df["lng"].astype(float)
    df["qtd_pessoas"] = df["qtd_pessoas"].astype(int)

    # PONTO CENTRAL (INÍCIO DAS ROTAS)
    centro_lat = df["lat"].mean()
    centro_lng = df["lng"].mean()
    ponto_inicial = (centro_lat, centro_lng)

    # ESCOLAS MAIS DISTANTES PARA O CARRO 1
    df["distancia"] = df[["lat", "lng"]].apply(lambda row: distancia_geografica(ponto_inicial, (row["lat"], row["lng"])), axis=1)
    df = df.sort_values(by="distancia", ascending=False)

    # ATRIBUI ESCOLAS AO CARRO 1 (PRIORIDADE PARA MAIS DISTANTES)
    rotas_por_carro = {i: [] for i in range(num_carros)}
    restantes = df.copy()
    capacidade_restante = capacidade.copy()

    for idx, row in df.iterrows():
        if capacidade_restante[0] >= row["qtd_pessoas"]:
            rotas_por_carro[0].append(row)
            capacidade_restante[0] -= row["qtd_pessoas"]
            restantes = restantes.drop(idx)

    # DISTRIBUI ESCOLAS RESTANTES ENTRE OS OUTROS CARROS
    for idx, row in restantes.iterrows():
        alocado = False
        for i in range(1, num_carros):
            if capacidade_restante[i] >= row["qtd_pessoas"]:
                rotas_por_carro[i].append(row)
                capacidade_restante[i] -= row["qtd_pessoas"]
                alocado = True
                break
        if not alocado:
            st.warning(f"Não foi possível alocar a escola: {row['nome']}")

    # CRIA O MAPA
    m = folium.Map(location=[centro_lat, centro_lng], zoom_start=12, control_scale=True, tiles=None)
    folium.TileLayer('cartodbpositron', name="Mapa Padrão").add_to(m)
    folium.TileLayer('https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                     name='Satélite (Google)',
                     attr='Google', overlay=False, control=True).add_to(m)

    # CORES PARA OS CARROS
    cores = ["red", "blue", "green", "purple", "orange", "darkred", "lightblue"]

    # ADICIONA ROTA E PONTOS NO MAPA
    for carro_id, escolas in rotas_por_carro.items():
        if not escolas:
            continue

        rota_df = pd.DataFrame(escolas)
        coords = [(row["lng"], row["lat"]) for _, row in rota_df.iterrows()]

        try:
            rota = cliente_direcoes.directions(
                coordinates=coords,
                profile='driving-car',
                format='geojson',
                optimize_waypoints=True
            )

            way_points_order = rota['features'][0]['properties'].get('way_points', list(range(len(rota_df))))

            for step_num, idx in enumerate(way_points_order):
                if idx >= len(rota_df):
                    continue
                row = rota_df.iloc[idx]
                folium.Marker(
                    location=[row["lat"], row["lng"]],
                    popup=f"{row['nome']} ({row['qtd_pessoas']} pessoas)",
                    icon=folium.Icon(color=cores[carro_id % len(cores)], icon="graduation-cap", prefix="fa")
                ).add_to(m)

            folium.GeoJson(
                rota,
                name=f"Rota Carro {carro_id + 1}",
                style_function=lambda x, cid=carro_id: {
                    "color": cores[cid % len(cores)],
                    "weight": 5,
                    "opacity": 0.8
                }
            ).add_to(m)

        except Exception as e:
            st.error(f"Erro ao solicitar rota para Carro {carro_id + 1}: {e}")

    folium.LayerControl().add_to(m)
    st_folium(m, width=1200, height=700)
