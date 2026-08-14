#!/bin/bash
# Copia figuras geradas pelo projeto para a pasta do TCC
# Execute após re-rodar os notebooks, antes de subir para o Overleaf

SRC="reports/figures"
DST="reports/academic/Figuras"

# Só as figuras que os notebooks de fato regeneram em reports/figures/.
# As demais (avaliacaoAutoCluster, boxplot_do_dataframe,
# grafico_sentimentos_cluster*, top_5_governadores_*) são versionadas
# diretamente em reports/academic/Figuras/ e não têm origem automatizada.
for fig in heatmap.png hierarchy.png intertopic_map.png sentiment_plots.png \
           hierarchical_Documents_and_Topics.png; do
  cp "$SRC/$fig" "$DST/$fig" && echo "✅ $fig" || echo "⚠️  $fig não encontrado"
done

echo ""
echo "Figuras sincronizadas. Agora faça upload de reports/academic/Figuras/ no Overleaf."