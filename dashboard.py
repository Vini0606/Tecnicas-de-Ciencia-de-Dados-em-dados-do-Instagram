import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os

# Adiciona o diretório raiz do projeto ao sys.path
project_root = os.path.abspath(os.path.join(os.getcwd(), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from config import settings

st.set_page_config(layout="wide")

st.title("Modelagem Hibrida de Comentários do Instagram dos Governadores do Brasil")

df_profiles = pd.read_excel(settings.ALL_XLSX, sheet_name="profiles")
df_comments = pd.read_excel(settings.ALL_XLSX, sheet_name="reels_latestComments")
df_reels = pd.read_excel(settings.ALL_XLSX, sheet_name="reels")

tab1, tab2, tab3 = st.tabs(["Perfis dos Governadores", "Publicações dos Perfis", "Comentários das Publicações"])

with tab1:
    
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric(label="Média de Seguidores", value=round(df_profiles['followersCount'].mean(), 2))
    with col2:
        st.metric(label="Média de Seguidos", value=round(df_profiles['followsCount'].mean(), 2))
    with col3:
        st.metric(label="Média de Publicações", value=round(df_profiles['postsCount'].mean(), 2))
    with col4:
        st.metric(label="Média de Comentários p/ Publicação", value=round((df_profiles['commentsSum'] / df_profiles['count']).mean(), 2))
    with col5:
        st.metric(label="Média de Likes p/ Publicação", value=round((df_profiles['likesSum'] / df_profiles['count']).mean(), 2))
    with col6:
        st.metric(label="Média de % de Engajamento", value=round(df_profiles['% ENGAJAMENTO'].mean(), 2))
    
    # 1. ORDENAR O DATAFRAME ANTES (boa prática)
    # Ordenamos os dados uma única vez para garantir que ambos os gráficos usem a mesma ordem.
    df_sorted = df_profiles.sort_values(by='followersCount', ascending=False)

    # 2. CRIE A FIGURA COM EIXO Y SECUNDÁRIO
    # Isso permite que cada métrica tenha sua própria escala
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 3. ADICIONE O GRÁFICO DE BARRAS (Seguidores) no eixo principal (esquerda)
    fig.add_trace(
        go.Bar(
            x=df_sorted["fullName"], 
            y=df_sorted['followersCount'],
            name='Nº de Seguidores' # Nome para a legenda
        ),
        secondary_y=False, # Define como eixo principal
    )

    # 4. ADICIONE O GRÁFICO DE LINHA (Engajamento) no eixo secundário (direita)
    fig.add_trace(
        go.Scatter(
            x=df_sorted['fullName'],
            y=df_sorted['% ENGAJAMENTO'],
            name='% de Engajamento', # Nome para a legenda
            mode='lines+markers',
            line=dict(color='red', width=3)
        ),
        secondary_y=True, # Define como eixo secundário
    )

    # 5. PERSONALIZE O LAYOUT (Títulos e Nomes dos Eixos)
    fig.update_layout(
        title_text='Seguidores vs. Engajamento por Perfil',
        xaxis_title='Perfis'
    )

    # Adiciona título ao eixo Y da esquerda
    fig.update_yaxes(title_text="<b>Nº de Seguidores</b>", secondary_y=False)

    # Adiciona título ao eixo Y da direita
    fig.update_yaxes(title_text="<b>% Engajamento</b>", secondary_y=True)

    # 6. EXIBA O GRÁFICO NO STREAMLIT
    st.plotly_chart(fig, use_container_width=True)

    # 1. ORDENAR O DATAFRAME ANTES (boa prática)
    # Ordenamos os dados uma única vez para garantir que ambos os gráficos usem a mesma ordem.
    df_sorted = df_profiles.sort_values(by='followsCount', ascending=False)

    # 2. CRIE A FIGURA COM EIXO Y SECUNDÁRIO
    # Isso permite que cada métrica tenha sua própria escala
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 3. ADICIONE O GRÁFICO DE BARRAS (Seguidores) no eixo principal (esquerda)
    fig.add_trace(
        go.Bar(
            x=df_sorted["fullName"], 
            y=df_sorted['followsCount'],
            name='Nº de Seguidos' # Nome para a legenda
        ),
        secondary_y=False, # Define como eixo principal
    )

    # 4. ADICIONE O GRÁFICO DE LINHA (Engajamento) no eixo secundário (direita)
    fig.add_trace(
        go.Scatter(
            x=df_sorted['fullName'],
            y=df_sorted['% ENGAJAMENTO'],
            name='% de Engajamento', # Nome para a legenda
            mode='lines+markers',
            line=dict(color='red', width=3)
        ),
        secondary_y=True, # Define como eixo secundário
    )

    # 5. PERSONALIZE O LAYOUT (Títulos e Nomes dos Eixos)
    fig.update_layout(
        title_text='Seguidos vs. Engajamento por Perfil',
        xaxis_title='Perfis'
    )

    # Adiciona título ao eixo Y da esquerda
    fig.update_yaxes(title_text="<b>Nº de Seguidos</b>", secondary_y=False)

    # Adiciona título ao eixo Y da direita
    fig.update_yaxes(title_text="<b>% Engajamento</b>", secondary_y=True)

    # 6. EXIBA O GRÁFICO NO STREAMLIT
    st.plotly_chart(fig, use_container_width=True)

    # 1. ORDENAR O DATAFRAME ANTES (boa prática)
    # Ordenamos os dados uma única vez para garantir que ambos os gráficos usem a mesma ordem.
    df_sorted = df_profiles.sort_values(by='postsCount', ascending=False)

    # 2. CRIE A FIGURA COM EIXO Y SECUNDÁRIO
    # Isso permite que cada métrica tenha sua própria escala
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 3. ADICIONE O GRÁFICO DE BARRAS (Seguidores) no eixo principal (esquerda)
    fig.add_trace(
        go.Bar(
            x=df_sorted["fullName"], 
            y=df_sorted['postsCount'],
            name='Nº de Posts' # Nome para a legenda
        ),
        secondary_y=False, # Define como eixo principal
    )

    # 4. ADICIONE O GRÁFICO DE LINHA (Engajamento) no eixo secundário (direita)
    fig.add_trace(
        go.Scatter(
            x=df_sorted['fullName'],
            y=df_sorted['% ENGAJAMENTO'],
            name='% de Engajamento', # Nome para a legenda
            mode='lines+markers',
            line=dict(color='red', width=3)
        ),
        secondary_y=True, # Define como eixo secundário
    )

    # 5. PERSONALIZE O LAYOUT (Títulos e Nomes dos Eixos)
    fig.update_layout(
        title_text='Posts vs. Engajamento por Perfil',
        xaxis_title='Perfis'
    )

    # Adiciona título ao eixo Y da esquerda
    fig.update_yaxes(title_text="<b>Nº de Posts</b>", secondary_y=False)

    # Adiciona título ao eixo Y da direita
    fig.update_yaxes(title_text="<b>% Engajamento</b>", secondary_y=True)

    # 6. EXIBA O GRÁFICO NO STREAMLIT
    st.plotly_chart(fig, use_container_width=True)

    col1_bar, col2_bar, col3_bar = st.columns(3)
    
    with col1_bar:
    
        df_sorted = df_profiles.sort_values(by='RECENCIA', ascending=True).tail(5)
        
        fig1 = px.bar(df_sorted, 
                y='fullName', 
                x="RECENCIA",
                orientation='h', 
                title="Perfil vs. Soma de Likes",
                labels={'Produto': 'Nome do Produto', 'Vendas': 'Unidades Vendidas'}, # Renomeia os eixos
                text_auto=True
                )
        
        st.plotly_chart(fig1, use_container_width=True)
    
    with col2_bar:
    
        df_sorted = df_profiles.sort_values(by='FREQUENCIA', ascending=True).tail(5)
        
        fig2 = px.bar(df_sorted, 
                y='fullName', 
                x="FREQUENCIA",
                orientation='h', 
                title="Perfil vs. Soma de Likes",
                labels={'Produto': 'Nome do Produto', 'Vendas': 'Unidades Vendidas'}, # Renomeia os eixos
                text_auto=True # Adiciona o valor no topo de cada barra
                )
        
        st.plotly_chart(fig2, use_container_width=True)

    with col3_bar:

        df_sorted = df_profiles.sort_values(by="% ENGAJAMENTO", ascending=True).tail(5)
    
        fig3 = px.bar(df_sorted, 
                y='fullName', 
                x="% ENGAJAMENTO",
                orientation='h', 
                title="Perfil vs. Soma de Likes",
                labels={'Produto': 'Nome do Produto', 'Vendas': 'Unidades Vendidas'}, # Renomeia os eixos
                text_auto=True # Adiciona o valor no topo de cada barra
                )
        
        st.plotly_chart(fig3, use_container_width=True)
    
    col1_bar_likes, col2_bar_likes = st.columns(2)

    with col1_bar_likes:
    
        df_sorted = df_profiles.sort_values(by='likesSum', ascending=True).tail(5)
        
        fig1 = px.bar(df_sorted, 
                y='fullName', 
                x="likesSum",
                orientation='h', 
                title="Perfil vs. Soma de Likes",
                labels={'Produto': 'Nome do Produto', 'Vendas': 'Unidades Vendidas'}, # Renomeia os eixos
                text_auto=True
                )
        
        st.plotly_chart(fig1, use_container_width=True)
    
    with col2_bar_likes:
    
        df_sorted = df_profiles.sort_values(by='commentsSum', ascending=True).tail(5)
        
        fig2 = px.bar(df_sorted, 
                y='fullName', 
                x="commentsSum",
                orientation='h', 
                title="Perfil vs. Soma de Likes",
                labels={'Produto': 'Nome do Produto', 'Vendas': 'Unidades Vendidas'}, # Renomeia os eixos
                text_auto=True # Adiciona o valor no topo de cada barra
                )
        
        st.plotly_chart(fig2, use_container_width=True)


