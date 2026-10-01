# Invoice Anomaly — protocolo de avaliação em VALIDATION

## Objetivo e escopo pré-registrado — 24/09/2026

Medir quanto o Isolation Forest existente sinaliza as fraudes conhecidas da
fonte, sem confundir anomalia estatística com fraude comprovada. Esta etapa
avalia somente VALIDATION (`split=val`). Invoice TEST e Supplier TEST não serão
carregados. Não há treino, tuning, escolha de threshold ou alteração de features.
A avaliação final Supplier permanece encerrada.

## Configuração preservada

Artefato local confiável: `ml/models/isolation_forest.joblib`.
IsolationForest, 200 árvores, contamination=0.22, random_state=42, n_jobs=-1,
as mesmas 19 features ordenadas de `ml/scripts/treinar_modelo.py`.
Não carregar pickle/joblib recebido de fontes não confiáveis.
Divergência de versão scikit-learn ao carregar o modelo interrompe a avaliação;
não retreinar automaticamente para contornar incompatibilidade.

Regra baseline fixa: anomalia quando `decision_function(X) < 0`, equivalente
a `predict(X) == -1`. Igualdade em zero é normal. Score contínuo:
`invoice_anomaly_score = -score_samples(X)` (maior = mais anômalo).
O limiar equivalente desse score é `-model.offset_`, aprendido no TRAIN
original. Nenhum valor de validação redefine o offset. Score não é probabilidade.

## Entradas e alinhamento

- `train_features.parquet`: apenas IDs/split para verificar disjunção; não há fit.
- `val_features.parquet`: IDs, split, is_fraud, fraud_type e 19 features.
- `data/raw/splits.parquet`: ler somente linhas train/val.
- `data/raw/labels.parquet`: ler somente IDs de VALIDATION.
- Metadata e modelo existentes, sem modificar arquivos.

Conferir IDs únicos/não nulos, splits corretos e disjuntos, cobertura exata dos
IDs frente ao split oficial, labels binárias e igualdade de labels/fraud_type
com a fonte por ID (não por posição). Rejeitar features nulas, infinitas ou
não numéricas; somente as 19 features chegam ao modelo. Não ler arquivos TEST.
`fraud_type` nulo é grupo ausente explícito; não imputar categorias nem decompor
strings compostas em fraudes inventadas.

## Métricas definidas antes de observar resultados

Principal: Average Precision da classe fraudulenta usando score contínuo.
Secundárias: ROC-AUC; precision, recall e F1 por classe; F1-macro; balanced
accuracy; accuracy complementar; matriz [0,1]; proporção de alertas.
Sem custos operacionais conhecidos, não inventar um mínimo arbitrário de F1.
Referência trivial: nunca alertar (classe 0), sem novo estimador.

Por fraud_type: quantidade, fraudes, alertas, TP, FN e recall entre fraudes;
FPR somente sobre normais do grupo. Não chamar recall de uma categoria isolada
de precision dessa fraude. Grupos sem denominador recebem null, não zero.
Por cobertura de fornecedor: `supplier_frequency > 0` indica fornecedor
observado no TRAIN segundo a transformação existente; frequência zero indica
não observado. Não afirmar desempenho em fornecedores novos se grupo vazio.

## Limitações que permanecem

Agregações usam todo TRAIN e incluem a própria observação: não representam
histórico ponto-a-ponto. Split de faturas pode compartilhar fornecedores entre
partições; esta avaliação não comprova generalização temporal ou externa.
O metadata antigo não possui hash do dataset usado no fit nem versão das
bibliotecas: hashes atuais identificam o que foi auditado, não comprovam
retrospectivamente a origem exata do treinamento. Labels são referências
da fonte, não comprovação empresarial independente.

## Implementação e saída planejadas

Comando: `python -m ml.scripts.avaliar_invoice --split val`.
Sem opção de split TEST. Publicar um JSON exclusivo em
`ml/experiments/invoice_validation_v1.json`, contendo métricas, grupos,
offset/regra, parâmetros, hashes antes/depois, versão do código/ambiente e
fingerprint dos IDs. Recusar sobrescrita; não alterar o artefato de modelo.
Fixtures sintéticas não dependem dos datasets locais.

## Estado de execução

Protocolo registrado antes da inferência real e preservado após a execução.
Implementação e resultados serão registrados em docs/invoice_validation_results.md
depois dos testes e da revisão. Esta etapa não congela uma configuração final
Invoice nem autoriza TEST.
