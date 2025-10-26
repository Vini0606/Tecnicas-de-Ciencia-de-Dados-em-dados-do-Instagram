import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
import numpy as np

# Adiciona o diretório raiz do projeto ao sys.path
project_root = os.path.abspath(os.path.join(os.getcwd(), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from config import settings

st.set_page_config(layout="wide")

dtype = {
    'inputUrl': 'str',
    'id': 'str',  # IDs são melhor tratados como texto
    'username': 'str',
    'url': 'str',
    'fullName': 'str',
    'biography': 'str',
    'externalUrls': 'str', # Provavelmente JSON, ler como texto primeiro
    'externalUrl': 'str',
    'externalUrlShimmed': 'str',
    'followersCount': 'int32',  # int32 economiza memória
    'followsCount': 'int32',
    'hasChannel': 'bool',
    'highlightReelCount': 'int32',
    'isBusinessAccount': 'bool',
    'joinedRecently': 'bool',
    'businessCategoryName': 'category',  # 'category' é ideal para textos repetidos
    'private': 'bool',
    'verified': 'bool',
    'profilePicUrl': 'str',
    'profilePicUrlHD': 'str',
    'igtvVideoCount': 'int32',
    'relatedProfiles': 'str', # Provavelmente JSON, ler como texto primeiro
    'latestIgtvVideos': 'str',
    'latestPosts': 'str',
    'postsCount': 'int32',
    'fbid': 'str',  # IDs são melhor tratados como texto
    'businessAddress': 'str'
}
df_profiles = pd.read_excel(settings.ALL_XLSX, sheet_name="profiles", dtype=dtype)
df_comments = pd.read_excel(settings.ALL_XLSX, sheet_name="reels_latestComments")
dtype = {
    'inputUrl': 'object',
    'id': 'str',
    'type': 'object',
    'shortCode': 'object',
    'caption': 'object',
    'hashtags': 'object',
    'mentions': 'object',
    'url': 'object',
    'commentsCount': 'int64',
    'firstComment': 'object',
    'latestComments': 'object',
    'dimensionsHeight': 'str',
    'dimensionsWidth': 'str',
    'displayUrl': 'object',
    'images': 'object',
    'videoUrl': 'object',
    'alt': 'float64',
    'likesCount': 'int64',
    'videoViewCount': 'int64',
    'videoPlayCount': 'int64',
    'timestamp': 'object',
    'childPosts': 'object',
    'ownerFullName': 'object',
    'ownerUsername': 'object',
    'ownerId': 'str',
    'productType': 'object',
    'videoDuration': 'float64',
    'isSponsored': 'bool',
    'musicInfo': 'object',
    'isCommentsDisabled': 'bool',
    'taggedUsers': 'object',
    'coauthorProducers': 'object',
    'locationName': 'object',
    'locationId': 'str',
    'isPinned': 'float64',
    'data_hora': 'datetime64[ns]',
    'Tipo': 'object'
}
df_reels = pd.read_excel(settings.ALL_XLSX, sheet_name="reels", dtype=dtype)
    
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

col2_bar, col3_bar = st.columns(2)
    
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

def plotarGraficoSeguidores():

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

def plotarGraficoSeguindo():

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

def plotarGraficoContagemPosts():

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

plotarGraficoSeguidores()

plotarGraficoSeguindo()

plotarGraficoContagemPosts()

col1, col2= st.columns(2)

with col1:

    # Identifica automaticamente todas as colunas numéricas
    numeric_cols = df_profiles.select_dtypes(include=np.number).columns.tolist()

    # Widget para selecionar o método de correlação (ainda útil)
    corr_method = st.selectbox(
        'Escolha o método de correlação:',
        ('pearson', 'kendall', 'spearman')
    )

    # Verifica se alguma coluna numérica foi encontrada
    if not numeric_cols:
        st.warning("Nenhuma coluna numérica foi encontrada nos dados para gerar a matriz.")
    else:
        # Calcula a matriz de correlação usando todas as colunas numéricas
        corr_matrix = df_profiles[numeric_cols].corr(method=corr_method)

        with st.spinner('Gerando o heatmap...'):
            # Gera o heatmap interativo com Plotly
            fig = px.imshow(
                corr_matrix,
                text_auto=True,
                aspect="auto",
                color_continuous_scale='RdBu_r', # Paleta de cores (Vermelho-Branco-Azul)
                #title="Heatmap de Correlação",
                height=1000, # <--- ADICIONE ESTA LINHA para ajustar a altura
                width=1000
            )
            
            # Exibe o gráfico no Streamlit
            st.plotly_chart(fig, use_container_width=True)

            # Opcional: Exibe a matriz de correlação como uma tabela
            if st.checkbox("Mostrar tabela da matriz de correlação"):
                st.dataframe(corr_matrix)

with col2:

    # Separa as colunas em numéricas e categóricas
    numeric_cols = df_profiles.select_dtypes(include=np.number).columns.tolist()

    # Verifica se há colunas numéricas suficientes
    if len(numeric_cols) < 2:
        st.error("Erro: Seus dados precisam ter pelo menos duas colunas numéricas para criar um gráfico de dispersão.")
        st.stop() # Interrompe a execução do script se não houver colunas suficientes

    # Cria três colunas para organizar os widgets de seleção lado a lado
    col1, col2= st.columns(2)

    with col1:
        # Widget para selecionar a variável do Eixo X
        x_axis = st.selectbox(
            'Selecione a variável para o Eixo X:',
            options=numeric_cols,
            index=0 # Define a primeira coluna numérica como padrão
        )

    with col2:
        # Widget para selecionar a variável do Eixo Y
        y_axis = st.selectbox(
            'Selecione a variável para o Eixo Y:',
            options=numeric_cols,
            index=1 # Define a segunda coluna numérica como padrão
        )

    # Gera o gráfico apenas se as variáveis dos eixos foram selecionadas
    if x_axis and y_axis:
        
        with st.spinner('Gerando seu gráfico...'):
            # Cria a figura do gráfico de dispersão usando Plotly Express
            fig = px.scatter(
                df_profiles,
                x=x_axis,
                y=y_axis,
                #title=f'Gráfico de Dispersão: {y_axis.capitalize()} vs. {x_axis.capitalize()}',
                # Adiciona mais informações ao passar o mouse sobre os pontos
                hover_data=df_profiles.columns,
                height=1000, # <--- ADICIONE ESTA LINHA para ajustar a altura
                width=1000

            )

            # Exibe o gráfico interativo no Streamlit
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Por favor, selecione as variáveis para os eixos X e Y.")