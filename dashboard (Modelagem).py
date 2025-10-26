import sys
import os

# Adiciona o diretório raiz do projeto ao sys.path
project_root = os.path.abspath(os.path.join(os.getcwd(), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from config import settings
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Dashboard de Vendas Interativo",
    page_icon="📊",
    layout="wide"
)


@st.cache_data
def carregar_dados():
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
    return df_comments, df_reels

df_comments, df_reels = carregar_dados()

# --- BARRA LATERAL (SIDEBAR) PARA FILTROS ---
st.sidebar.header("Filtros do Dashboard")

# Filtro 1: Região
sentimento_selecionado = st.sidebar.multiselect(
    "Selecione o Sentimento:",
    options=df_comments['sentiment_label'].unique(),
    default=df_comments['sentiment_label'].unique() # Por padrão, todas as opções são selecionadas
)

# Filtro 2: Categoria
topico_selecionada = st.sidebar.selectbox(
    "Selecione o Assunto:",
    options=df_comments['Topic'].unique()
)

# Filtro 3: Vendedor
governador_selecionado = st.sidebar.selectbox(
    "Selecione o Governador:",
    options=df_comments['inputUrl'].unique()
)

# --- APLICAÇÃO DOS FILTROS NO DATAFRAME ---
# A query abaixo filtra o dataframe com base nas seleções da barra lateral
df_filtrado_comments = df_comments.query(
    "sentiment_label == @sentimento_selecionado & Topic == @topico_selecionada & inputUrl == @governador_selecionado"
)

df_filtrado_reels = df_reels.query(
    "inputUrl == @governador_selecionado"
)

# --- PÁGINA PRINCIPAL ---
st.title("📊 Comentários dos Governadores do Brasil")
st.markdown("---")

# Tratamento para quando o dataframe filtrado estiver vazio
if df_filtrado_comments.empty:
    st.warning("Nenhum dado encontrado para os filtros selecionados.")
else:
   
    qtd_reels = int(df_filtrado_comments['id_reel'].nunique())
    qtd_comments = int(df_filtrado_comments['id_comment'].nunique())
    qtd_replies = int(df_filtrado_comments['repliesCount'].nunique())
    qtd_likes = int(df_filtrado_comments['repliesCount'].nunique())

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(label="Qtd de Reels", value=f"{qtd_reels}")
    with col2:
        st.metric(label="Qtd de Comentários", value=f"{qtd_comments}")
    with col3:
        st.metric(label="Qtd de Comentários", value=f"{qtd_replies}")
    with col4:
        st.metric(label="Qtd de Comentários", value=f"{qtd_likes}")
    
    
    col1, col2 = st.columns(2)
    
    with col1:

        df_filtrado_reels['shortCode'] = df_filtrado_reels['shortCode'].astype(str)
        
        df = df_filtrado_reels.sort_values(by='Total de Engajamento', ascending=False).head(10)

        # Criando a figura do gráfico
        fig = px.bar(
            df,
            x='Total de Engajamento',          # Valores numéricos no eixo X
            y='shortCode',       # Categorias no eixo Y
            orientation='h',
            height=700     # <<< A MÁGICA ACONTECE AQU
        )

        # Customizando a aparência (opcional)
        fig.update_traces(marker_color='#FF8C00', textposition='inside')
        fig.update_layout(
            yaxis={'categoryorder':'total ascending'} # Ordena as barras pela venda
        )

        # Plotando no Streamlit
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        with st.container(border=True):
            st.markdown("#### Resuma do Tópico")
            st.write(df_filtrado_comments['Name'].iloc[0])
        cols = ['timestamp_comment', 'owner.username', 'text', 'repliesCount', 'likesCount_comment']
        df_matrix = df_filtrado_comments[cols]
        st.dataframe(df_matrix)

# Para mostrar os dados brutos (opcional)
if st.checkbox("Mostrar dados brutos filtrados"):
    st.subheader("Dados Brutos")
    st.write(df_filtrado_comments)