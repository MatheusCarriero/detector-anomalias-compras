# Supplier Risk — primeira rodada experimental

## 1. Objetivo e estado da entrega

**IMPLEMENTADO:** uma baseline majoritária, quatro configurações de Logistic Regression (LR) e quatro de Random Forest (RF), treinadas exclusivamente em TRAIN e comparadas em VALIDATION. O [notebook 02 executado](../ml/supplier_risk/notebooks/02_supplier_risk_baseline_models.ipynb) contém validações, parâmetros, métricas, matrizes de confusão, ablações, incerteza e gráficos. Os resultados abaixo são transcritos de suas saídas, arredondados a cinco casas; nenhuma nova execução de treinamento foi necessária para fechar este relatório.

**Pergunta:** os dados disponíveis permitem classificar `Risk_Level` melhor que uma previsão trivial da classe majoritária?

**RESULTADO OBSERVADO:** sim, nesta divisão TRAIN/VALIDATION e nas configurações fixadas. Todos os oito classificadores superaram a referência trivial em F1-macro e balanced accuracy e reconheceram ambas as classes. Isso constitui evidência experimental, não avaliação final nem validação empresarial.

**LIMITAÇÃO:** `0 = menor risco` e `1 = maior risco` são a convenção do projeto. A origem/regra de `Risk_Level` permanece desconhecida. O objetivo é reproduzir a classificação fornecida, não prever fraude, falha, ruptura ou risco real futuro. Nenhuma versão final foi selecionada, nenhum threshold foi otimizado e nenhum modelo foi serializado.

## 2. Dados utilizados e prevenção de leakage

Foram abertos somente estes quatro Parquets de `data/processed/supplier_risk/ml_ready/`:

- `X_train.parquet`;
- `y_train.parquet`;
- `X_validation.parquet`;
- `y_validation.parquet`.

O `preprocessing_metadata.json` existente foi consultado para contrato, hashes e rastreabilidade do produtor, usando somente os campos necessários à comparação TRAIN/VALIDATION. Nenhum Parquet de TEST foi aberto; nenhuma estatística de TEST orientou os experimentos. Os splits originais não foram recalculados.

| Conjunto | Fornecedores | Classe 0 | Classe 1 | Features de A |
|---|---:|---:|---:|---:|
| TRAIN | 16.894 | 5.008 (29,6437%) | 11.886 (70,3563%) | 10 |
| VALIDATION | 3.539 | 1.110 (31,3648%) | 2.429 (68,6352%) | 10 |

O notebook verifica schemas e ordem das features, ausência de identificadores/target em X, X/y com o mesmo tamanho e índice posicional, ambas as classes, ausência de nulos/infinitos e hashes exatos dos arquivos conforme o metadata de produção. X/y não contêm `supplier_id`: a prova de alinhamento depende dos hashes das saídas do produtor, que ordenou e reconciliou os IDs. Não se afirma que um RangeIndex igual, isoladamente, comprova alinhamento, nem que os IDs foram novamente associados nesta rodada.

**Imputação:** o ML-Ready já recebeu imputação mediana aprendida somente em TRAIN. Os Pipelines obrigatórios ajustam novamente `SimpleImputer(strategy="median")` exclusivamente em TRAIN; como esses dados não têm nulos, essa transformação é neutra. As estatísticas são conferidas contra TRAIN, as transformações preservam os valores e os estados aprendidos não mudam após prever VALIDATION. O `StandardScaler` da LR também é ajustado apenas em TRAIN, sem regravar os Parquets.

Não houve cross-validation. Uma CV futura deverá partir da base com nulos, filtrada para TRAIN, com transformadores aprendidos dentro de cada fold; não reutilizar diretamente este X_train previamente imputado para CV.

## 3. Configuração fixa e métricas

| Modelo | Configuração inicial | Transformações |
|---|---|---|
| Baseline 0 | `DummyClassifier(strategy="most_frequent")`; maioria aprendida de y_train = classe 1 | Nenhuma necessária |
| Logistic Regression | `C=1.0`, `solver="lbfgs"`, `max_iter=1000`, `random_state=42`, sem ponderação de classes; demais parâmetros padrão | SimpleImputer mediano → StandardScaler → LogisticRegression |
| Random Forest | `n_estimators=100`, `random_state=42`, `n_jobs=-1`; demais parâmetros padrão | SimpleImputer mediano → RandomForestClassifier |

O limite de 1.000 iterações da LR foi uma precaução inicial de convergência, não tuning. O orçamento foi fixado em **nove fits**: uma baseline e quatro versões de cada família. Todos concluíram sem avisos de ajuste. Foram usadas predições padrão de `predict()`, sem busca de corte. Não houve GridSearch, calibração ou ajuste adaptativo de hiperparâmetros.

