import numpy as np
import pandas as pd
from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
from sklearn.preprocessing import StandardScaler
from hyperopt import fmin, tpe, hp, STATUS_OK, Trials
import warnings

# Suprimir avisos para uma saída mais limpa
warnings.filterwarnings('ignore')

class AutoClusterHPO:
    
    def __init__(self, max_evals_per_algo=50):
        """
        Inicializa a classe AutoClusterHPO para aplicar o método do autor.

        Args:
            max_evals_per_algo (int): Número máximo de tentativas de otimização
                                      para cada algoritmo de agrupamento usando Hyperopt.
        """
        self.max_evals_per_algo = max_evals_per_algo
        self.best_overall_model = None
        self.best_overall_score = -np.inf
        self.best_overall_config = None
        self.best_overall_labels = np.array([]) # Inicialização aqui!

    def _evaluate_combined_cvi_score(self, X, labels):
        """
        Avalia um modelo de agrupamento usando múltiplos CVIs e retorna uma pontuação combinada.
        """
        n_clusters = len(np.unique(labels))
        
        # Filtra pontos de ruído para cálculo de CVIs se for DBSCAN
        if -1 in labels:
            filtered_X = X[labels != -1]
            filtered_labels = labels[labels != -1]
            if len(np.unique(filtered_labels)) < 2 or len(filtered_X) < 2:
                return -np.inf
            X_for_cvi = filtered_X
            labels_for_cvi = filtered_labels
        else:
            if n_clusters < 2:
                return -np.inf
            X_for_cvi = X
            labels_for_cvi = labels

        try:
            sil_score = silhouette_score(X_for_cvi, labels_for_cvi)
        except ValueError:
            sil_score = -1.0 

        try:
            chi_score = calinski_harabasz_score(X_for_cvi, labels_for_cvi)
        except ValueError:
            chi_score = 0.0

        try:
            dbi_score = davies_bouldin_score(X_for_cvi, labels_for_cvi)
        except ValueError:
            dbi_score = np.inf 
        
        normalized_chi = np.tanh(chi_score / 10000.0) 
        normalized_dbi = 0.0
        if dbi_score != np.inf and dbi_score > 0:
            normalized_dbi = np.tanh(1.0 / dbi_score) 
        
        combined_score = (sil_score + normalized_chi + normalized_dbi) / 3.0
        return combined_score

    def _objective_function(self, params, X_scaled, algorithm_name, random_state):
        """
        Função objetivo para Hyperopt para otimizar hiperparâmetros de um algoritmo específico.
        Hyperopt minimiza, então retornamos -combined_score.
        """
        labels = np.array([])
        model = None
        
        try:
            if algorithm_name == 'KMeans':
                n_clusters = int(params['n_clusters'])
                if n_clusters < 2 or n_clusters >= len(X_scaled): 
                     return {'loss': np.inf, 'status': STATUS_OK}
                model = KMeans(n_clusters=n_clusters, random_state=random_state, n_init='auto')
                model.fit(X_scaled)
                labels = model.labels_
            elif algorithm_name == 'DBSCAN':
                model = DBSCAN(eps=params['eps'], min_samples=int(params['min_samples']))
                labels = model.fit_predict(X_scaled)
            elif algorithm_name == 'Agglomerative Clustering':
                n_clusters = int(params['n_clusters'])
                if n_clusters < 2 or n_clusters >= len(X_scaled):
                     return {'loss': np.inf, 'status': STATUS_OK}
                model = AgglomerativeClustering(n_clusters=n_clusters, linkage=params['linkage'])
                labels = model.fit_predict(X_scaled)
            else:
                return {'loss': np.inf, 'status': STATUS_OK} 

            combined_score = self._evaluate_combined_cvi_score(X_scaled, labels)
            loss = -combined_score
            if np.isinf(loss):
                loss = np.inf

            return {'loss': loss, 'status': STATUS_OK, 'model': model, 'labels': labels, 'params': params}
        except Exception as e:
            return {'loss': np.inf, 'status': STATUS_OK}

    def fit_predict(self, X_df):
        """
        Aplica o framework AutoCluster para encontrar o melhor agrupamento para o DataFrame.

        Args:
            X_df (pd.DataFrame): DataFrame contendo apenas as características (sem rótulos de verdade).
        
        Returns:
            np.ndarray: Os rótulos de cluster atribuídos pelo melhor modelo encontrado.
        """
        if X_df.empty:
            print("DataFrame de entrada vazio.")
            # Garante que self.best_overall_labels é um array vazio se o DF estiver vazio.
            self.best_overall_labels = np.array([]) 
            return self.best_overall_labels

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_df)
        
        n_samples = len(X_scaled)
        max_n_clusters = min(21, int(n_samples * 0.5) + 1)
        if max_n_clusters < 3:
            max_n_clusters = 3 

        algorithms_and_spaces = {
            'KMeans': {'n_clusters': hp.randint('kmeans_n_clusters', 3, max_n_clusters)},
            'DBSCAN': {'eps': hp.uniform('dbscan_eps', 0.1, 2.0), 'min_samples': hp.randint('dbscan_min_samples', 2, 20)},
            'Agglomerative Clustering': {'n_clusters': hp.randint('agglo_n_clusters', 3, max_n_clusters), 'linkage': hp.choice('agglo_linkage', ['ward', 'complete', 'average', 'single'])}
        }

        print("Iniciando otimização de hiperparâmetros...")
        
        for algo_name, space in algorithms_and_spaces.items():
            trials = Trials()
            fmin(
                fn=lambda params: self._objective_function(params, X_scaled, algo_name, random_state=42),
                space=space,
                algo=tpe.suggest,
                max_evals=self.max_evals_per_algo,
                trials=trials,
                rstate=np.random.default_rng(42)
            )

            best_trial_result = None
            for t in trials.results:
                if t['status'] == STATUS_OK and ('model' in t) and ('labels' in t) and not np.isinf(-t['loss']):
                    if best_trial_result is None or -t['loss'] > -best_trial_result['loss']:
                        best_trial_result = t
            
            if best_trial_result:
                current_best_score = -best_trial_result['loss']
                if current_best_score > self.best_overall_score:
                    self.best_overall_score = current_best_score
                    self.best_overall_model = best_trial_result.get('model')
                    self.best_overall_config = {k: (int(v) if isinstance(v, np.int64) else v) for k, v in best_trial_result.get('params', {}).items()}
                    self.best_overall_labels = best_trial_result.get('labels') # Atribuição aqui!

        print("\nProcesso de AutoCluster concluído.")
        if self.best_overall_model is not None and self.best_overall_score != -np.inf:
            print(f"Melhor algoritmo: {self.best_overall_model.__class__.__name__}")
            print(f"Melhores parâmetros: {self.best_overall_config}")
            print(f"Melhor pontuação CVI combinada: {self.best_overall_score:.4f}")
            return (
                self.best_overall_labels,
                self.best_overall_model,
                self.best_overall_config,
                self.best_overall_score,
                self.best_overall_model.__class__.__name__
            )
        else:
            print("Não foi possível encontrar um modelo de agrupamento válido.")
            # Garante que self.best_overall_labels é um array vazio se nenhum modelo válido for encontrado.
            self.best_overall_labels = np.array([]) 
            return (self.best_overall_labels, None, None, -np.inf, None)

