import pandas as pd
from apify_client import ApifyClient
import json
from config import settings
import os

class Extract():

    def __init__(self, apify_api_key, links, resultsLimit=30):

        # Initialize the ApifyClient with your API token
        self.client = ApifyClient(apify_api_key)
        self.links = links
        self.resultsLimit = resultsLimit
        self.extractProfiles()
        self.extractPosts()
        self.extractReels()

    def extractProfiles(self):

        # Prepare the Actor input
        run_input = {
            "directUrls": self.links,
            "addParentData": False,
            "enhanceUserSearchWithFacebookPage": False,
            "isUserReelFeedURL": False,
            "isUserTaggedFeedURL": False,
            "resultsLimit": 100,
            "resultsType": "details",
            "searchType": "user"
        }

        # Run the Actor and wait for it to finish
        run = self.client.actor("shu8hvrXbJbY3Eb9W").call(run_input=run_input)

        items = []

        # Fetch and print Actor results from the run's dataset (if there are any)
        for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
            items.append(item)
            
        # Salva o item como um arquivo JSON
        with open(settings.PROFILES_JSON, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=4)

    def extractPosts(self):

        # Prepare the Actor input
        run_input = {
            "username": self.links,
            "resultsLimit": self.resultsLimit,
        }

        # Run the Actor and wait for it to finish
        run = self.client.actor("apify/instagram-post-scraper").call(run_input=run_input)

        items = []

        # Fetch and print Actor results from the run's dataset (if there are any)
        for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
            items.append(item)
            
        # Salva o item como um arquivo JSON
        with open(settings.POSTS_JSON, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=4)

    def extractReels(self):
        
        # Prepare the Actor input
        run_input = {
            "username": self.links,
            "resultsLimit": self.resultsLimit,
        }

        # Run the Actor and wait for it to finish
        run = self.client.actor("apify/instagram-reel-scraper").call(run_input=run_input)

        items = []

        # Fetch and print Actor results from the run's dataset (if there are any)
        for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
            items.append(item)
            
        # Salva o item como um arquivo JSON
        with open(settings.REELS_JSON, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=4)

