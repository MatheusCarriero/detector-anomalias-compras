# Feature Engineering do Supplier Risk Model

## Objetivo e estado atual

O pipeline `ml/supplier_risk/scripts/prepare_features.py`, versão **2.0.0**, gera uma base pré-modelagem com uma linha por fornecedor. Esta revisão substitui a preparação anterior com imputação global.

**`supplier_features_base.parquet` NÃO é uma matriz pronta para ser passada diretamente ao `fit()`.** A base preserva nulos. O split e o ajuste de imputação exclusivamente no treino já foram implementados em scripts separados, gerando os derivados `ml_ready/` sem modificar a base. Nenhum modelo foi treinado e não houve EDA, normalização, padronização, encoding ou clipping. Esta documentação descreve a camada pré-modelagem, não desfaz a preparação ML-Ready concluída posteriormente.

## Fontes e integridade

- Fonte principal: `data/external/supplier_risk/supplier_risk_dataset.csv`.
- Referência, sem participação na consolidação: `data/external/supplier_risk/raw_supplier_risk_dataset_1.csv`.
- SHA-256 da fonte principal na execução validada: `2A772A6AABB65CCA3785CDBC61335D4AD42AFACE2A61F523691ECCC0641D00D2`.

Os CSVs são imutáveis para o pipeline. O hash da fonte principal é conferido antes e depois do processamento em memória, antes de publicar as saídas. Nenhum arquivo em `data/external/` é escrito.

O Procurement KPI é apenas auxiliar do projeto e não participa desta preparação ou do treinamento dos três modelos principais. O Invoice Anomaly e o Purchase Risk mantêm seus próprios domínios e metodologias.

## Unidade de análise e reconciliação

A unidade é o **fornecedor**, identificado por `Supplier_ID`. Na execução validada em 2026-09-07:

| Controle | Resultado |
|---|---:|
| Linhas iniciais | 28.098 |
| Células nulas na fonte | 2.057 |
| Duplicatas exatas removidas | 3.447 |
| Linhas após deduplicação | 24.651 |
| Fornecedores únicos antes da consolidação | 24.112 |
| Fornecedores após a consolidação | 24.112 |
| IDs perdidos / inesperados / duplicados | 0 / 0 / 0 |

A deduplicação compara todas as colunas da fonte, antes da conversão numérica, e remove somente linhas exatas. Não elimina fornecedores com dados incompletos nem registros apenas semelhantes.

A consolidação utiliza a **mediana dos valores presentes da própria feature no próprio fornecedor**. Não busca valores em outros fornecedores. Se nenhum registro do fornecedor tem uma feature preenchida, o resultado daquela feature permanece nulo. Se existe valor conhecido em outro registro do mesmo fornecedor, a agregação pode recuperá-lo; isso não equivale a uma imputação entre fornecedores.

A mediana é uma estratégia intrafornecedor conservadora, mas não identifica estado mais recente, tendência ou pior caso. Na fonte atual, nenhum dos fornecedores repetidos apresenta variação nas nove variáveis numéricas quando as observações comparadas estão preenchidas. Se isso mudar, o contador de variações da execução deve motivar uma revisão da estratégia de consolidação.

O pipeline compara os conjuntos completos de IDs, não apenas suas quantidades, e reconcilia a soma de `supplier_record_count` com as 24.651 linhas deduplicadas.

## Contrato das features

As nove variáveis numéricas anteriores foram preservadas, acompanhadas de `supplier_record_count`. A ordem abaixo é a ordem da base e do metadata:

| Coluna de origem | Feature | Significado / condição |
|---|---|---|
| `Financial_Stability_Score` | `financial_stability_score` | Indicador de estabilidade financeira |
| `On_Time_Delivery_Rate` | `on_time_delivery_rate` | Taxa de entrega no prazo; janela e denominador não comprovados |
| `Defect_Rate` | `defect_rate` | Taxa de defeitos; janela e denominador não comprovados |
| `Geopolitical_Risk_Index` | `geopolitical_risk_index` | Feature provisória sujeita à validação da origem |
| `Lead_Time_Days` | `lead_time_days` | Prazo em dias; significado de zero pendente |
| `Alternative_Suppliers_Available` | `alternative_suppliers_available` | Disponibilidade de fornecedores alternativos |
| `Contract_Length_Months` | `contract_length_months` | Duração contratual em meses |
| `Environmental_Compliance` | `environmental_compliance` | Indicador de conformidade ambiental; escala precisa ser confirmada |
| `Previous_Disruptions` | `previous_disruptions` | Indicador de disrupções anteriores; período não documentado |
| Contagem dos registros deduplicados por `Supplier_ID` | `supplier_record_count` | Quantidade de registros distintos da fonte associados ao fornecedor após a remoção das duplicatas exatas |

O arquivo contém 11 colunas físicas: `supplier_id` como string de rastreabilidade, nove features `float64` e a contagem `int64`. Tipos e ordem efetivos são registrados no metadata. Os valores numéricos mantêm a escala de origem; nomes em `snake_case` são apenas padronização de nomenclatura.

### Interpretação de supplier_record_count

**Definição:** “Quantidade de registros distintos da fonte associados ao fornecedor após a remoção das duplicatas exatas.”

A variável não comprova profundidade ou maturidade histórica, nem quantidade de observações temporais. Não existe dimensão temporal comprovando histórico. Nos 532 fornecedores com múltiplos registros, as diferenças nas variáveis numéricas parecem relacionadas principalmente a preenchimento/incompletude; os valores conhecidos não divergem.

| Registros distintos por fornecedor | Fornecedores |
|---|---:|
| 1 | 23.580 |
| 2 | 525 |
| 3 | 7 |

Sua utilidade será avaliada futuramente em experimento **COM e SEM `supplier_record_count`**, sobre as mesmas partições e o mesmo protocolo. A feature permanece na base candidata, sem alegação de valor preditivo já demonstrado.

## Exclusões e uso de labels

- `Risk_Level`, `Risk_Category` quando existir, e classificações equivalentes não entram nas features.
- `Supplier_ID` não é entrada do modelo. Sua versão `supplier_id` serve somente para rastreabilidade, split e associação futura do score.
- `Risk_Level` é o target definido para a futura classificação supervisionada do Supplier Risk; nunca é feature. A convenção de classes adotada pelo projeto é 0 = menor risco e 1 = maior risco, sem comprovação da origem ou validade operacional da label. Ver [objetivo e limitações](supplier_risk_model.md).
- `Delivery_Quality_Index` e `Supplier_Dependency_Score` continuam excluídos por redundância determinística, não por constituírem automaticamente leakage.
- `Country`, `Region`, `Industry` e `Supplier_Tier` permanecem fora da baseline numérica; nenhum encoding é aplicado.

A auditoria anterior verificou, nos valores válidos e com tolerância de 0,0001:

- `Delivery_Quality_Index = On_Time_Delivery_Rate * (1 - Defect_Rate / 100)`;
- `Supplier_Dependency_Score = 1 / (Alternative_Suppliers_Available + 1)`.

A classificação desses campos não depende de adicioná-los à matriz. A seleção explícita das dez features impede a inclusão automática de labels ou novas colunas.

A avaliação futura das categorias comparará **baseline numérica vs. baseline numérica + categóricas**. Todo encoder deverá ser ajustado somente no treino, com política para categorias desconhecidas.

## Cobertura e qualidade da informação

O arquivo separado `data/processed/supplier_risk/supplier_features_quality.parquet` contém uma linha por feature. Sua finalidade é auditoria, rastreabilidade e controle da qualidade. Ele **não pertence à matriz de treinamento**. Não foram adicionadas flags de missing como features.

A cobertura é `100 * valores_presentes / quantidade_fornecedores`. Para cada feature, presentes + ausentes = 24.112:

| Feature | Presentes | Ausentes | Cobertura |
|---|---:|---:|---:|
| `financial_stability_score` | 23.826 | 286 | 98,81% |
| `on_time_delivery_rate` | 23.952 | 160 | 99,34% |
| `defect_rate` | 23.872 | 240 | 99,00% |
| `geopolitical_risk_index` | 24.112 | 0 | 100,00% |
| `lead_time_days` | 23.936 | 176 | 99,27% |
| `alternative_suppliers_available` | 23.916 | 196 | 99,19% |
| `contract_length_months` | 24.112 | 0 | 100,00% |
| `environmental_compliance` | 23.842 | 270 | 98,88% |
| `previous_disruptions` | 23.954 | 158 | 99,34% |
| `supplier_record_count` | 24.112 | 0 | 100,00% |

São **1.486 nulos preservados na base**, sem valores infinitos. A consolidação não significa que todas as informações do fornecedor foram observadas. A imputação train-only já implementada nos derivados mantém rastreabilidade da ausência original no metadata, sem sobrescrever a base.

## Domínio e outliers

Um **outlier estatístico** depende da distribuição e do critério adotado; um **possível valor inválido de negócio** depende de regras e escalas comprovadas. Um caso não implica automaticamente o outro.

Nesta revisão, não são calculados cortes de IQR, classificações de outlier ou diagnósticos de EDA. São registrados controles descritivos de domínio solicitados, sem corrigir valores por aparência.

| Feature | Mínimo | Máximo | Zeros | Negativos |
|---|---:|---:|---:|---:|
| `financial_stability_score` | 2,671689 | 100 | 0 | 0 |
| `on_time_delivery_rate` | 30,837012 | 100 | 0 | 0 |
| `defect_rate` | 0 | 19,248047 | 2.334 | 0 |
| `geopolitical_risk_index` | 11 | 87 | 0 | 0 |
| `lead_time_days` | 0 | 88 | 1.134 | 0 |
| `alternative_suppliers_available` | 0 | 10 | 2.957 | 0 |
| `contract_length_months` | 1 | 68 | 0 | 0 |
| `environmental_compliance` | 1,52 | 100,95 | 0 | 0 |
| `previous_disruptions` | 0 | 6 | 9.161 | 0 |
| `supplier_record_count` | 1 | 3 | 0 | 0 |

Mínimos e máximos usam somente valores presentes. Na auditoria de uma feature inteiramente ausente, os extremos são nulos, não zero.

### Environmental_Compliance

Há **1.386 fornecedores com valor > 100**, com mínimo **100,10** e máximo **100,95** entre esses casos. Classificação: **“possível inconsistência de domínio pendente de confirmação da escala original”**. Os valores são preservados; não se aplica clipping para 100.

### Lead_Time_Days

Há **1.134 valores iguais a zero** e **nenhum negativo** na base consolidada. O significado de lead time igual a zero precisa ser confirmado. Zeros não são removidos nem substituídos.

O artefato de qualidade registra dtype, extremos, zeros, negativos, ausências e cobertura de todas as features. Valores semanticamente suspeitos são sinalizados, sem inferir novas regras de negócio.

## Geopolitical_Risk_Index provisório

O valor do arquivo `supplier_risk_dataset.csv` é mantido temporariamente porque esse arquivo foi definido como fonte principal.

A auditoria dos dois arquivos correspondentes encontrou 26.520 divergências em 28.098 registros (aproximadamente 94,38%). A cardinalidade observada é 98 na referência bruta e 17 na versão enriquecida; nesta última, cada país possui um único valor observado do índice. Esses resultados não explicam a transformação.

Ainda não estão comprovados:

- fonte original do índice;
- fórmula de enriquecimento;
- data de referência;
- periodicidade;
- metodologia do mapeamento por país.

O ZIP fornecido `Supplier RIsk Assessment Dataset.zip`, inspecionado em 2026-09-07, contém apenas os dois CSVs, sem documentação adicional. Nenhuma origem ou fórmula foi inferida. A feature é explicitamente marcada no metadata como **“feature provisória sujeita à validação da origem”**.

## Validações estruturais