Métrica principal: **F1-macro**. Secundárias: balanced accuracy, precision/recall/F1 por classe, ROC-AUC e PR-AUC reportada como **Average Precision (AP)**; accuracy é complementar. Classe positiva = 1. ROC-AUC/AP usam scores contínuos de `predict_proba()`, não os rótulos previstos. Métricas indefinidas por ausência de previsões de uma classe são reportadas como zero, sem ocultar a matriz de confusão.

A saída probabilística representa **estimativa de pertencimento à classe 1**, não probabilidade real de falha. Calibração não foi avaliada; esses percentuais não estão aprovados para comunicação operacional.

## 4. RESULTADO OBSERVADO — comparação com as dez features

| Modelo | F1-macro | Balanced accuracy | Accuracy | ROC-AUC | AP |
|---|---:|---:|---:|---:|---:|
| Logistic Regression A | 0,92955 | 0,92432 | 0,94010 | 0,98765 | 0,99429 |
| Random Forest A | 0,91538 | 0,90630 | 0,92879 | 0,97580 | 0,98792 |
| Baseline majoritária | 0,40700 | 0,50000 | 0,68635 | 0,50000 | 0,68635 |

O score constante da baseline não discrimina classes: ROC-AUC = 0,5 e AP igual à prevalência positiva de VALIDATION. Sua accuracy de 68,635% não significa reconhecimento da classe minoritária.

| Modelo | Precision 0 | Recall 0 | F1 0 | Precision 1 | Recall 1 | F1 1 |
|---|---:|---:|---:|---:|---:|---:|
| Logistic Regression A | 0,92358 | 0,88198 | 0,90230 | 0,94716 | 0,96665 | 0,95681 |
| Random Forest A | 0,92059 | 0,84595 | 0,88169 | 0,93212 | 0,96665 | 0,94907 |
| Baseline majoritária | 0,00000 | 0,00000 | 0,00000 | 0,68635 | 1,00000 | 0,81401 |

Matrizes de confusão, ordem `[0, 1]`; linhas representam a classe real e colunas a prevista:

| Modelo | Real 0 / prevista 0 (TN) | Real 0 / prevista 1 (FP) | Real 1 / prevista 0 (FN) | Real 1 / prevista 1 (TP) |
|---|---:|---:|---:|---:|
| Logistic Regression A | 979 | 131 | 81 | 2.348 |
| Random Forest A | 939 | 171 | 81 | 2.348 |
| Baseline majoritária | 0 | 1.110 | 0 | 2.429 |

**INTERPRETAÇÃO:** LR e RF não estão apenas prevendo a maioria. LR A reconhece 88,198% da classe 0 e 96,665% da classe 1. RF A não supera LR A nesta rodada: tem 40 erros adicionais na classe 0 e o mesmo total de erros na classe 1. A ordenação é descritiva; não constitui escolha de algoritmo definitivo.

## 5. RESULTADO OBSERVADO — ablações A/B/C/D

Lista ordenada das features de A:

1. `financial_stability_score`
2. `on_time_delivery_rate`
3. `defect_rate`
4. `geopolitical_risk_index`
5. `lead_time_days`
6. `alternative_suppliers_available`
7. `contract_length_months`
8. `environmental_compliance`
9. `previous_disruptions`
10. `supplier_record_count`

| Versão | Quantidade | Exclusões em relação a A; demais features e ordem preservadas |
|---|---:|---|
| A | 10 | Nenhuma |
| B | 9 | `geopolitical_risk_index` |
| C | 9 | `supplier_record_count` |
| D | 8 | `geopolitical_risk_index`, `supplier_record_count` |

Cada versão foi ajustada em TRAIN com os mesmos parâmetros da respectiva família e comparada nos mesmos fornecedores de VALIDATION. Nenhuma feature foi removida dos arquivos de dados.

| Modelo / versão | F1-macro | Balanced accuracy | Recall 0 | F1 0 | Recall 1 | F1 1 |
|---|---:|---:|---:|---:|---:|---:|
| LR A | 0,92955 | 0,92432 | 0,88198 | 0,90230 | 0,96665 | 0,95681 |
| LR B | 0,78657 | 0,77397 | 0,63604 | 0,69557 | 0,91190 | 0,87758 |
| LR C | 0,92955 | 0,92432 | 0,88198 | 0,90230 | 0,96665 | 0,95681 |
| LR D | 0,78685 | 0,77417 | 0,63604 | 0,69591 | 0,91231 | 0,87780 |
| RF A | 0,91538 | 0,90630 | 0,84595 | 0,88169 | 0,96665 | 0,94907 |
| RF B | 0,77966 | 0,76489 | 0,61171 | 0,68310 | 0,91807 | 0,87623 |
| RF C | 0,91601 | 0,90671 | 0,84595 | 0,88252 | 0,96748 | 0,94949 |
| RF D | 0,78148 | 0,76666 | 0,61441 | 0,68577 | 0,91890 | 0,87719 |