# Exemplo de uso:
if __name__ == "__main__":
    
    from sklearn.datasets import make_blobs

    # Criar um DataFrame de exemplo qualquer
    X_sample, _ = make_blobs(n_samples=500, n_features=4, centers=4, cluster_std=1.0, random_state=42)
    data_to_cluster_df = pd.DataFrame(X_sample, columns=[f'feature_{i}' for i in range(X_sample.shape[1])])

    print(f"DataFrame de entrada. Dimensões: {data_to_cluster_df.shape}")
    print(data_to_cluster_df.head())

    # Inicializar e aplicar o AutoCluster
    autocluster_tool = AutoClusterHPO(max_evals_per_algo=20) 
    cluster_labels = autocluster_tool.fit_predict(data_to_cluster_df)

    if cluster_labels.size > 0:
        
        print("\n--- Resultados do Agrupamento ---")
        unique_labels = np.unique(cluster_labels)
        n_detected_clusters = len(unique_labels)
        if -1 in unique_labels: 
            n_detected_clusters -= 1
            print(f"Número de clusters detectados (excluindo ruído): {n_detected_clusters}")
            print(f"Número de pontos de ruído: {np.sum(cluster_labels == -1)}")
        else:
            print(f"Número de clusters detectados: {n_detected_clusters}")
        print(f"Primeiros 10 rótulos de cluster: {cluster_labels[:10]}")

        # Opcional: adicionar os rótulos ao DataFrame original para inspeção
        data_to_cluster_df['cluster_label'] = cluster_labels
        print("\nDataFrame com rótulos de cluster (primeiras linhas):")
        print(data_to_cluster_df.head())