O processamento falha com mensagem clara para fonte vazia, ausência de `Supplier_ID`, ID nulo ou vazio, feature obrigatória ausente, conversão numérica inválida, infinito, perda de fornecedor, ID inesperado ou ID duplicado após consolidação.

A conversão numérica valida cada valor originalmente presente: conversões inválidas não são transformadas silenciosamente em missing. Nulos legítimos são permitidos, inclusive numa feature inteiramente ausente. Os IDs são lidos como strings, preservando sua identidade textual.

Também são verificados o schema ordenado, a contagem inteira positiva de registros, a soma das contagens e a preservação da ausência quando um grupo não possui nenhuma observação válida da feature.

## Preparação para treinamento futuro

```text
Fonte
  ↓
Validação
  ↓
Deduplicação
  ↓
Consolidação por fornecedor
  ↓
supplier_features_base.parquet (nulos preservados)
  ↓
Split train / validation / test                     [script separado]
  ↓
Fit do SimpleImputer(median) somente no train       [ML-Ready implementado]
  ↓
Transform validation / test                        [ML-Ready implementado]
  ↓
Treinamento                                       [futuro]
```

Os parâmetros de imputação devem ser aprendidos apenas no treino. Validação e teste somente aplicam os parâmetros aprendidos. A mesma regra vale para scaling e encoding futuros. Com uma linha por fornecedor, os IDs devem ser disjuntos entre partições; não se deve inventar corte temporal sem datas confiáveis.

As medianas de agregação **dentro de cada fornecedor** não são parâmetros de imputação. O pipeline da base não calcula medianas globais de imputação nem implementa split/transformadores. A [auditoria do target e split](supplier_risk_target_and_split.md) está em `prepare_target_and_split.py`; `build_ml_dataset.py` ajusta o imputador somente no treino e produz os seis arquivos X/y em `ml_ready/`. Treinamento e EDA permanecem futuros, com metodologia supervisionada definida em [Supplier Risk Model](supplier_risk_model.md).

## Artefatos, migração e reprodutibilidade

O pipeline gera:

- `supplier_features_base.parquet`: única base oficial pré-modelagem;
- `supplier_features_quality.parquet`: auditoria separada;
- `supplier_features_base_metadata.json`: contrato e evidências da execução.

O Parquet legado `supplier_features.parquet`, produzido com imputação global, e seu `supplier_features_metadata.json` foram retirados após validar os substitutos. Não devem ser usados como fonte oficial de futuras métricas. O legado é reproduzível pelo código anterior no histórico Git e pela fonte original preservada, mas reintroduzi-lo não corrige o leakage.

Os Parquets permanecem ignorados pelo Git. O novo metadata é versionável e registra versão do pipeline, data UTC, SHA-256 da fonte e saídas, unidade, schema, features ordenadas, exclusões, feature provisória, controles de domínio, cobertura, reconciliação e indicadores explícitos de ausência de imputação, scaling e encoding.

Versões do ambiente verificado: Python 3.14.3, pandas 2.2.2, NumPy 2.5.2, PyArrow 25.0.1 e scikit-learn 1.9.0. A consolidação de qualidade fixou dependências de execução e desenvolvimento nos respectivos requirements, sem upgrades, e persistiu testes em `tests/supplier_risk/test_prepare_features.py`. O ambiente local passa nos testes, mas uma instalação limpa por wheels falha para pandas 2.2.2/Python 3.14; não se alega compatibilidade com outros ambientes. Ver [limitação de reprodução no README](../README.md).

## Decisões ainda pendentes

- Confirmar escala de compliance e significado de prazo zero.
- Validar origem e disponibilidade temporal do índice geopolítico.
- Confirmar procedência e significado das repetições da fonte.
- Avaliar posteriormente o tratamento mediano já aprendido somente no treino, respeitando o [split estabelecido](supplier_risk_target_and_split.md).
- Avaliar, futuramente, a contagem COM/SEM e as categorias COM/SEM em experimentos controlados.
- Confirmar disponibilidade, janelas e denominadores dos indicadores; a classificação atual não deve ser interpretada como previsão temporal ou probabilidade real de falha.
