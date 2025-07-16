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

colunas_esperadas = ["inep", "escola", "latitude", "longitude"]
faltando = [col for col in colunas_esperadas if col not in escolas_df.columns]

if faltando:
    st.error(f"⚠️ Colunas ausentes no CSV: {faltando}")
    st.stop()

# Renomear para padronizar internamente
escolas_df = escolas_df.rename(columns={
    "inep": "codigo",
    "escola": "nome"
})

# Corrigir vírgulas decimais e converter para float
escolas_df["latitude"] = escolas_df["latitude"].astype(str).str.replace(",", ".").astype(float)
escolas_df["longitude"] = escolas_df["longitude"].astype(str).str.replace(",", ".").astype(float)

# Criar coluna auxiliar para exibição
escolas_df["exibir"] = escolas_df["codigo"].astype(str) + " - " + escolas_df["nome"]

st.title("🚗 Roteirizador Automático de Técnicos")

# Interface
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
        destinos_codigos = [int(item.split(" - ")[0]) for item
