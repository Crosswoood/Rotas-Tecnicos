import streamlit as st
import pandas as pd
import folium
from geopy.distance import geodesic
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from folium.features import DivIcon
import tempfile
import os
import streamlit.components.v1 as components

st.set_page_config(page_title="Rotas Automáticas")

@st.cache_data
def carregar_escolas(caminho_csv):
    df = pd.read_csv(caminho_csv, encoding="latin1", sep=";")
    df.columns = df.columns.str.strip().str.lower()
    df["latitude"] = df["latitude"].astype(str).str.replace(",", ".").astype(float)
    df["longitude"] = df["longitude"].astype(str).str.replace(",", ".").astype(float)
    df["exibir"] = df["codigo"].astype(str) + " - " + df["nome"]
    return df

@st.cache_data
def create_distance_matrix(locations):
    n = len(locations)
    matrix = []
    for i in range(n):
        row = []
        for j in range(n):
            dist = int(geodesic(locations[i], locations[j]).meters) if i != j else 0
            row.append(dist)
        matrix.append(row)
    return matrix

if "mostrar_mapa" not in st.session_state:
    st.session_state["mostrar_mapa"] = False
if "mapa_html_path" not in st.session_state:
    st.session_state["mapa_html_path"] = None

# Carregar dados
escolas_df = carregar_escolas("ESCOLAS-CAPITAL.csv")

st.title("📍 Rotas Automáticas")

map_placeholder = st.empty()

with st.form("roteirizador"):
    partida_exibir = st.selectbox("📍 Escolha o ponto de partida", escolas_df["exibir"].tolist())
    destinos_exibir = st.multiselect("🌟 Escolas de destino", escolas_df["exibir"].tolist())
    num_carros = st.number_input("🚘 Número de carros disponíveis", min_value=1, max_value=10, value=1)
    capacidade = st.number_input("👥 Pessoas por carro (incluindo motorista)", min_value=1, max_value=10, value=4)
    gerar = st.form_submit_button("🔄 Gerar rota")

def gerar_rotas(partida_exibir, destinos_exibir, num_carros, capacidade):
    partida_codigo = int(partida_exibir.split(" - ")[0])
    destinos_codigos = [int(item.split(" - ")[0]) for item in destinos_exibir]

    if partida_codigo not in destinos_codigos:
        destinos_codigos.insert(0, partida_codigo)

    destinos_df = escolas_df[escolas_df["codigo"].isin(destinos_codigos)].reset_index(drop=True)
    locations = list(zip(destinos_df["latitude"], destinos_df["longitude"]))
    distance_matrix = create_distance_matrix(tuple(locations))

    # === Adiciona ponto virtual de fim ===
    dummy_point = (0.0, 0.0)  # Não será usado realmente
    all_locations = locations + [dummy_point]

    starts = [0] * num_carros
    ends = [len(locations)] * num_carros  # ponto fictício
    manager = pywrapcp.RoutingIndexManager(len(all_locations), num_carros, starts, ends)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        if from_node >= len(distance_matrix) or to_node >= len(distance_matrix):
            return 0
        return distance_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    demands = [1] * len(locations) + [0]
    vehicle_capacities = [capacidade] * num_carros

    demand_callback_index = routing.RegisterUnaryTransitCallback(lambda idx: demands[manager.IndexToNode(idx)])
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index, 0, vehicle_capacities, True, "Capacity"
    )

    for i in range(num_carros):
        routing.AddVariableMinimizedByFinalizer(routing.NextVar(manager.End(i)))

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC

    solution = routing.SolveWithParameters(search_parameters)

    if not solution:
        st.error("❌ O OR-Tools não conseguiu encontrar uma solução viável para os parâmetros fornecidos.")
        st.session_state["mostrar_mapa"] = False
        st.stop()

    mapa = folium.Map(location=locations[0], zoom_start=13)
    cores = ["red", "blue", "green", "purple", "orange", "darkred", "cadetblue", "darkgreen", "orange", "black"]

    for vehicle_id in range(num_carros):
        index = routing.Start(vehicle_id)
        rota = []
        ordem_pontos = []
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            if node_index < len(locations):  # ignora ponto virtual
                rota.append(locations[node_index])
                ordem_pontos.append(node_index)
            index = solution.Value(routing.NextVar(index))

        folium.PolyLine(rota, color=cores[vehicle_id % len(cores)], weight=5, opacity=0.8).add_to(mapa)

        for i, idx in enumerate(ordem_pontos):
            coord = locations[idx]
            nome_escola = destinos_df.iloc[idx]["nome"]
            numero_ponto = i
            folium.Marker(
                location=coord,
                icon=DivIcon(
                    icon_size=(30, 30),
                    icon_anchor=(15, 15),
                    html=f'<div style="font-size: 16pt; color: black; font-weight: bold; background: white; border-radius: 50%; width: 30px; height: 30px; text-align: center; line-height: 30px;">{numero_ponto}</div>'
                ),
                tooltip=f"Carro {vehicle_id+1} - {nome_escola}"
            ).add_to(mapa)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".html", dir=".") as tmpfile:
        mapa.save(tmpfile.name)
        st.session_state["mapa_html_path"] = tmpfile.name

    st.session_state["mostrar_mapa"] = True
    st.success("✅ Rota gerada com sucesso! Veja abaixo o mapa interativo.")

if gerar:
    if not destinos_exibir:
        st.warning("Você precisa selecionar ao menos um destino.")
    else:
        gerar_rotas(partida_exibir, destinos_exibir, num_carros, capacidade)

if st.session_state["mostrar_mapa"] and st.session_state["mapa_html_path"] is not None:
    with open(st.session_state["mapa_html_path"], 'r', encoding='utf-8') as f:
        mapa_html = f.read()
    components.html(mapa_html, height=600, scrolling=True)
else:
    map_placeholder.write("Mapa será exibido aqui após gerar a rota.")
