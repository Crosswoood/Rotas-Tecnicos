import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.distance import geodesic
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from folium.features import DivIcon

# Leitura do CSV com encoding e separador corretos
try:
    escolas_df = pd.read_csv("ESCOLAS-CAPITAL.csv", encoding="utf-8", sep=';')
except UnicodeDecodeError:
    escolas_df = pd.read_csv("ESCOLAS-CAPITAL.csv", encoding="latin1", sep=';')

escolas_df.columns = escolas_df.columns.str.strip().str.lower()

st.write("🔎 Colunas detectadas no CSV:", escolas_df.columns.tolist())

colunas_esperadas = ["cod_escola", "escola", "latitude", "longitude"]
faltando = [col for col in colunas_esperadas if col not in escolas_df.columns]

if faltando:
    st.error(f"⚠️ Colunas ausentes no CSV: {faltando}")
    st.stop()

escolas_df = escolas_df.rename(columns={
    "cod_escola": "codigo",
    "escola": "nome"
})

# Corrigir vírgulas decimais e converter para float
escolas_df["latitude"] = escolas_df["latitude"].astype(str).str.replace(",", ".").astype(float)
escolas_df["longitude"] = escolas_df["longitude"].astype(str).str.replace(",", ".").astype(float)

escolas_df["exibir"] = escolas_df["codigo"].astype(str) + " - " + escolas_df["nome"]

st.title("🚗 Roteirizador Automático de Técnicos")

partida_exibir = st.selectbox("📍 Escolha o ponto de partida", escolas_df["exibir"].tolist())
destinos_exibir = st.multiselect("🎯 Escolas de destino", escolas_df["exibir"].tolist())

num_carros = st.number_input("🚐 Número de carros disponíveis", min_value=1, max_value=5, value=1)
capacidade = st.number_input("👥 Pessoas por carro", min_value=1, max_value=10, value=4)

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

if st.button("🔄 Gerar rota"):
    if not destinos_exibir:
        st.warning("Você precisa selecionar ao menos um destino.")
    else:
        partida_codigo = int(partida_exibir.split(" - ")[0])
        destinos_codigos = [int(item.split(" - ")[0]) for item in destinos_exibir]

        if partida_codigo not in destinos_codigos:
            destinos_codigos.insert(0, partida_codigo)

        destinos_df = escolas_df[escolas_df["codigo"].isin(destinos_codigos)].reset_index(drop=True)
        locations = list(zip(destinos_df["latitude"], destinos_df["longitude"]))

        distance_matrix = create_distance_matrix(locations)

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
            demand_callback_index,
            0, vehicle_capacities, True, "Capacity"
        )

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC

        solution = routing.SolveWithParameters(search_parameters)

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
                rota.append(locations[0])  # volta ao início

                folium.PolyLine(rota, color=cores[vehicle_id % len(cores)], weight=5, opacity=0.8).add_to(mapa)

                for i, coord in enumerate(rota):
                    nome_escola = destinos_df.iloc[i % len(destinos_df)]["nome"]
                    folium.Marker(
                        location=coord,
                        icon=DivIcon(
                            icon_size=(30,30),
                            icon_anchor=(15,15),
                            html=f'<div style="font-size: 16pt; color : black; font-weight: bold; background: white; border-radius: 50%; width: 30px; height: 30px; text-align: center; line-height: 30px;">{i}</div>'
                        ),
                        tooltip=f"Carro {vehicle_id+1} - {nome_escola}"
                    ).add_to(mapa)

            st.session_state["mapa"] = mapa
        else:
            st.error("❌ Não foi possível gerar a rota com os parâmetros fornecidos.")

if "mapa" in st.session_state:
    st_folium(st.session_state["mapa"], height=600)
