import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.distance import geodesic
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from folium.features import DivIcon

st.set_page_config(page_title="Rotas Automáticas")

@st.cache_data
def carregar_escolas(caminho_csv):
    df = pd.read_csv(caminho_csv, encoding="latin1", sep=";")
    df.columns = df.columns.str.strip().str.lower()
    df = df.rename(columns={"codigo": "codigo", "escola": "nome"})
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

# Inicializa session_state para mapa e flag de exibição
if "mostrar_mapa" not in st.session_state:
    st.session_state["mostrar_mapa"] = False
if "mapa" not in st.session_state:
    st.session_state["mapa"] = None

# Carregar dados
escolas_df = carregar_escolas("ESCOLAS-CAPITAL.csv")

st.title("🗺️ Rotas Automáticas")

with st.form("roteirizador"):
    partida_exibir = st.selectbox("📍 Escolha o ponto de partida", escolas_df["exibir"].tolist())
    destinos_exibir = st.multiselect("🎯 Escolas de destino", escolas_df["exibir"].tolist())
    num_carros = st.number_input("🚐 Número de carros disponíveis", min_value=1, max_value=5, value=1)
    capacidade = st.number_input("👥 Pessoas por carro", min_value=1, max_value=10, value=4)
    gerar = st.form_submit_button("🔄 Gerar rota")

def gerar_rotas(partida_exibir, destinos_exibir, num_carros, capacidade):
    partida_codigo = int(partida_exibir.split(" - ")[0])
    destinos_codigos = [int(item.split(" - ")[0]) for item in destinos_exibir]

    if partida_codigo not in destinos_codigos:
        destinos_codigos.insert(0, partida_codigo)

    destinos_df = escolas_df[escolas_df["codigo"].isin(destinos_codigos)].reset_index(drop=True)
    locations = list(zip(destinos_df["latitude"], destinos_df["longitude"]))

    distance_matrix = create_distance_matrix(tuple(locations))  # tupla para cache

    manager = pywrapcp.RoutingIndexManager(len(distance_matrix), num_carros, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    demands = [1] * len(distance_matrix)
    vehicle_capacities = [capacidade] * num_carros
    demand_callback_index = routing.RegisterUnaryTransitCallback(lambda idx: demands[manager.IndexToNode(idx)])
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index, 0, vehicle_capacities, True, "Capacity"
    )

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC

    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        mapa = folium.Map(location=locations[0], zoom_start=13)
        cores = ["red", "blue", "green", "purple", "orange"]

        for vehicle_id in range(num_carros):
            index = routing.Start(vehicle_id)
            rota = []
            ordem_pontos = []
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                rota.append(locations[node_index])
                ordem_pontos.append(node_index)
                index = solution.Value(routing.NextVar(index))
            rota.append(locations[0])

            folium.PolyLine(rota, color=cores[vehicle_id % len(cores)], weight=5, opacity=0.8).add_to(mapa)

            for i, idx in enumerate(ordem_pontos):
                coord = locations[idx]
                nome_escola = destinos_df.iloc[idx]["nome"]
                folium.Marker(
                    location=coord,
                    icon=DivIcon(
                        icon_size=(30, 30),
                        icon_anchor=(15, 15),
                        html=f'<div style="font-size: 16pt; color : black; font-weight: bold; background: white; border-radius: 50%; width: 30px; height: 30px; text-align: center; line-height: 30px;">{i}</div>'
                    ),
                    tooltip=f"Carro {vehicle_id+1} - {nome_escola}"
                ).add_to(mapa)

        st.session_state["mapa"] = mapa
        st.session_state["mostrar_mapa"] = True
        st.success("✅ Rota gerada com sucesso!")
    else:
        st.session_state["mostrar_mapa"] = False
        st.error("❌ Não foi possível gerar a rota com os parâmetros fornecidos.")

if gerar:
    if not destinos_exibir:
        st.warning("Você precisa selecionar ao menos um destino.")
    else:
        gerar_rotas(partida_exibir, destinos_exibir, num_carros, capacidade)

mapa_placeholder = st.empty()
if st.session_state["mostrar_mapa"] and st.session_state["mapa"] is not None:
    st_folium(st.session_state["mapa"], height=600)
else:
    mapa_placeholder.write("Mapa será exibido aqui após gerar a rota.")
