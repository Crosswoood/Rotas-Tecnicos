import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from openrouteservice import Client, convert
from sklearn.cluster import KMeans
from math import radians, cos, sin, sqrt, atan2

# Configuração da página
st.set_page_config(layout="wide", page_title="🗺️ Rotas Automáticas")

# Carregar chave da API do secrets
API_KEY = st.secrets["ors_api_key"]["key"]
client = Client(key=API_KEY)

# Capacidade dos carros
capacidade_carros = {
    "Carro 1": st.number_input("Capacidade do Carro 1", min_value=1, value=15),
    "Carro 2": st.number_input("Capacidade do Carro 2", min_value=1, value=15)
}

# Upload da planilha
st.header("📊 Carregamento dos Dados de Escolas")
uploaded_file = st.file_uploader("Envie a planilha 'ESCOLAS-CAPITAL'", type=["csv", "xlsx"])
if not uploaded_file:
    st.stop()

# Leitura da planilha
if uploaded_file.name.endswith('.csv'):
    df = pd.read_csv(uploaded_file)
else:
    df = pd.read_excel(uploaded_file)

df.columns = df.columns.str.lower()
df = df.rename(columns={"codigo": "codigo", "nome": "nome", "longitude": "lon", "latitude": "lat"})

# Coordenadas da base (ponto de partida e retorno)
lat_base = st.number_input("Latitude da Base", value=-3.118)
lon_base = st.number_input("Longitude da Base", value=-60.021)

# Função para calcular distância
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))

# Ordenar por distância da base
df["dist_base"] = df.apply(lambda row: haversine(lat_base, lon_base, row.lat, row.lon), axis=1)
df = df.sort_values("dist_base", ascending=False).reset_index(drop=True)

# Alocação baseada em capacidade
cap1 = capacidade_carros["Carro 1"]
cap2 = capacidade_carros["Carro 2"]
total = cap1 + cap2

n_escolas = len(df)
escolas_carro1 = df.iloc[:round(n_escolas * cap1 / total)].copy()
escolas_carro2 = df.iloc[round(n_escolas * cap1 / total):].copy()

# Função para solicitar rota ao ORS
def obter_rota(coordenadas):
    try:
        route = client.directions(
            coordinates=coordenadas,
            profile='driving-car',
            format='geojson',
            optimize_waypoints=True
        )
        return route
    except Exception as e:
        st.error(f"Erro ao solicitar rota: {e}")
        return None

# Criar mapa com imagem satélite
m = folium.Map(location=[lat_base, lon_base], zoom_start=12, tiles='https://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
               attr='Google Satellite', subdomains=['mt0', 'mt1', 'mt2', 'mt3'])

cores = {"Carro 1": "blue", "Carro 2": "green"}

for i, (nome_carro, escolas) in enumerate(zip(["Carro 1", "Carro 2"], [escolas_carro1, escolas_carro2])):
    coordenadas = [[lon_base, lat_base]] + escolas[["lon", "lat"]].values.tolist() + [[lon_base, lat_base]]
    coordenadas_latlon = [[c[1], c[0]] for c in coordenadas]

    rota = obter_rota(coordenadas)

    if rota:
        coords_rota = [(coord[1], coord[0]) for coord in convert.decode_polyline(rota['features'][0]['geometry'])['coordinates']]
        folium.PolyLine(coords_rota, color=cores[nome_carro], weight=5, opacity=0.8, tooltip=nome_carro).add_to(m)

        for _, row in escolas.iterrows():
            folium.Marker([row.lat, row.lon], tooltip=row.nome,
                          icon=folium.Icon(color=cores[nome_carro], icon="school", prefix="fa")).add_to(m)

# Adiciona base
folium.Marker([lat_base, lon_base], tooltip="Base", icon=folium.Icon(color="red", icon="home", prefix="fa")).add_to(m)

# Exibe mapa
st_folium(m, width=1200, height=700)