class Transform():

    def __init__(self):
        
        self.lerDataframes()
        self.tranformData()

    def lerArquivo(self, nome_arquivo):
        try:
            with open(nome_arquivo, 'r', encoding='utf-8') as f:
                dados = json.load(f)
        except FileNotFoundError:
            print(f"Erro: O arquivo '{nome_arquivo}' não foi encontrado.")
            return None
        except json.JSONDecodeError:
            print(f"Erro: Não foi possível decodificar o arquivo '{nome_arquivo}'. Verifique se é um JSON válido.")
            return None
        except Exception as e:
            print(f"Ocorreu um erro inesperado: {e}")
            return None
        return dados

    def gerarDicionario(self):
        df_dicionario_profiles = pd.DataFrame({'Variáveis': list(self.df_profiles.columns), 'Fonte: ': 'Profiles.json'})
        df_dicionario_reels = pd.DataFrame({'Variáveis': list(self.df_posts.columns), 'Fonte: ': 'Posts.json'})
        df_dicionario_posts = pd.DataFrame({'Variáveis': list(self.df_reels.columns), 'Fonte: ': 'Reels.json'})
        df = pd.concat([df_dicionario_profiles, df_dicionario_reels, df_dicionario_posts])
        df.to_excel(settings.DICIONARIO_XLSX, index=False)

    def lerDataframes(self):
        
        profiles = self.lerArquivo(settings.PROFILES_JSON)
        posts = self.lerArquivo(settings.POSTS_JSON)
        reels = self.lerArquivo(settings.REELS_JSON)

        self.df_profiles = pd.DataFrame(profiles)
        self.df_posts = pd.DataFrame(posts)
        self.df_reels = pd.DataFrame(reels)

    def tranformData(self):
        
        self.df_posts['data_hora'] = pd.to_datetime(self.df_posts['timestamp']).dt.tz_convert('America/Sao_Paulo').dt.tz_localize(None)
        self.df_reels['data_hora'] = pd.to_datetime(self.df_reels['timestamp']).dt.tz_convert('America/Sao_Paulo').dt.tz_localize(None)
        self.df_reels['Width X Height'] = self.df_reels['dimensionsWidth'].astype(str) + ' X ' + self.df_reels['dimensionsHeight'].astype(str)
        
        self.df_posts['Tipo'] = 'FEED'
        self.df_reels['Tipo'] = 'REELS'

        self.df_reels_posts = pd.concat([self.df_posts, self.df_reels], axis=0)

        self.df_reels_posts_gruped = self.df_reels_posts.groupby(['ownerId', 'ownerUsername']).agg(
            commentsSum=('commentsCount', 'sum'),
            likesSum=('likesCount', 'sum'),
            minData=('data_hora', 'min'),
            maxData=('data_hora', 'max'),
            count=('ownerId', 'count')
        ).reset_index()

        self.df_profiles = pd.merge(self.df_profiles, self.df_reels_posts_gruped, left_on='id', right_on='ownerId', how='left').drop(['ownerId'], axis=1) 
        self.df_profiles[r'TOTAL ENGAJAMENTO'] = self.df_profiles['commentsSum'] + self.df_profiles['likesSum']
        self.df_profiles[r'% ENGAJAMENTO'] = self.df_profiles[r'TOTAL ENGAJAMENTO'] / self.df_profiles['followersCount']
        self.df_profiles['RECENCIA'] = 1 / ((self.df_profiles['maxData'].max() - self.df_profiles['maxData']).dt.days + 1)
        self.df_profiles['FREQUENCIA'] = self.df_profiles['count'] / ((self.df_profiles['maxData'] - self.df_profiles['minData']).dt.days + 1)

        df_exploded = self.df_reels.explode('latestComments').copy()
        df_normalized = pd.json_normalize(df_exploded['latestComments'])
        df_normalized.index = df_exploded.index
        self.df_latestComments = df_exploded.drop('latestComments', axis=1).join(df_normalized, lsuffix='_reel', rsuffix='_comment')
        self.df_latestComments = self.df_latestComments.drop(['hashtags', 'mentions', 'images', 'childPosts', 'musicInfo', 'replies', 'taggedUsers', 'coauthorProducers'], axis=1)
        self.df_latestComments['comprimento texto'] = self.df_latestComments['text'].str.len()
        self.df_latestComments = self.df_latestComments[self.df_latestComments['comprimento texto'] < 512]
        self.df_latestComments = self.df_latestComments.drop_duplicates()

class Load():

    def __init__(self, transformer):
        self.transformer = transformer
        self.generateDataframes()
        self.loadDataframes()
    
    def generateDataframes(self):
        self.df_profiles = self.transformer.df_profiles
        self.df_posts = self.transformer.df_posts
        self.df_reels = self.transformer.df_reels
        self.df_latestComments = self.transformer.df_latestComments
        self.df_reels_posts = self.transformer.df_reels_posts
    
    def loadDataframes(self):
        with pd.ExcelWriter(settings.ALL_XLSX, engine='openpyxl') as writer:
            self.df_profiles.to_excel(writer, sheet_name="profiles", index=False)
            self.df_posts.to_excel(writer, sheet_name="posts", index=False)
            self.df_reels.to_excel(writer, sheet_name="reels", index=False)
            self.df_latestComments.to_excel(writer, sheet_name="reels_latestComments", index=False)
            self.df_reels_posts.to_excel(writer, sheet_name="reels_posts", index=False)

def ELT(apify_api_key: str, links: list[str], results_limit: int = 30):
    """
    Executa as etapas de Extração, Transformação e Carga dos dados.
    """
    files_exist = all([
        os.path.exists(settings.PROFILES_JSON),
        os.path.exists(settings.POSTS_JSON),
        os.path.exists(settings.REELS_JSON),
    ])

    if not files_exist:
        print("🔍 [1/3] EXTRAÇÃO: Arquivos não encontrados, extraindo com Apify...")
        Extract(apify_api_key=apify_api_key, links=links, resultsLimit=results_limit)
    else:
        print("📁 [1/3] EXTRAÇÃO: Arquivos já existem. Pulando extração...")

    print("🔧 [2/3] TRANSFORMAÇÃO: Processando dados...")
    transformer = Transform()

    print("💾 [3/3] CARGA: Salvando arquivos processados...")
    Load(transformer)

    print(f"✅ Pipeline ELT finalizado com sucesso!")
    print(f"📄 Arquivo salvo em: {settings.ALL_XLSX}")