Precision por classe nas ablações:

| Modelo / versão | Precision 0 | Precision 1 |
|---|---:|---:|
| LR A | 0,92358 | 0,94716 |
| LR B | 0,76739 | 0,84574 |
| LR C | 0,92358 | 0,94716 |
| LR D | 0,76823 | 0,84580 |
| RF A | 0,92059 | 0,93212 |
| RF B | 0,77335 | 0,83803 |
| RF C | 0,92240 | 0,93217 |
| RF D | 0,77588 | 0,83910 |

O notebook preserva também accuracy, ROC-AUC, AP e matrizes de confusão de todas as oito configurações.

**INTERPRETAÇÃO:**

- Remover o índice geopolítico reduz F1-macro em aproximadamente **14,30 pontos percentuais na LR** e **13,57 pontos na RF** (B − A). A perda aparece principalmente no reconhecimento da classe 0, mas também afeta a classe 1. Há dependência relevante de uma feature cuja procedência não foi comprovada.
- Remover a contagem não altera F1-macro/balanced accuracy da LR em A versus C. Na RF, C − A é apenas +0,00063 em F1-macro; o intervalo pareado inclui zero. D versus B também não demonstra contribuição clara da contagem. Isso não prova inutilidade universal, mas **não há evidência de ganho com supplier_record_count nesta rodada**.
- As versões sem índice geopolítico também superam claramente a baseline, inclusive D sem as duas features. O sinal classificatório não depende exclusivamente dessas variáveis.
- Não foi escolhida uma versão final. Não confundir o maior valor pontual com justificativa para ignorar procedência ou incerteza.

## 6. Incerteza descritiva

Conforme o protocolo anterior, foram realizadas **2.000 reamostragens pareadas por fornecedor em VALIDATION**, seed 42, sem novos fits. Todas continham ambas as classes; zero descartes. ICs percentis de 95%, condicionais aos modelos já ajustados.

| Comparação | Delta F1-macro | IC 95% do delta |
|---|---:|---|
| LR A − baseline | +0,52255 | [+0,51102; +0,53248] |
| RF A − baseline | +0,50838 | [+0,49605; +0,51987] |
| RF A − LR A | −0,01417 | [−0,02242; −0,00617] |
| LR B − LR A | −0,14298 | [−0,15856; −0,12742] |
| RF B − RF A | −0,13572 | [−0,15123; −0,12050] |
| LR C − LR A | 0,00000 | [0,00000; 0,00000] |
| RF C − RF A | +0,00063 | [−0,00482; +0,00617] |
| LR D − LR B | +0,00028 | [−0,00057; +0,00114] |
| RF D − RF B | +0,00182 | [−0,00584; +0,00968] |

Os limites inferiores dos deltas de F1-macro **e** balanced accuracy contra a baseline ficaram acima de zero em todas as oito configurações. Para LR A, o ganho de balanced accuracy foi +0,42432, IC [+0,41395; +0,43389]; para RF A, +0,40630, IC [+0,39430; +0,41728]. O notebook contém todos os intervalos.

**LIMITAÇÃO:** os intervalos não corrigem comparações múltiplas, reutilização futura de VALIDATION, incerteza de treino ou variação entre seeds/populações. O intervalo nulo de LR C − A descreve esta comparação fixa, não prova equivalência universal. Não se declara significância generalizável nem vencedor definitivo.

## 7. Features e relação com a EDA

**RESULTADO OBSERVADO**, conjunto A:

| Feature | Coeficiente LR padronizado | Importância RF (MDI) |
|---|---:|---:|
| financial_stability_score | −5,62404 | 0,38701 |
| geopolitical_risk_index | +4,20136 | 0,19007 |
| alternative_suppliers_available | −2,43159 | 0,07753 |
| previous_disruptions | +1,90549 | 0,04477 |
| environmental_compliance | −1,82045 | 0,08989 |
| contract_length_months | +1,46598 | 0,06449 |
| on_time_delivery_rate | −0,77630 | 0,05555 |
| lead_time_days | +0,50473 | 0,04314 |
| defect_rate | +0,10179 | 0,04566 |
| supplier_record_count | +0,03133 | 0,00188 |

