#!/bin/bash
# Copia figuras geradas pelo projeto para a pasta do TCC
# Execute após re-rodar os notebooks, antes de subir para o Overleaf

SRC="reports/figures"
DST="reports/academic/Figuras"

for fig in heatmap.png hierarchy.png intertopic_map.png sentiment_plots.png \
           avaliacaoAutoCluster.png boxplot_do_dataframe.png \
           grafico_sentimentos_cluster-1.png grafico_sentimentos_cluster0.png \
           grafico_sentimentos_cluster1.png top_5_governadores_positivo.png \
           top_5_governadores_negativo.png; do
  cp "$SRC/$fig" "$DST/$fig" && echo "✅ $fig" || echo "⚠️  $fig não encontrado"
done

echo ""
echo "Figuras sincronizadas. Agora faça upload de reports/academic/Figuras/ no Overleaf."