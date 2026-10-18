# Invoice — avaliador acadêmico

**Estado em 18/10/2026:** avaliação final única em TEST concluída com o executor
da arquitetura simplificada. O modelo existente e as 19 features foram
preservados, sem fit ou tuning. TEST e raw não devem ser acessados durante
desenvolvimento ou verificação; esta atualização documental não repete a avaliação.

## Fluxo e responsabilidades

Dados → preparação → EDA → features → treinamento → validação →
avaliação final → resultados.

- [invoice_final_evaluation.py](../ml/scripts/invoice_final_evaluation.py)
  calcula a avaliação com dados/modelo explicitamente fornecidos, sem fit.
- [invoice_data_adapter.py](../ml/scripts/invoice_data_adapter.py) valida
  schema, ordem das features, IDs únicos/disjuntos, partições, labels e
  compatibilidade do modelo com metadata e features.
- [invoice_real_inputs.py](../ml/scripts/invoice_real_inputs.py) confere
  cobertura dos IDs, correspondência de labels por ID, ausência de
  sobreposição e consistência de valores monetários/moeda.
- [invoice_real_evaluation.py](../ml/scripts/invoice_real_evaluation.py)
  fornece a entrada pública `run_final_evaluation(output_path, *, frames, model,
  metadata, splits, labels, amounts, configuration, evaluation_id)`. Ela exige
  as partições e fontes em memória e chama `validate_frames()` antes de avaliar
  o frame/modelo retornados e gravar um JSON normal. Falha de validação impede
  scoring e gravação; destino existente é recusado antes da validação. Não aceita
  apenas frame/modelo nem oferece opção para pular a validação das fontes.
- [invoice_historical_evidence.py](../ml/scripts/invoice_historical_evidence.py)
  verifica os três resultados históricos separadamente. Não é requisito para
  avaliar novos inputs.

Os scripts científicos históricos e seus resultados são preservados. Rotas
antigas que leem raw compartilhado continuam impróprias para ensaios no checkout
real: filtrar TRAIN/VALIDATION não isola fisicamente TEST.

## Validações e cálculo

Usar exatamente as 19 features e sua ordem em
[FEATURES](../ml/scripts/treinar_modelo.py), sem labels/IDs como features.
Features são numéricas, finitas e sem nulos; labels binárias válidas; IDs
únicos e partições separadas. Não descartar colunas inesperadas ou corrigir
labels silenciosamente. Alinhar fontes por ID, nunca pela posição das linhas.

Preservar Isolation Forest, 200 árvores, `contamination=0.22`,
`random_state=42`, `n_jobs=-1`, `max_features=1.0`, `max_samples=auto`,
`bootstrap=False`, `warm_start=False`, `verbose=0` e offset legado
`-0.5211491197816622`. Compatibilidade técnica não prova a procedência do fit.

O score é `-score_samples`, ordenado de forma decrescente; o avaliador não
chama `fit`, `predict` ou `decision_function`. A baseline ordena
`invoice_amount` decrescente, com sinal original e sem câmbio. A mesma
coorte e uma moeda única não nula são exigidas. Desempate por
`invoice_id` crescente, sem usar a label.

Reportar todos os orçamentos 1%, 5% e 10%, com
K = min(N, ceil(N × percentual / 100)), fração efetiva e empates.
Precision@K, captura, lift, composição por `fraud_type`, comuns/exclusivos,
Jaccard e ganhos líquido/bruto/sacrificado seguem o
[protocolo de comparação](invoice_value_comparison_protocol.md).
Denominadores inexistentes produzem `null`.

As matrizes de seleção têm linhas de referência [0, 1] e colunas
[não selecionada, selecionada]. Por tipo, aplicar a máscara global, sem criar
uma fila própria. Não interpretá-las como classificação automática de fraude
pelo threshold legado. Grupos sem seleção permanecem visíveis.

## Resultado e execução

O JSON registra identificação da avaliação, partição, configuração do modelo,
lista ordenada de features, métricas, resultados relevantes, limitações e
timestamp. A gravação cria um arquivo novo e recusa destino existente.
Não sobrescrever resultados históricos nem executar novamente TEST em outro
destino para contornar a proteção.

O chamador fornece explicitamente os dados/modelo e o destino. A avaliação final
foi realizada em tarefa própria, após a refatoração, com validação das fontes
concluída antes do scoring: schema, IDs, partições sem sobreposição, ordem das
19 features, labels, valores/moeda e compatibilidade do modelo com a metadata.
TRAIN e VALIDATION participaram das verificações de consistência e separação;
somente os 60.000 registros de TEST foram pontuados. A moeda validada foi ZAR.

O executor utilizou `ml/models/isolation_forest.joblib` e
`ml/models/model_metadata.json`, sem alterar parâmetros ou offset. Houve uma
única chamada de `score_samples`, nenhum fit, nenhum tuning e uma gravação
exclusiva em [ml/experiments/invoice_test_final_v1.json](../ml/experiments/invoice_test_final_v1.json).

- Identificação: `invoice_test_final_v1`.
- SHA-256: `203e9ceb18c028c73eb0e3688eaaa24ead21129aa60d61daf0ae19468512b58a`.

O arquivo contém a comparação IF × valor em 1%, 5% e 10%, matrizes de seleção
globais e por tipo e limitações. Os JSONs históricos de VALIDATION foram
preservados. Não repetir TEST nem usá-lo para debugging, tuning ou exploração.

## Evidência e limitações

`is_fraud` é referência secundária não verificada; `fraud_type` serve à
composição, preservando ausências, NONE e divergências. Score de anomalia não
é fraude confirmada, probabilidade de fraude ou risco empresarial comprovado.

Manter `source_reconciled=false`,
`legacy_training_provenance_certified=false` e
`raw_independence_certified=false`. Conferência de linhas, hashes e
compatibilidade não certifica os inputs do treinamento legado. Permanecem as
limitações de temporalidade, fornecedores conhecidos, labels e utilidade
humana do [protocolo acadêmico](invoice_academic_evaluation_protocol.md).

Testes usam fixtures sintéticas e diretórios temporários. Seus resultados não
são evidência científica e não devem ser inseridos em `ml/experiments/`.
Excluir da execução testes que acessam dados reais ou executam células da EDA;
não executar notebooks. A verificação técnica inclui testes científicos
isolados, Ruff, imports e referências documentais, sem avaliar datasets reais.