**INTERPRETAÇÃO:** estabilidade financeira e índice geopolítico têm as maiores magnitudes na LR e importâncias na RF, coerentes com as associações descritivas da [EDA restrita ao TRAIN](supplier_risk_eda.md). O sinal negativo da estabilidade financeira se associa a menor log-odds estimado da classe 1, condicionando nas demais features; o índice geopolítico tem sinal positivo. Não são efeitos causais.

A concentração nessas variáveis e a queda da ablação são compatíveis com a hipótese de participação na construção da label ou de proxy. **Não comprovam essa hipótese, data leakage direto, nem a regra original.** Importâncias MDI são calculadas no treino, podem favorecer alta cardinalidade e não medem isoladamente valor incremental fora da amostra. Coeficientes também dependem de escala, regularização e relações entre features.

## 8. Limitações e próximos experimentos — PLANEJADO

1. Priorizar a procedência de `Risk_Level` e `geopolitical_risk_index`: origem, fórmula, data e relação com país continuam sem confirmação. Uma métrica alta pode reproduzir uma regra do dataset sem representar risco empresarial real.
2. Manter `supplier_record_count` como contagem de registros distintos, não histórico temporal. Não alterar o contrato agora; eventual preferência por uma versão conservadora exige decisão experimental documentada.
3. Preservar as pendências de domínio: compliance acima de 100 e lead time zero não foram corrigidos ou eliminados nesta rodada. Os dados não têm temporalidade comprovada para prever eventos futuros.
4. Antes de novos ajustes, registrar orçamento e finalidade. Se houver CV interna em TRAIN, usar a base com nulos e um Pipeline completo em cada fold; evitar exploração indefinida da mesma VALIDATION. Avaliação de estabilidade por seeds e importância por permutação podem ser experimentos posteriores, não resultados desta entrega.
5. Se probabilidades forem exibidas futuramente, avaliar calibração em um protocolo de desenvolvimento separado. Não interpretar AP/ROC-AUC elevados como comprovação de calibração.
6. TEST permanece congelado. Somente após decisão e congelamento explícitos de features, transformações e modelo poderá ocorrer avaliação final; nenhuma autorização para essa leitura é inferida desta rodada.

Não foram alterados Invoice Anomaly, Purchase Risk, fontes, splits ou ML-Ready. Procurement KPI permanece auxiliar e não participou dos fits. Não há modelo definitivo, artefato de produção ou seleção de threshold.

## 9. Reprodução e verificação

Notebook executado integralmente: **dez células de código, zero erros**, nove fits experimentais e quatro figuras incorporadas. Versões: Python 3.14.3; pandas 2.3.3; NumPy 2.5.2; PyArrow 25.0.1; scikit-learn 1.9.0; matplotlib 3.10.8; nbformat 5.10.4; nbclient 0.10.4; ipykernel 7.2.0. Foi usado o ambiente temporário isolado já validado, sem modificar a `.venv` principal ou requisitos.

O executor Jupyter emitiu aviso não bloqueante sobre o event loop do Windows/PyZMQ; as células terminaram normalmente e nenhum fit emitiu avisos. Não foram salvos modelos, imputadores, scores de produção ou novos datasets. Os resultados permanecem nas saídas do notebook e nesta documentação.

Verificações finais executadas no ambiente isolado:

- `ruff check .`: **All checks passed!** (cache desabilitado).
- `pytest -q`: **113 passed in 14.78s**, com fixtures sintéticas, cache desabilitado e diretório temporário exclusivo; nenhum teste depende dos datasets Kaggle.
- `git diff --check`: **exit code 0**, sem erros de whitespace; o Git emitiu apenas avisos de conversão futura LF/CRLF, sem normalização forçada.
- Schema do notebook válido; dez células executadas sequencialmente, zero erros, quatro figuras inspecionadas. O fechamento alterou somente Markdown no notebook, preservando código executável e resultados calculados.
- **62 arquivos preexistentes monitorados mantiveram seus SHA-256**, incluindo fontes, dados processados fora de TEST, splits, modelos existentes, scripts, testes e requisitos. O único acréscimo dentro dessas árvores foi o notebook 02.
- Os três Parquets de TEST existentes (Supplier e Invoice) mantiveram tamanho e data de modificação. Seu conteúdo não foi aberto nem para calcular hashes: não se afirma verificação SHA-256 desses arquivos nesta rodada.

Nenhum commit foi criado pelo agente. Na retomada já existia o commit `8e62dbc`, incluindo o notebook experimental; ele foi preservado. O fechamento deixa apenas o novo relatório e alterações documentais/Markdown no diretório de trabalho, sem staging ou commit.
