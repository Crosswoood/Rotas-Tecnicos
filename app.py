import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.distance import geodesic
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

# === Carregar dados das escolas ===
escolas_df = pd.read_csv("ESCOLAS-CAPITAL.csv")

# Criar coluna auxiliar para busca
escolas_df["exibir"] = escolas_df["codigo"].astype(str) + " - " + escolas_df["nome"]

# === Interface ===
st.title("🚗 Roteirizador Automático de Técnicos")

partida_exibir = st.selectbox("📍 Escolha o ponto de partida", escolas_df["exibir"].tolist())
destinos_exibir = st.multiselect("🎯 Escolas de destino", escolas_df["exibir"].tolist())

num_carros = st.number_input("🚐 Número de carros disponíveis", min_value=1, max_value=5, value=1)
capacidade = st.number_input("👥 Pessoas por carro", min_value=1, max_value=10, value=4)

if st.button("🔄 Gerar rota"):
    if not destinos_exibir:
        st.warning("Você precisa selecionar ao menos um destino.")
    else:
        # === Preparar os dados ===
        partida_codigo = int(partida_exibir.split(" - ")[0])
        destinos_codigos = [int(item.split(" - ")[0]) for item in destinos_exibir]

        if partida_codigo not in destinos_codigos:
            destinos_codigos.insert(0, partida_codigo)

        destinos_df = escolas_df[escolas_df["codigo"].isin(destinos_codigos)].reset_index(drop=True)
        locations = list(zip(destinos_df["latitude"], destinos_df["longitude"]))

        # === Criar matriz de distância ===
        def create_distance_matrix(locations):
            n = len(locations)
            matrix = []
            for i in range(n):
                row = []
                for j in range(n):
                    if i == j:
                        row.append(0)
                    else:
                        dist = int(geodesic(locations[i], locations[j]).meters)
                        row.append(dist)
                matrix.append(row)
            return matrix

        distance_matrix = create_distance_matrix(locations)

        # === Configurar OR-Tools ===
        manager = pywrapcp.RoutingIndexManager(len(distance_matrix), num_carros, 0)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return distance_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Capacidade de veículos
        demands = [1] * len(distance_matrix)
        vehicle_capacities = [capacidade] * num_carros
        demand_callback_index = routing.RegisterUnaryTransitCallback(lambda idx: demands[manager.IndexToNode(idx)])
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0, vehicle_capacities, True, "Capacity"
        )

        # Parâmetros de busca
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )

        solution = routing.SolveWithParameters(search_parameters)

        # === Exibir solução ===
        if solution:
            st.success("✅ Rota gerada com sucesso!")

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
                rota.append(locations[0])  # retorna ao início

                folium.PolyLine(rota, color=cores[vehicle_id % len(cores)], weight=5, opacity=0.8).add_to(mapa)

                for i, coord in enumerate(rota):
                    nome_escola = destinos_df.iloc[i % len(destinos_df)]["nome"]
                    folium.Marker(coord, tooltip=f"Carro {vehicle_id+1} - {nome_escola}").add_to(mapa)

            st_folium(mapa, height=600)

        else:
            st.error("❌ Não foi possível encontrar uma rota com os parâmetros informados.")
