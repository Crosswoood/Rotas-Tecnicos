import streamlit as st
import pandas as pd
import folium
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from streamlit_folium import st_folium
from geopy.distance import geodesic

# === Carregar dados das escolas ===
escolas_df = pd.read_csv("escolas_com_coords.csv")

# === Interface ===
st.title("🚗 Roteirizador Automático de Técnicos")

partida_nome = st.selectbox("📍 Escolha o ponto de partida", escolas_df["nome"].tolist())
destinos_nome = st.multiselect("🎯 Escolas de destino", escolas_df["nome"].tolist())

num_carros = st.number_input("🚐 Número de carros disponíveis", min_value=1, max_value=5, value=1)
capacidade = st.number_input("👥 Pessoas por carro", min_value=1, max_value=10, value=4)

if st.button("🔄 Gerar rota"):
    # === Preparar os dados ===
    if partida_nome not in destinos_nome:
        destinos_nome.insert(0, partida_nome)

    destinos_df = escolas_df[escolas_df["nome"].isin(destinos_nome)].reset_index(drop=True)
    locations = list(zip(destinos_df["latitude"], destinos_df["longitude"]))

    # === Matriz de distância geográfica ===
    def create_distance_matrix(locations):
        n = len(locations)
        matrix = []
        for from_idx in range(n):
            row = []
            for to_idx in range(n):
                if from_idx == to_idx:
                    row.append(0)
                else:
                    row.append(int(geodesic(locations[from_idx], locations[to_idx]).meters))
            matrix.append(row)
        return matrix

    distance_matrix = create_distance_matrix(locations)

    # === OR-Tools Routing ===
    manager = pywrapcp.RoutingIndexManager(len(distance_matrix), num_carros, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Adicionar capacidade
    demands = [1] * len(distance_matrix)
    vehicle_capacities = [capacidade] * num_carros
    demand_callback_index = routing.RegisterUnaryTransitCallback(lambda idx: demands[manager.IndexToNode(idx)])
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0, vehicle_capacities, True, "Capacity"
    )

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)

    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        st.success("✅ Rota gerada com sucesso!")

        # === Mostrar no mapa ===
        mapa = folium.Map(location=locations[0], zoom_start=13)
        cores = ["red", "blue", "green", "purple", "orange"]

        for vehicle_id in range(num_carros):
            index = routing.Start(vehicle_id)
            rota = []
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                coord = locations[node_index]
                rota.append(coord)
                index = solution.Value(routing.NextVar(index))
            rota.append(locations[0])  # retorna ao início (opcional)

            folium.PolyLine(rota, color=cores[vehicle_id % len(cores)], weight=5, opacity=0.8).add_to(mapa)

            for i, coord in enumerate(rota):
                folium.Marker(coord, tooltip=f"Carro {vehicle_id+1} - Ponto {i+1}").add_to(mapa)

        st_folium(mapa, height=600)

    else:
        st.error("❌ Não foi possível encontrar uma rota.")

