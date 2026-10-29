# Invoice Anomaly — resultados históricos de VALIDATION

Este documento reúne a baseline de **24/09/2026**, a triagem de **27/09/2026**
e a comparação IF × valor de **28/09/2026**. São etapas distintas, preservadas
com seus métodos, tabelas, limitações e registros técnicos; a consolidação não
recalculou métricas nem produziu nova inferência.

- [Baseline e threshold original](#1-baseline--24092026).
- [Triagem e diagnóstico temporal](#2-triagem-e-diagnóstico-temporal--27092026).
- [Comparação IF--valor](#3-comparação-if--valor--28092026).
- [Integridade e recomendações históricas](#4-registros-técnicos-e-recomendações-históricas).

**Estado vigente:** TEST foi avaliado uma única vez em 18/10/2026. Seu
[resultado oficial](../ml/experiments/invoice_test_final_v1.json) permanece separado
dos três registros de VALIDATION. Os trechos sobre TEST fechado, próximos passos,
HEAD, arquivos novos e resultados de testes abaixo descrevem suas respectivas
entregas históricas, não o estado atual do checkout nem autorização de reexecução.
Consulte o [protocolo vigente](invoice_academic_evaluation_protocol.md).

## 1. Baseline — 24/09/2026

### 1.1. Decisão de prioridade e escopo concluído

Em 24/09/2026, a revisão do checkout `b624204` confirmou:
Invoice tem preparação de 19 features e Isolation Forest salvo; Purchase possui
apenas auditoria/documentação e pastas vazias; backend/frontend são placeholders.
Supplier concluiu sua avaliação acadêmica e ficou fora desta execução.

Foi priorizada a fase 6 do roadmap: medir a baseline Invoice já existente.
Purchase exige antes decidir anomalia vs desfecho, target/horizonte quando
aplicáveis, disponibilidade pré-aprovação, política de moedas e avaliação.
Não foi criado modelo, feature, frontend, serviço ou mecanismo de score combinado.

**Executado:** uma inferência em 30.000 faturas de VALIDATION, zero fits reais,
sem tuning ou alteração de threshold. Invoice TEST e Supplier TEST não foram
carregados. Modelo, metadata, features e datasets existentes foram preservados.
A implementação está em `ml/scripts/avaliar_invoice.py`; o
[protocolo prévio](invoice_validation.md) permaneceu inalterado após a inferência.

### 1.2. Configuração e evidência

- Isolation Forest existente: 200 árvores, contamination=0.22, seed 42, n_jobs=-1.
- Mesmas 19 features ordenadas; IDs, labels e fraud_type excluídos da entrada.
- Score: negativo de score_samples, maior indica maior anomalia.
- Offset original: `-0.5211491197816622`; limiar equivalente do score:
  `0.5211491197816622`.
- Classificação: decision_function < 0; igualdade é normal.
- Execução registrada em `2026-09-24T13:04:00.697102+00:00`.
- Resultado: [invoice_validation_v1.json](../ml/experiments/invoice_validation_v1.json).
- Python 3.14.3, pandas 2.3.3, numpy 2.5.2, scikit-learn 1.9.0,
  joblib 1.6.0 e pyarrow 25.0.1, sem mudanças nos pins do projeto.

SHA-256 do resultado completo:

```text
1218ed395095c69dd8d3439e27b7e1416dfeba68b8f1d9d83328e2c2f27e12f9
```

SHA-256 do protocolo anterior à inferência:

```text
16176cf0ec2a2754b65fc8fb658f1a67791110e65291d66124c1317f014708a6
```

SHA-256 do modelo, preservado antes/depois:

```text
c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b
```

O JSON registra hashes de fonte, features, modelo, metadata, script e contrato
de features, fingerprint dos IDs, versões, parâmetros e regra de score.
Esses hashes identificam os arquivos atuais, mas o metadata antigo não contém
hash dos inputs/ambiente do fit original; não certificam retroativamente sua origem.

### 1.3. Resultados observados

Valores arredondados a cinco casas; precisão completa no JSON, sem recalcular
métricas para produzir este documento. Fraude positiva = is_fraud=1.

| Métrica | Isolation Forest existente | Referência nunca alertar |
|---|---:|---:|
| Average Precision (principal) | 0,31607 | 0,22577 |
| ROC-AUC | 0,57976 | 0,50000 |
| F1-macro | 0,52434 | 0,43638 |
| Balanced accuracy | 0,55423 | 0,50000 |
| Precision fraude | 0,27210 | 0,00000 |
| Recall fraude | 0,49313 | 0,00000 |
| F1 fraude | 0,35069 | 0,00000 |
| Accuracy (complementar) | 0,58773 | 0,77423 |
| Proporção de alertas | 0,40917 | 0,00000 |

Average Precision usa `average_precision_score`, não área trapezoidal da curva PR.
A referência não discrimina as classes: sua AP é a prevalência de fraude
(6.773/30.000). Accuracy sozinha favorece a previsão de normalidade.

Matriz de confusão: linhas reais, colunas previstas, ordem [0, 1].

| | Previsto normal | Previsto anomalia |
|---|---:|---:|
| Real normal | 14292 | 8935 |
| Real fraude | 3433 | 3340 |

O modelo emite 12.275 alertas; 3.340 correspondem às fraudes rotuladas e 8.935
a normais. O FPR sobre normais é 0,38468.
A taxa de alertas em VALIDATION não precisa ser 22%: contamination define o
offset usando TRAIN, não um orçamento fixo de alertas em dados novos.

#### Resultado por tipo informado pela fonte

| fraud_type | Faturas | Fraudes rotuladas | TP | FN | Recall entre fraudes | Normais rotulados | FP |
|---|---:|---:|---:|---:|---:|---:|---:|
| DOC_TAMPER | 230 | 226 | 110 | 116 | 0,48673 | 4 | 0 |
| DUPLICATE | 8 | 8 | 2 | 6 | 0,25000 | 0 | 0 |
| GHOST_SUPPLIER | 1254 | 1224 | 493 | 731 | 0,40278 | 30 | 9 |
| INFLATED | 565 | 553 | 553 | 0 | 1,00000 | 12 | 12 |
| NONE | 23533 | 446 | 159 | 287 | 0,35650 | 23087 | 8873 |
| SPLIT | 4410 | 4316 | 2023 | 2293 | 0,46872 | 94 | 41 |

Recall por tipo usa somente is_fraud=1 daquele grupo; não é precision de
classificação multiclasse. A categoria DUPLICATE contém apenas oito casos;
não sustenta uma conclusão robusta de generalização. INFLATED teve recall 1
nesta amostra, mas também sinalizou seus 12 normais; não significa perfeição
de um detector específico dessa fraude.

#### Fornecedores observados/não observados

As 30.000 faturas possuem supplier_frequency > 0 segundo as estatísticas do
TRAIN geradas pelo pipeline existente. O grupo não observado possui zero casos;
seu recall/FPR são null. Não há evidência de desempenho para fornecedores novos.
Essa classificação depende da semântica da feature, não de uma nova fonte de IDs.

### 1.4. Interpretação e pendências metodológicas

**OBSERVADO:** há ganho de ordenação sobre a referência trivial, mas discriminação
modesta (ROC-AUC 0,57976), recall de fraude 0,49313 e precision de alerta 0,27210.
O volume de falsos positivos é elevado. A configuração não está demonstrada
como útil operacionalmente, e não deve ser apresentada como detector de fraude
pronto. Não se tentou melhorar o resultado nesta execução.

**OBSERVADO — referência de avaliação:** há 446 linhas is_fraud=1 com
fraud_type=NONE; outras 140 têm is_fraud=0 com tipo diferente de NONE.
Esses valores reconciliam exatamente com labels.parquet por invoice_id:
não foram introduzidos pelo join do avaliador. O manifest disponível só
informa versão, data e contagens; não explica a regra de rotulagem.
O script histórico validar_dataset.py já contém verificações dessas combinações;
ele não foi executado, pois carrega a fonte global e não restringe holdouts.

**HIPÓTESES, não conclusões:** a diferença entre tipos pode refletir alinhamento
das features a determinadas anomalias, particularidades de geração ou ruído da
fonte. Não há evidência suficiente para atribuir causalidade, explicar a regra
de labels ou afirmar que trocar o algoritmo resolverá o problema.

**LIMITAÇÕES:** anomalia não é probabilidade de fraude; dados e label não provam
fraude empresarial real; agregações de todo TRAIN não são ponto-a-ponto
temporais; fornecedores já conhecidos dominam a avaliação; não há evidência
externa/temporal, custos de erro definidos ou intervalos de confiança novos.
O artefato legado não identifica por hash seu treinamento original.

## 2. Triagem e diagnóstico temporal — 27/09/2026

**Escopo concluído:** TRAIN/VALIDATION; modelo, offset e 19 features preservados. O enquadramento passou a priorização para revisão humana, sem classificação automática de fraude.

### 2.1. Definição final recomendada

O Invoice Anomaly é um **sistema de priorização de faturas com comportamento
tabular incomum para revisão humana**, inicialmente avaliado de forma retrospectiva
sobre um lote disponível. A unidade é a fatura; a saída é um score de anomalia
e sua posição no ranking. Não é confirmação de irregularidade, probabilidade
de fraude, autorização de bloqueio ou substituição da decisão do auditor.

Isolation Forest estima isolamento no espaço das features, sem aprender a
reproduzir is_fraud. Por isso, ranking para investigação é mais compatível
com seu objetivo do que classificação automática de fraude. Compatibilidade
conceitual não comprova eficácia operacional.

is_fraud permanece uma **referência secundária, imperfeita e não verificada**.
Precision@K neste documento é precisão relativa a essa referência, não porcentagem
de fraudes empresariais comprovadas. Um caso rotulado normal pode ser uma anomalia
útil; um positivo pode não ser estranho nas 19 dimensões observadas. A validade
prática ainda exige julgamento humano independente e contexto de negócio.

A [baseline de 24/09/2026](#1-baseline--24092026), o [protocolo anterior](invoice_validation.md)
e a [auditoria metodológica](invoice_methodological_audit.md) foram preservados.
O novo enquadramento não apaga o resultado limitado do threshold original nem
transforma retrospectivamente métricas de classificação em evidência de produção.

### 2.2. Método registrado antes da execução

O [protocolo de triagem](invoice_triage_protocol.md) foi gravado antes da inferência
e permaneceu inalterado. Usou-se o mesmo artefato Isolation Forest: 200 árvores,
contamination=0.22, random_state=42, n_jobs=-1, mesmas 19 features, sem fit/tuning.

- Score = negativo de score_samples; maior significa maior anomalia.
- TRAIN: 210.000 linhas, somente distribuições descritivas in-sample.
- VALIDATION: 30.000 linhas e 6.773 positivos da referência (22,5767%).
- Orçamentos fixos: 1%, 5%, 10%; K=ceil(n*percentual/100).
- Ranking por score decrescente; empates por invoice_id crescente, nunca pela label.
- Precision@K = positivos selecionados/K; captura = positivos selecionados/6.773;
  lift = Precision@K/prevalência.
- Referência aleatória analítica, sem novo estimador:
  E[positivos]=K*prevalência, E[Precision@K]=prevalência, E[captura]=K/n.
- Datas filtradas antes da materialização e associadas por invoice_id, não por posição.
- Quantis lineares fixados no protocolo; distância máxima entre CDFs empíricas
  apenas descritiva, sem p-value ou afirmação de significância estatística.
- Comparações de períodos internos usam os mesmos orçamentos, mas filas próprias;
  também se informa sua participação na fila global.

Os três orçamentos são cenários de capacidade, **não escolha de threshold**.
Os scores nas fronteiras são descritivos do lote; não foram implantados como
limiares. Não foi escolhido orçamento vencedor ou configuração nova.

### 2.3. Resultados observados: enriquecimento do ranking

| Orçamento | Faturas para revisão | Positivos da referência | Negativos da referência | Precision@K | Captura dos positivos | Lift sobre aleatório | Positivos esperados ao acaso |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1% | 300 | 255 | 45 | 85,00% | 3,76% | 3,76x | 67,73 |
| 5% | 1.500 | 645 | 855 | 43,00% | 9,52% | 1,90x | 338,65 |
| 10% | 3.000 | 980 | 2.020 | 32,67% | 14,47% | 1,45x | 677,30 |

Não ocorreram empates múltiplos nas três fronteiras observadas; a política de
desempate foi mesmo assim testada. Os grupos selecionados são aninhados e as
métricas não são experimentos estatisticamente independentes.

**OBSERVAÇÃO:** os três orçamentos concentram mais positivos do que a referência
aleatória. A menor fila contém 255 positivos em 300 faturas, contra 67,73 esperados
ao acaso. Entretanto, captura somente 3,76% dos 6.773 positivos disponíveis.
Na fila de 10%, a captura sobe a 14,47%, com 2.020 negativos da referência.

**INTERPRETAÇÃO:** há evidência de utilidade potencial para priorizar uma parte
dos casos desta fonte, principalmente os extremos. Isso não sustenta cobertura
global de fraude ou uma taxa garantida de acerto de auditoria. A redução de
volume frente aos 12.275 alertas do offset histórico decorre do orçamento fixado,
não de um aprimoramento do estimador. Não houve comparação otimizada de limiares.

#### Composição: onde está o sinal

Cada célula informa **positivos da referência / faturas selecionadas daquele tipo**,
sem substituir fraud_type por is_fraud. Zeros indicam ausência do tipo na fila.

| fraud_type | Top 1% | Top 5% | Top 10% |
|---|---:|---:|---:|
| DOC_TAMPER | 5 / 5 | 13 / 13 | 29 / 29 |
| DUPLICATE | 0 / 0 | 0 / 0 | 1 / 1 |
| GHOST_SUPPLIER | 2 / 2 | 52 / 53 | 124 / 126 |
| INFLATED | 248 / 251 | 517 / 529 | 548 / 560 |
| NONE | 0 / 42 | 6 / 846 | 24 / 2025 |
| SPLIT | 0 / 0 | 57 / 59 | 254 / 259 |

**OBSERVAÇÃO:** no top 1%, 251 das 300 faturas são INFLATED; 248 dos 255
positivos também são INFLATED (**97,25% dos acertos da referência**).
No top 10%, entram 548 dos 553 positivos INFLATED, mas somente 254 dos 4.316
SPLIT e um dos oito DUPLICATE. Este último denominador é insuficiente para
conclusão robusta por mecanismo. Positivos NONE continuam explicitamente
incluídos, sem tentativa de resolver a ambiguidade da label.

As filas de 1%, 5% e 10% contêm, respectivamente, 3, 21 e 43 combinações
divergentes is_fraud/fraud_type, pela regra da auditoria anterior. Nenhuma foi
corrigida ou removida.

**HIPÓTESE:** o bom topo reflete alinhamento das representações de valor com
INFLATED. A composição observada é compatível com isso, mas não demonstra
causalidade nem que o IF acrescente valor sobre uma regra simples de valor alto.
Na data deste diagnóstico, essa comparação ainda não havia sido executada e exigia definição prévia; a execução posterior de 28/09/2026 está na [seção 3](#3-comparação-if--valor--28092026).

### 2.4. Distribuição dos scores e diferenças temporais

#### TRAIN versus VALIDATION

| Quantil linear | TRAIN | VALIDATION |
|---|---:|---:|
| min | 0,436486 | 0,460485 |
| p01 | 0,455327 | 0,478160 |
| p05 | 0,464497 | 0,486686 |
| p25 | 0,482008 | 0,501935 |
| p50 | 0,497926 | 0,515757 |
| p75 | 0,517864 | 0,533723 |
| p95 | 0,559510 | 0,571894 |
| p99 | 0,605541 | 0,615575 |
| max | 0,694322 | 0,688747 |

A mediana aumenta de 0,497926 para 0,515757. A distância descritiva entre CDFs
é **0,31657**; nenhum score VALIDATION sai do intervalo mínimo/máximo TRAIN.
Portanto, permanecer na faixa de treino não implica ter a mesma distribuição.

**OBSERVAÇÃO:** há deslocamento da distribuição de scores.
**LIMITAÇÃO:** TRAIN é in-sample, e os períodos/composição/referências agregadas
diferem. A distância não isola drift temporal prejudicial, causalidade de uma
feature ou impacto econômico. Não foi executado teste de significância ou
experimento removendo calendário.

#### Janelas parciais de VALIDATION

Setembro representa **14–30/09/2023**, outubro **01–20/10/2023**. Não são meses
completos nem múltiplas replicações temporais. TRAIN cobre 01/01–14/09/2023.

| Período | Faturas | Prevalência | Mediana do score | P@1% interno | P@5% interno | P@10% interno |
|---|---:|---:|---:|---:|---:|---:|
| 2023-09 | 13.970 | 22,49% | 0,516543 | 85,00% | 43,49% | 33,64% |
| 2023-10 | 16.030 | 22,65% | 0,515085 | 84,47% | 42,27% | 31,69% |

As filas internas usam K=140/699/1.397 em setembro e 161/802/1.603 em outubro,
com arredondamento para cima. Não são as mesmas seleções da fila global e não
devem ser somadas como se fossem seu resultado.

| Orçamento global | Setembro na fila | Outubro na fila | Participação de outubro na fila | Taxa selecionada de setembro | Taxa selecionada de outubro |
|---|---:|---:|---:|---:|---:|
| 1% | 136 | 164 | 54,67% | 0,97% | 1,02% |
| 5% | 729 | 771 | 51,40% | 5,22% | 4,81% |
| 10% | 1427 | 1573 | 52,43% | 10,21% | 9,81% |

**OBSERVAÇÃO:** outubro compõe 53,43% da base e aproximadamente 51,40%–54,67%
das filas globais. Suas medianas e Precision@K são próximas às de setembro.

**INTERPRETAÇÃO:** o diagnóstico não confirma a hipótese simplista de que a fila
seja dominada desproporcionalmente por outubro apenas porque esse mês não foi
visto. Isso não exclui efeito do calendário, efeito comum aos dois períodos ou
interações com outras features. Duas janelas parciais não provam estabilidade
sazonal ou ausência de drift.

#### Mudança das features existentes

Não foram criadas features de modelo. O diagnóstico mede somente as 19 colunas
persistidas; máscaras de período/novidade são auxiliares, nunca entradas do IF.

| Feature | Distância CDF TRAIN/VALIDATION | Linhas VALIDATION fora da faixa TRAIN |
|---|---:|---:|
| invoice_amount | 0,00614 | 1 |
| log_invoice_amount | 0,00614 | 1 |
| supplier_age_days | 0,00348 | 0 |
| supplier_frequency | 0,04607 | 0 |
| country_frequency | 0,00570 | 0 |
| amount_vs_supplier_mean | 0,00640 | 0 |
| supplier_amount_zscore | 0,00734 | 6 |
| department_frequency | 0,00388 | 0 |
| amount_vs_department_mean | 0,00689 | 1 |
| supplier_department_frequency | 0,26978 | 3.659 |
| payment_terms_days | 0,00400 | 0 |
| invoice_type_encoded | 0,00237 | 0 |
| submission_hour_sin | 0,00527 | 0 |
| submission_hour_cos | 0,00546 | 0 |
| day_of_week_sin | 0,01147 | 0 |
| day_of_week_cos | 0,02317 | 0 |
| month_sin | 0,94771 | 16.030 |
| month_cos | 0,46637 | 0 |
| is_weekend | 0,00635 | 0 |

As maiores diferenças estão em calendário e frequência fornecedor/departamento.
A distância de month_sin é 0,94771; os 16.030 registros de outubro estão abaixo
do mínimo dessa feature no TRAIN. A codificação cíclica continua matematicamente
coerente, mas não elimina mudanças de suporte. Os quantis completos constam do JSON.

As 3.659 faturas com relação fornecedor/departamento ausente do TRAIN representam
12,20% de VALIDATION. Sua mediana de score é 0,520724; elas somam 41/205/422
faturas nas filas globais de 1%/5%/10% — participação de 13,67%/13,67%/14,07%.
Há sobrerrepresentação descritiva, não explicação causal de falsos positivos.

### 2.5. Suficiência das features e limites restantes

O diagnóstico reforça a necessidade de distinguir **incomum no espaço atual**
de **suspeito segundo o processo de compras**.

| Mecanismo | Cobertura atual | Limitação não resolvida |
|---|---|---|
| Valor inflado | Valor, log, razões e z-score | Sem preço unitário, quantidade, contrato ou referência de preço comparável |
| Duplicação | Perfil individual tabular | Sem comparação documental/pagamentos entre faturas |
| Fracionamento | Valor e frequência de relacionamento | Sem janelas de operações relacionadas e limites de aprovação |
| Fornecedor fantasma | Idade/frequência/cadastro indireto | Sem evidência de existência, vínculo bancário ou prestação efetiva |
| Adulteração | Sinais tabulares indiretos | Sem evidência documental independente avaliada |

Não há autorização para introduzir essas informações automaticamente. Origem,
chaves, disponibilidade antes da decisão e risco de leakage precisariam ser
confirmados. As fontes Supplier/Purchase não possuem integração real comprovada.

Permanecem: 4.847 divergências de labels em TRAIN/VALIDATION; procedência parcial
do fit legado; agregações autorreferentes que usam todo TRAIN; idade cadastral
sem referência temporal comprovada; fornecedores conhecidos nas duas partições;
ausência de ciclo anual completo e de julgamento humano/custos de investigação.
Nenhum desses problemas foi ocultado, corrigido manualmente ou declarado resolvido.

## 3. Comparação IF × valor — 28/09/2026

**Escopo concluído:** exclusivamente VALIDATION. TEST permanecia fechado naquela data.

### 3.1. Objetivo e conclusão

Verificar se o ranking do Isolation Forest existente acrescenta informação à
priorização por valor, à mesma capacidade de revisão. O objetivo continua sendo
**triagem de faturas incomuns para auditoria humana**, não classificação automática
de fraude. `is_fraud` é referência de avaliação sem validade empresarial comprovada.

**Resultado observado:** o ganho líquido do IF é **−40, +7 e +192 positivos**
nos orçamentos fixos de 1%, 5% e 10%, respectivamente. As filas compartilham
aproximadamente 61%–64% das faturas; portanto não são equivalentes, mas têm
sobreposição substancial. O enriquecimento anterior no top 1% não demonstrava,
por si só, vantagem sobre uma regra simples: nessa capacidade a baseline por
valor recupera mais positivos.

**Interpretação:** existe evidência descritiva de complementaridade e ganho
incremental condicionado ao orçamento nesta fonte, sobretudo em SPLIT no top 10%.
Não há superioridade uniforme, escolha de vencedor, recomendação automática de
10% ou prova de benefício empresarial. As evidências anteriores foram preservadas.

### 3.2. Método executado

O [protocolo pré-definido](invoice_value_comparison_protocol.md) foi registrado e
hashado antes da inferência. Esta etapa não refez o planejamento nem escolheu
novos percentuais. Os resultados históricos estão na
[triagem anterior](invoice_validation_results.md#2-triagem-e-diagnóstico-temporal--27092026).

- Coorte única: **30.000 faturas VALIDATION**, 6.773 positivos (22,5767%) e 23.227
  negativos da referência. Mesmos IDs, splits e labels nas duas estratégias.
- IF existente: 200 árvores, contamination=0.22, random_state=42, n_jobs=-1,
  mesmas 19 features. Nenhum fit, mudança do offset ou uso de predict.
- IF ordenado por `-score_samples` decrescente. Baseline por `invoice_amount`
  decrescente, sem valor absoluto ou conversão.
- Valores processados reconciliados exatamente por ID com invoices. Uma única
  moeda não nula: **ZAR**. Não houve mistura de moedas.
- Top 1%, 5%, 10%: K=300, 1.500, 3.000; arredondamento ceil.
  Empates previstos por invoice_id crescente, nunca pela label. Nenhum empate
  múltiplo observado nas seis fronteiras.
- Precision@K=positivos/K; captura=positivos/6.773;
  lift=Precision@K/0,2257666667. Negativo da referência não significa caso
  necessariamente inútil para auditoria.
- Concentração medida em dois universos: todas as faturas selecionadas e somente
  positivos. NONE/ausentes não são reclassificados.
- Comparação pareada dos conjuntos comuns/exclusivos e ganho líquido à mesma
  capacidade. A união não é uma terceira estratégia de igual custo.
- TRAIN: somente IDs/split e hashes para separação/procedência, sem scoring.
  Fontes compartilhadas filtradas antes da materialização. Nenhum TEST dedicado lido.
- Uma nova chamada de score_samples, somente em VALIDATION: necessária porque
  a evidência anterior era agregada. Resumo IF completo, coorte e fingerprints
  das três seleções coincidiram exatamente com a evidência anterior.

### 3.3. Resultados observados: recuperação de positivos

| Orçamento | Estratégia | K | Positivos | Negativos da referência | Precision@K | Captura | Lift |
|---|---|---:|---:|---:|---:|---:|---:|
| 1% | Isolation Forest | 300 | 255 | 45 | 85,00% | 3,76% | 3,76x |
| 1% | Valor | 300 | 295 | 5 | 98,33% | 4,36% | 4,36x |
| 5% | Isolation Forest | 1.500 | 645 | 855 | 43,00% | 9,52% | 1,90x |
| 5% | Valor | 1.500 | 638 | 862 | 42,53% | 9,42% | 1,88x |
| 10% | Isolation Forest | 3.000 | 980 | 2.020 | 32,67% | 14,47% | 1,45x |
| 10% | Valor | 3.000 | 788 | 2.212 | 26,27% | 11,63% | 1,16x |

Em pontos percentuais, IF menos valor em Precision@K: **−13,33; +0,47; +6,40**.
Na captura: **−0,59; +0,10; +2,83**. São diferenças descritivas, sem teste de
significância, intervalo de confiança ou alegação de estabilidade independente.

### 3.4. Sobreposição e ganho incremental

| Orçamento | Casos comuns (positivos) | Casos exclusivos por estratégia | Sobreposição | Jaccard | Positivos só IF | Positivos só valor | Ganho líquido IF |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1% | 189 (187) | 111 | 63,00% | 45,99% | 68 | 108 | -40 |
| 5% | 965 (556) | 535 | 64,33% | 47,42% | 89 | 82 | +7 |
| 10% | 1.832 (662) | 1.168 | 61,07% | 43,95% | 318 | 126 | +192 |

Os exclusivos têm o mesmo número de linhas em cada estratégia, pois os K são
iguais. Por exemplo, no top 10%, o IF troca 1.168 casos por outros 1.168:
obtém 318 positivos exclusivos, mas deixa de recuperar 126 exclusivos do valor.
O ganho líquido é **318 − 126 = 192**, não 318.

A união contém 411/2.035/4.168 faturas e 363/727/1.106 positivos. Esses números
exigiriam capacidade maior que 300/1.500/3.000; não justificam promover a união
como melhoria de igual custo. Nenhuma estratégia combinada foi implementada.

#### Composição dos positivos exclusivos

| Tipo dos positivos exclusivos | IF 1% | Valor 1% | IF 5% | Valor 5% | IF 10% | Valor 10% |
|---|---:|---:|---:|---:|---:|---:|
| DOC_TAMPER | 1 | 2 | 3 | 7 | 9 | 14 |
| DUPLICATE | 0 | 0 | 0 | 0 | 0 | 0 |
| GHOST_SUPPLIER | 2 | 0 | 26 | 28 | 45 | 69 |
| INFLATED | 65 | 106 | 0 | 36 | 0 | 5 |
| NONE | 0 | 0 | 3 | 11 | 11 | 24 |
| SPLIT | 0 | 0 | 57 | 0 | 253 | 14 |

**OBSERVAÇÕES:**

- Top 1%: os 68 positivos só IF incluem 65 INFLATED; os 108 só valor incluem
  106 INFLATED. Existe complemento, porém saldo negativo à mesma capacidade.
- Top 5%: IF encontra 57 positivos SPLIT, ausentes da fila por valor, mas
  sacrifica positivos de outros tipos. O saldo agregado é pequeno: +7.
- Top 10%: 253 dos 318 positivos só IF são SPLIT (**79,56%**);
  valor encontra 14 SPLIT exclusivos. A diferença total de SPLIT nas filas é
  +239, parcialmente compensada por −47 positivos nos demais tipos, resultando
  em +192. Nenhum positivo INFLATED é exclusivo IF nos top 5%/10%.

**INTERPRETAÇÃO:** o IF não é simplesmente a mesma ordenação por valor; introduz
mudanças relevantes na seleção. Isso não identifica qual feature causa o ganho,
não isola informação independente do valor (que já participa das 19 features)
e não demonstra captura causal de mecanismos reais de fraude.

### 3.5. Tipos e concentração

Cada célula: **positivos is_fraud / total de faturas daquele fraud_type**.
Ausência de um tipo aparece como zero, não como dado omitido.

| fraud_type | IF 1% | Valor 1% | IF 5% | Valor 5% | IF 10% | Valor 10% |
|---|---:|---:|---:|---:|---:|---:|
| DOC_TAMPER | 5 / 5 | 6 / 6 | 13 / 13 | 17 / 17 | 29 / 29 | 34 / 34 |
| DUPLICATE | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 1 / 1 | 1 / 1 |
| GHOST_SUPPLIER | 2 / 2 | 0 / 0 | 52 / 53 | 54 / 55 | 124 / 126 | 148 / 150 |
| INFLATED | 248 / 251 | 289 / 294 | 517 / 529 | 553 / 565 | 548 / 560 | 553 / 565 |
| NONE | 0 / 42 | 0 / 0 | 6 / 846 | 14 / 863 | 24 / 2025 | 37 / 2235 |
| SPLIT | 0 / 0 | 0 / 0 | 57 / 59 | 0 / 0 | 254 / 259 | 15 / 15 |

| Orçamento | Estratégia | Tipo dominante em todas as faturas | Participação | Tipo dominante nos positivos | Participação |
|---|---|---|---:|---|---:|
| 1% | IF | INFLATED | 83,67% | INFLATED | 97,25% |
| 1% | Valor | INFLATED | 98,00% | INFLATED | 97,97% |
| 5% | IF | NONE | 56,40% | INFLATED | 80,16% |
| 5% | Valor | NONE | 57,53% | INFLATED | 86,68% |
| 10% | IF | NONE | 67,50% | INFLATED | 55,92% |
| 10% | Valor | NONE | 74,50% | INFLATED | 70,18% |

**OBSERVAÇÃO:** no top 1%, INFLATED representa 97,25% dos positivos IF e 97,97%
dos positivos da baseline por valor. Ambos têm forte concentração no mesmo tipo.
No top 10%, essa concentração cai para 55,92% no IF e 70,18% em valor, enquanto
o diferencial exclusivo IF se concentra principalmente em SPLIT.

**INTERPRETAÇÃO:** diversificação relativa existe, mas não equivale a cobertura
ampla e validada de todos os mecanismos. Não foi criado um limiar pós-resultado
para chamar concentração de excessiva. NONE continua podendo conter positivos,
pois `fraud_type` e `is_fraud` não são semanticamente intercambiáveis.

Os casos com combinação divergente segundo a regra da auditoria anterior são
3/21/43 nas filas IF e 5/27/51 nas filas por valor. Nenhuma label foi corrigida.

### 3.6. Limitações e hipóteses

- A origem/regra empresarial de is_fraud não foi comprovada. Métricas não são
  taxas de fraudes confirmadas, e scores não são probabilidades de fraude.
- Há ambiguidades entre labels e tipos. Positivos NONE foram preservados e não
  tratados como mecanismo conhecido. Duplicação tem poucos exemplos para conclusões.
- VALIDATION já foi usada em diagnósticos anteriores; não é avaliação final
  independente. Os top-k são aninhados, e faturas de um mesmo fornecedor podem
  ser dependentes. Não se afirma significância ou generalização.
- Permanecem as limitações temporais, agregações sobre todo TRAIN, fornecedores
  conhecidos, falta de contexto documental/transacional e procedência incompleta
  do fit legado descritas na [auditoria](invoice_methodological_audit.md).
- Não há custos, capacidade real dos auditores, severidade confirmada, perda
  evitada ou julgamento humano independente. Mais positivos não comprova maior
  utilidade operacional ou retorno financeiro.
- **Hipótese, não causalidade:** outros componentes do perfil tabular podem mudar
  a seleção em favor dos casos rotulados SPLIT. Este experimento não atribui
  importância causal nem autoriza novas features ou ajustes.
- A validade de negócio de `fraud_type` também não é garantida; distribuição
  por tipo é evidência descritiva da fonte.
- A integridade de TEST foi monitorada por tamanho/mtime, não por hash de seu
  conteúdo. Row groups físicos de fontes globais podem ser compartilhados com
  outros splits; os filtros garantem isolamento lógico, não físico.

## 4. Registros técnicos e recomendações históricas

As contagens de testes, ambientes e situações do Git a seguir pertencem às entregas datadas. Os comandos não autorizam repetir análises reais ou executar notebooks; verificar a seleção dos testes antes de qualquer validação técnica.

### 24/09/2026 — baseline: Implementação, validação e integridade

**Nota técnica de 06/10/2026:** os itens abaixo descrevem a execução histórica.
Filtrar IDs não garante isolamento físico dos raw compartilhados; não certifica
ausência de leitura física de TEST. A rota histórica atualmente recusa o checkout
real e é exercitada apenas com fixtures. Não reexecutar nem copiar fontes reais
para contornar a guarda. O [contrato vigente](invoice_academic_evaluation_protocol.md#71-responsabilidades-dos-módulos) mantém
`source_reconciled=false`; os resultados e JSON históricos não foram alterados.

- Avaliador importa o contrato seguro de features sem acionar treino.
- Recusa qualquer split diferente de val antes de I/O.
- Confere schema, tipos, nulos/infinitos, IDs e disjunção train/val, IDs frente ao
  split oficial e labels/fraud_type por ID; não associa linhas por posição.
- Lê labels somente para IDs val e atribuições oficiais somente train/val.
- Valida tipo, parâmetros, número de árvores e features do modelo; divergência
  de versão sklearn interrompe em vez de retreinar.
- Mantém offset original, verifica direção de score e regra de predict;
  gera métricas agregadas, grupos com denominadores explícitos e saída exclusiva.
- Testes novos passaram pelo ciclo RED→GREEN. Validação final de código:
  **38 testes Invoice aprovados em 8,30s**, Ruff dos dois arquivos novos
  `All checks passed!`, pip check sem conflitos. Nenhum teste/experimento
  Supplier foi repetido. A revisão independente não apontou bloqueadores.
- Conferência pós-execução preservou os **51 arquivos protegidos monitorados**,
  incluindo modelo Invoice, artefatos/notebooks Supplier e notebook EDA.
  Arquivos TEST foram excluídos dessa leitura de hashes e não foram abertos.
- Inputs/code/protocolo do JSON conferidos; contagens dos grupos reconciliadas
  com o agregado. Verificação de integridade não executa inferência novamente.

A venv temporária anterior estava incompleta e a principal não conseguia
importar pandas por dependências ausentes. Foi criada uma venv nova separada
com exatamente requirements-dev.txt, sem upgrade/downgrade ou alteração da
venv principal. O ambiente usado naquela etapa era temporário e externo ao
repositório; seu caminho pessoal não é requisito de reprodução.

Ambientes temporários podem ser removidos pelo sistema. Para continuidade técnica,
criar ambiente isolado com os pins do README quando necessário;
não presumir que a venv principal esteja funcional.

### 24/09/2026 — baseline: Encerramento e próximo passo exato

Entregue: avaliador funcional e testado, protocolo prévio, resultado agregado
verificável e documentação do desempenho real. Não há novo modelo nem mudança
de metodologia de treinamento. O JSON não é um modelo serializado de produção.

**Próximo incremento recomendado:** auditoria restrita a TRAIN/VALIDATION da
referência is_fraud versus fraud_type e da procedência do artefato Invoice.
Registrar explicitamente o significado dessas divergências, ou sua ausência
de explicação; verificar limites das transformações e documentar o uso pretendido
antes de definir qualquer experimento de threshold. Não corrigir labels por
suposição, não abrir TEST e não trocar algoritmo para compensar métricas.

Somente depois desse diagnóstico definir antecipadamente objetivo operacional,
métricas/custos, orçamento de comparação em validação e eventual congelamento
para avaliação final autorizada. A baseline atual permanece preservada.
Purchase continua pendente de contrato de problema. Supplier permanece encerrado.

Para validação de código, usar o Python do ambiente isolado:

```powershell
python -I -B -m pytest -q -p no:cacheprovider tests/invoice
python -I -m ruff check ml/scripts/avaliar_invoice.py tests/invoice/test_evaluate_invoice.py --no-cache
git diff --check
```

Para consulta, ler o JSON existente. Não apagar a saída para repetir o comando
de avaliação. Nenhum commit foi criado nesta tarefa.

### 27/09/2026 — triagem: Evidência, qualidade e integridade

Execução registrada em **2026-09-27T16:03:53.267667+00:00**. Nova evidência:
[invoice_triage_validation_v1.json](../ml/experiments/invoice_triage_validation_v1.json).
Contém agregados, parâmetros, versões, hashes, quantis, composição e fingerprints
dos IDs selecionados. Não é um modelo ou dataset de features; não expõe fila
individual de produção.

SHA-256 do protocolo anterior à inferência:

```text
4ebeb61eca2133ac27bfd0c810cee7aaa125d9f36ac485f9b884263a4a4d21eb
```

SHA-256 do resultado:

```text
ff218d45c54c2376d43b0be46bfda93ba8eb438c8ebd72c395e67fe7cfbdfb3d
```

Modelo preservado:

```text
c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b
```

- 20 testes novos, sintéticos: ranking, ceil, empates sem labels, ausência de
  positivos, scores inválidos, CDF, fontes filtradas, datas por ID, ausência de
  fit, modelo incompatível, mudança dos inputs e recusa de sobrescrita.
- Revisões metodológica e de código independentes concluídas antes da execução.
- Suíte final: **283 passed in 14.61s**, usando fixtures temporárias, sem Kaggle,
  treinamento real ou acesso a TEST real.
- Ruff dos dois arquivos novos: **All checks passed!**.
- Ruff completo: **três avisos preexistentes**, não corrigidos por estarem fora
  do escopo Supplier: I001 e RUF100 em ml/supplier_risk/scripts/final_evaluation.py;
  I001 em tests/supplier_risk/test_final_evaluation_artifact.py. Os dois arquivos
  coincidem com HEAD; não foram alterados para fazer a checagem parecer limpa.
- 31 hashes de arquivos protegidos e 36 registros de tamanho/mtime de dados/modelos
  preservados. Entre os hashes: modelo Invoice, evidências históricas, código
  existente e arquivos Supplier, inclusive o notebook EDA protegido.
- Arquivos de dados TEST foram verificados somente por tamanho/mtime, não abertos
  para hash. Fontes globais têm filtros lógicos: não se promete isolamento físico
  dos bytes de row groups compartilhados nem hash completo dessas fontes.
- Agregados, filas por período e hashes registrados reconciliados sem nova inferência.
- git diff --check e verificação de whitespace dos cinco arquivos novos sem erros;
  links locais conferidos. Avisos informativos de conversão LF/CRLF do Git não
  representam alteração dos datasets ou falha de whitespace.
- Nenhum dataset, split, ML-Ready, modelo, label ou feature existente foi alterado.

Python 3.14.3, pandas 2.3.3, numpy 2.5.2, pyarrow 25.0.1, scikit-learn 1.9.0,
joblib 1.6.0; ambiente isolado preexistente, sem instalação ou mudança de pins.
Foi executada uma chamada de score_samples em TRAIN e uma em VALIDATION;
zero fits reais, zero tuning, zero seleção de threshold, zero leitura analítica
de TEST. Supplier Risk/Purchase não foram executados com dados reais.
Não houve notebook, frontend, staging ou commit.

### 27/09/2026 — triagem: Entrega e execução

Criados nesta etapa:

- docs/invoice_triage_protocol.md — contrato anterior à inferência;
- relatório de triagem — hoje incorporado à seção 2 deste documento;
- ml/scripts/diagnosticar_triagem_invoice.py — diagnóstico somente leitura;
- tests/invoice/test_invoice_triage.py — testes sintéticos;
- ml/experiments/invoice_triage_validation_v1.json — resultado exclusivo.

README, roadmap e somente a seção Invoice da estratégia de modelos foram
atualizados para refletir triagem; mudanças locais anteriores foram preservadas.

Comando histórico do diagnóstico, **já executado** (não reexecutar com dados reais):

```powershell
python -m ml.scripts.diagnosticar_triagem_invoice --split val
```

A saída já existe: a reexecução é recusada antes de ler dados. **Nota técnica de
06/10/2026:** o carregador histórico também recusa o checkout real; filtros não
isolam os raw compartilhados de TEST. Não copiar fontes reais para contornar a
guarda de fixtures. Para consulta, ler o JSON; não apagar evidência para repetir.
O fluxo futuro depende do [contrato vigente](invoice_academic_evaluation_protocol.md#71-responsabilidades-dos-módulos).
Comandos de qualidade:

```powershell
python -I -B -m pytest -q -p no:cacheprovider
python -I -m ruff check ml/scripts/diagnosticar_triagem_invoice.py tests/invoice/test_invoice_triage.py --no-cache
git diff --check
```

Usar ambiente isolado funcional com os pins atuais; não presumir que a venv
principal esteja funcional. A venv temporária usada pode ser removida pelo sistema.

### 27/09/2026 — triagem: Próximo passo recomendado

**Conclusão:** há sinal promissor de enriquecimento do topo, concentrado em
INFLATED, mas utilidade de triagem ampla e operacional ainda não está validada.
Nenhum dos três orçamentos foi escolhido para implantação; TEST continua fechado.

O menor avanço útil é definir um **protocolo de utilidade da triagem**, ainda
somente em TRAIN/VALIDATION:

1. Definir quem revisaria faturas, quais evidências sustentam uma anomalia útil,
   instante de uso e capacidade/custo de investigação.
2. Planejar comparação prévia com uma regra simples de priorização por valor,
   para verificar se o IF acrescenta sinal além dos extremos monetários. Não
   escolher regra/orçamento retrospectivamente para maximizar a métrica.
3. Quando houver documentação/evidência de negócio suficiente, revisar amostras
   do topo e uma referência aleatória, com critérios independentes de is_fraud
   e sem revelar o score ao revisor quando viável; distinguir achado útil de fraude.
4. Se esses insumos não existirem, limitar a conclusão acadêmica ao enriquecimento
   observado na referência não verificada. Não simular validação humana ou empresarial.

Depois, e não nesta etapa, decidir se uma comparação controlada de representação
é justificada. Produção e TEST exigem contrato final e autorização próprios.

### 28/09/2026 — comparação: Evidência, validação e integridade

Evidência: [invoice_value_comparison_v1.json](../ml/experiments/invoice_value_comparison_v1.json),
gerada em **2026-09-28T13:49:30.181043+00:00**, com criação exclusiva e sem sobrescrita.
Inclui métricas completas, fronteiras descritivas, conjuntos comuns/exclusivos,
tipos/concentração, hashes de IDs, versões, código/protocolo e inputs.

| Item | SHA-256 |
|---|---|
| JSON do resultado | 9f47cdb9d70ca0cded04aef63cf4e8c1794118b84533fc880f1cba44ab59beea |
| Protocolo anterior à inferência | 259f5155000cd444965f54f461b0287251ac88cb3e41953b3878bec93369b5ec |
| Script executado | 75b6b23ea0b365add1a792bc359d0029168e2bf3cd15dfd775df0d2e55d4e6b3 |
| Modelo preservado | c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b |

Os demais hashes constam do JSON. `selected_ids_sha256` preserva ordem do ranking;
`ids_sha256` nos grupos usa IDs ordenados alfabeticamente para representar o
conjunto. São fingerprints distintos por definição.

- **25 testes novos sintéticos aprovados**: cálculos independentes, ganhos
  negativos/zero/positivos, sobreposição, empates, ausência de positivos, dados
  inválidos, filtros antes da materialização, divergências de fonte/moeda,
  hashes/coorte/seleções anteriores, nenhum fit e recusa de sobrescrita.
- **Suíte completa: 308 passed in 20.82s.** Fixtures temporárias; nenhum treino
  real ou uso dos datasets reais pelos testes.
- Ruff nos dois arquivos novos: **All checks passed!**
- Ruff global: **3 avisos preexistentes**, preservados por estarem fora do escopo:
  I001 e RUF100 em `ml/supplier_risk/scripts/final_evaluation.py`;
  I001 em `tests/supplier_risk/test_final_evaluation_artifact.py`.
- Revisão independente antes da execução: nenhum problema crítico/importante.
  Sugestão menor não bloqueante deixada para manutenção: adicionar caso sintético
  com fonte de valores embaralhada; o realinhamento por ID foi revisado e está correto.
- Reconciliação posterior apenas dos JSONs: métricas IF anteriores, decomposição
  de todos os grupos/tipos e ganhos líquidos; **11 hashes** de inputs/código/
  protocolo conferidos. Nenhuma segunda inferência.
- `git diff --check`: sem erros. Os cinco arquivos novos também foram verificados
  individualmente com `--no-index --check`: nenhuma ocorrência de whitespace;
  status 1 indica arquivos novos/diferentes de /dev/null, não erro de whitespace.
  Links locais, timestamp e hashes citados na documentação conferidos.
- **91 arquivos preexistentes com hashes preservados**; **59 arquivos protegidos
  com tamanho/mtime preservados**, incluindo dados, modelos e Supplier/Purchase.
  Ambos os notebooks locais Supplier 01/02 permaneceram byte a byte inalterados.
- Python 3.14.3; pandas 2.3.3; numpy 2.5.2; pyarrow 25.0.1; scikit-learn 1.9.0;
  joblib 1.6.0. Ambiente isolado preexistente, sem instalar ou alterar dependências.

Nenhum dataset, split, label, feature ou modelo alterado. Zero fits reais,
zero tuning, zero escolha de threshold/orçamento. Nenhum notebook ou execução
real de Supplier/Purchase. Sem frontend, staging ou commit.

### 28/09/2026 — comparação: Arquivos e reprodução

Criados somente nesta etapa:

- [Protocolo](invoice_value_comparison_protocol.md).
- [Comparador](../ml/scripts/comparar_triagem_invoice.py).
- [Testes](../tests/invoice/test_invoice_comparison.py).
- [JSON](../ml/experiments/invoice_value_comparison_v1.json).
- Este relatório.

Nenhum arquivo preexistente foi editado. As alterações locais anteriores continuam
no checkout e não pertencem a esta entrega. HEAD permanece `b624204`, sem staging
ou novo commit; os cinco arquivos desta entrega permanecem não rastreados.

Comando histórico utilizado naquela etapa (não é instrução vigente de reexecução):

```powershell
python -m ml.scripts.comparar_triagem_invoice --split val
```

**A execução atual já terminou.** O comando recusa sobrescrever o JSON existente
antes de acessar dados/modelo; não apagar a evidência para repetir. **Nota técnica
de 06/10/2026:** a rota histórica agora admite somente fixtures externas e recusa
o checkout real, pois filtros de linhas não isolam fisicamente TEST. Não copiar
dados reais para contornar essa proteção. Consultar o JSON preservado e o
[contrato vigente](invoice_academic_evaluation_protocol.md#71-responsabilidades-dos-módulos) para qualquer etapa futura autorizada.
O ambiente principal não foi reparado nem declarado reproduzível naquela etapa.

Verificações sintéticas, sem datasets:

```powershell
python -m pytest -q tests/invoice/test_invoice_comparison.py
python -m ruff check ml/scripts/comparar_triagem_invoice.py tests/invoice/test_invoice_comparison.py
git diff --check
```

### 28/09/2026 — comparação: Próximo passo recomendado — ainda não executado

Manter TEST fechado. Definir um protocolo curto de **revisão humana cega de uma
amostra pré-especificada dos casos comuns e discordantes em TRAIN/VALIDATION**,
com critérios de relevância independentes de score/is_fraud, contexto disponível,
capacidade e custo de investigação. Documentar quando faltarem evidências para
julgar um caso, sem corrigir labels por suposição.

A questão seguinte é se os exclusivos IF — especialmente SPLIT — são úteis para
auditoria, e se compensam os casos sacrificados e o esforço. Somente depois de
fixar finalidade, capacidade por critério externo e conclusões admissíveis,
definir eventual protocolo final antes de qualquer TEST autorizado. Não escolher
10% por ter mostrado maior ganho neste relatório e não promover o modelo a produção.
