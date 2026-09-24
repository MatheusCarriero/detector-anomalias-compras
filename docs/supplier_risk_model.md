# Supplier Risk Model

## 1. Objetivo

O Supplier Risk Model será tratado como um problema de **classificação supervisionada** cujo objetivo é estimar o pertencimento de um fornecedor à classe de risco definida pelo dataset, utilizando características do seu perfil operacional, financeiro e de qualidade.

O target é `Risk_Level`, armazenado como `risk_level`, com a convenção adotada pelo projeto:

- classe `0`: menor risco;
- classe `1`: maior risco.

A saída é a classe prevista e, para modelos compatíveis, a **probabilidade estimada de pertencimento à classe de risco**, especificamente à classe 1. Um eventual campo `supplier_risk_score` deverá preservar esse significado e não será chamado de “probabilidade real de ocorrer um problema”. A primeira rodada produziu predições apenas para comparação experimental em VALIDATION; não há modelo definitivo ou saída de produção.

Essa definição substitui a hipótese anterior de tratar Supplier Risk simplesmente como identificação de perfis incomuns. Invoice Anomaly e Purchase Risk conservam seus próprios objetivos e arquiteturas; não há merge direto das features dessas populações distintas.

Esta documentação define o contrato arquitetural do domínio. O pipeline de preparação versão 2.0.0 produz uma base pré-modelagem com nulos preservados. O pipeline ML-Ready versão 1.0.0, descrito na seção 11, deriva conjuntos de treino, validação e teste com imputação aprendida somente no treino, sem alterar essa base. Essas etapas de preparação não treinaram classificadores. Posteriormente foram concluídas a EDA TRAIN, a primeira rodada experimental TRAIN/VALIDATION e a CV exploratória A/D dentro de TRAIN, descritas nas seções 13.8, 15 e 16. O contrato detalhado da base está em [Features do Supplier Risk](supplier_risk_features.md).

## 2. Unidade de análise

A unidade de análise é o **fornecedor**.

O pipeline remove somente duplicatas exatas e consolida pela mediana dos valores presentes de cada variável no próprio fornecedor. Quando não existe valor conhecido, o nulo permanece. Os 24.112 fornecedores são reconciliados por conjunto de IDs, sem perdas. Não há dimensão temporal comprovando snapshots ou histórico.

## 3. Fontes de dados

Diretório:

```text
data/external/supplier_risk/
```

Arquivos disponíveis:

- `raw_supplier_risk_dataset_1.csv`;
- `supplier_risk_dataset.csv`.

A versão enriquecida possui 28.098 registros, 17 colunas e 24.112 fornecedores únicos. A auditoria identificou 2.057 células nulas e 3.447 linhas totalmente duplicadas.

As duas versões compartilham 11 colunas, mas `Geopolitical_Risk_Index` diverge em 26.520 de 28.098 registros (aproximadamente 94,38%). A fonte principal é `supplier_risk_dataset.csv`; o arquivo bruto permanece referência. O valor enriquecido é mantido temporariamente como **feature provisória sujeita à validação da origem**. Fonte do índice, fórmula, data de referência, periodicidade e método de mapeamento por país não estão comprovados. A auditoria anterior encontrou cardinalidade 98 na referência bruta e 17 na enriquecida, com um valor observado por país nesta última: há possível associação forte com `Country`, não evidência de uma metodologia validada de risco geopolítico.

## 4. Features candidatas

O conjunto inicial de variáveis candidatas é:

1. `Financial_Stability_Score`
2. `On_Time_Delivery_Rate`
3. `Defect_Rate`
4. `Geopolitical_Risk_Index`
5. `Lead_Time_Days`
6. `Alternative_Suppliers_Available`
7. `Contract_Length_Months`
8. `Environmental_Compliance`
9. `Previous_Disruptions`
10. `supplier_record_count` (derivada da contagem de registros distintos)

Essas dez features compõem a base candidata numérica, com nomes de saída em `snake_case`. Sua inclusão não comprova utilidade preditiva. Tipos, escalas, disponibilidade temporal e significado de negócio continuam sujeitos às decisões documentadas.

`supplier_record_count` significa: "Quantidade de registros distintos da fonte associados ao fornecedor após a remoção das duplicatas exatas." Não representa profundidade histórica. Os 532 fornecedores repetidos não apresentam variações conhecidas nas nove variáveis numéricas quando preenchidas; as diferenças parecem relacionadas principalmente a preenchimento/incompletude. Pode refletir características do processo de coleta, não características de risco. Sua utilidade será avaliada nos experimentos COM e SEM a feature da seção 13, sem alterar a base atual.

## 5. Campos de contexto

A versão enriquecida também contém:

- `Country`;
- `Region`;
- `Industry`;
- `Supplier_Tier`.

Esses campos permanecem fora da baseline atual, sem encoding. Um experimento futuro comparará baseline numérica vs. baseline numérica + categóricas, com encoder aprendido somente no treino. Também será necessário verificar cardinalidade, categorias raras e comportamento de categorias não observadas.

## 6. Campos proibidos ou condicionados

### 6.1. Target supervisionado e limitação de origem

`Risk_Level` **não deve ser utilizado como feature**.

Esse campo fornece a classificação a ser reproduzida. É consistente por `Supplier_ID`, mas sua origem e regra de construção não foram comprovadas. Não sabemos se representa avaliação humana, regra sintética ou outro processo; sua consistência não comprova validade operacional. Os nomes “menor/maior risco” são a convenção de interpretação adotada nesta decisão, não evidência adicional sobre sua procedência. A label poderá ser usada para:

- análise exploratória somente no TRAIN;
- treinamento supervisionado futuro, apenas como y em TRAIN;
- avaliação da classificação produzida, segundo o protocolo de validation/test;
- comparação entre grupos;
- comparação com baselines, sem fornecer o target como feature.

A mesma restrição deverá ser aplicada a eventuais campos equivalentes, como `Risk_Category`, `Risk_Class`, targets ou classificações derivadas.

A conclusão futura deverá ser formulada como **“capacidade de reproduzir padrões associados à classificação de risco fornecida pelo dataset”**. Não será apresentada como “capacidade comprovada de prever risco real de fornecedores”. Uma métrica alta pode refletir reprodução da regra original da label, não previsão de resultados operacionais; essa possibilidade precisa permanecer explícita.

### 6.2. Identificação

`Supplier_ID` não deve ser apresentado diretamente ao modelo. Ele deverá ser mantido apenas para:

- consolidar a unidade fornecedor;
- detectar duplicidades;
- construir grupos de separação;
- relacionar scores e resultados;
- garantir rastreabilidade.

### 6.3. Indicadores derivados

Os campos abaixo permanecem excluídos por redundância determinística confirmada na auditoria:

- `Delivery_Quality_Index`;
- `Supplier_Dependency_Score`.

`Delivery_Quality_Index` deriva de `On_Time_Delivery_Rate * (1 - Defect_Rate / 100)`. `Supplier_Dependency_Score` deriva de `1 / (Alternative_Suppliers_Available + 1)`. Essas informações não são duplicadas na matriz de features.

## 7. Qualidade e preparação futura

O pipeline da base registra deduplicação, reconciliação, cobertura e domínio em metadata e em `supplier_features_quality.parquet`, separado da matriz. Os nulos são preservados na base, sem imputação, scaling, encoding ou clipping nessa camada. A imputação ocorre somente nos arquivos derivados ML-Ready, conforme a seção 11. Foram encontrados 1.386 fornecedores com compliance > 100 (100,10 a 100,95) e 1.134 com lead time = 0; são pendências sem correção automática. Compliance acima de 100 é uma possível inconsistência de domínio pendente de confirmação da escala original. Lead time zero requer confirmação do significado. Alertas de domínio não são classificações estatísticas de outliers.

Etapas futuras deverão considerar:

- investigação da origem das 3.447 duplicatas exatas já removidas na preparação da base;
- avaliação da imputação mediana já implementada exclusivamente no treino, após o split;
- validação de limites, incluindo scores acima das faixas esperadas;
- validação da origem da versão provisória de `Geopolitical_Risk_Index`;
- análise de distribuições e outliers;
- codificação de variáveis categóricas;
- padronização ou transformação somente quando justificada;
- persistência da ordem das features;
- preservação dos arquivos de origem.

Qualquer remoção, imputação ou transformação deverá acontecer em dados processados, nunca nos CSVs originais.

## 8. Estratégia de separação

Como a unidade de análise é fornecedor, a divisão impede que o mesmo `supplier_id` atravesse os conjuntos. O [protocolo de target e split](supplier_risk_target_and_split.md) já estabeleceu atribuições determinísticas por SHA-256 do identificador, independentes de `Risk_Level`, sem estratificação ou rebalanceamento.

O protocolo atual separa fornecedores entre treino, validação e teste e permite avaliar generalização para IDs não observados no treino. Avaliar novos registros de fornecedores já conhecidos exigiria outro protocolo, que não está implementado. Como o dataset não apresenta dimensão temporal comprovada, não se interpreta esse split como avaliação fora do tempo.

O pipeline ML-Ready reutiliza `supplier_split_assignments.parquet` sem recalcular atribuições: 16.894 fornecedores em `train`, 3.539 em `validation` e 3.679 em `test`, com interseções de IDs iguais a zero.

## 9. Contrato do pipeline futuro

**Entrada:** registros validados do Supplier Risk Assessment Dataset.

**Unidade:** fornecedor.

**Features:** conjunto aprovado após auditoria e preparação.

**Target supervisionado:** `Risk_Level`, nunca como feature.

**Saída planejada:** classe prevista 0/1 e, quando compatível, probabilidade estimada de pertencimento à classe 1.

**Artefatos futuros:** `ml/supplier_risk/models/`.

O pipeline deverá salvar junto ao modelo a lista ordenada de features, parâmetros, estratégia de imputação, categorias aprendidas e metadados da execução.

O artefato oficial pré-modelagem é `data/processed/supplier_risk/supplier_features_base.parquet`, com nulos preservados. Ele **não é uma matriz pronta para o `fit()`**. Seus derivados numéricos para consumo futuro ficam em `data/processed/supplier_risk/ml_ready/`. O fluxo implementado vai da fonte à base com nulos, reutiliza o split por fornecedor e ajusta apenas o imputador no treino, aplicando-o nos três conjuntos. O treinamento de um modelo final continua futuro; classificadores já foram ajustados apenas como experimentos TRAIN/VALIDATION documentados nas seções 15 e 16. A base anterior com imputação global foi descontinuada e não participa desse fluxo.

## 10. Critérios históricos de prontidão e gate atual

Os critérios abaixo foram definidos antes da primeira rodada experimental:

- a representação por fornecedor estiver definida;
- duplicidades e nulos tiverem tratamento documentado;
- a versão de `Geopolitical_Risk_Index` estiver escolhida;
- indicadores derivados tiverem origem auditada;
- `Risk_Level` estiver excluído da matriz de features;
- a divisão entre treino, validação e teste estiver definida;
- testes confirmarem ausência de leakage e estabilidade do esquema.

Preparação, EDA e ajustes experimentais TRAIN/VALIDATION já ocorreram. Isso não significa que todos os pontos de procedência foram resolvidos: a versão enriquecida do índice permaneceu provisoriamente nos cenários A/C e a origem de `Risk_Level` continua desconhecida.

**Gate atual — PLANEJADO:** antes de treino final ou abertura de TEST, extrair os helpers experimentais e o carregador com allowlist para módulos testáveis, revisar procedência, registrar orçamento adicional e congelar explicitamente features, transformações, modelo, parâmetros, seed(s), threshold e eventual calibração. É válido concluir que nenhum candidato é defensável. Não há seleção final nesta documentação.

## 11. Pipeline de preparação para Machine Learning

### Responsabilidade e entradas

O script `ml/supplier_risk/scripts/build_ml_dataset.py`, versão `1.0.0`, prepara os conjuntos ML-Ready sem misturar essa lógica com os pipelines anteriores. Os caminhos partem de `Path(__file__).resolve().parents[3]`.

Entradas obrigatórias em `data/processed/supplier_risk/`:

- `supplier_features_base.parquet`;
- `supplier_targets.parquet`;
- `supplier_split_assignments.parquet`.

A existência dos três arquivos é verificada antes da leitura. Cada tabela precisa conter `supplier_id` textual, não nulo, não vazio e único. Os conjuntos completos de IDs devem coincidir, sem fornecedores ausentes ou inesperados. O target deve ser binário e não nulo; cada split precisa ser válido e não vazio.

As associações são realizadas por `supplier_id`, com joins validados como um-para-um, reconciliação após o merge e verificação de ausência de overlap. A separação reutiliza os valores `train`, `validation` e `test` já atribuídos. O target não decide a partição e não é passado ao imputador.

### Contrato de features

Somente estas dez colunas entram no transformador e nos arquivos `X`, nesta ordem:

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

`supplier_id`, `risk_level` (target originado de `Risk_Level`) e `split` ficam fora de `X`. Colunas ausentes, inesperadas, duplicadas ou não numéricas provocam erro; não há seleção estatística de features nem descarte silencioso. `supplier_record_count` continua candidato para futura comparação COM/SEM, sem interpretação de histórico temporal.

### Imputação e prevenção de data leakage

O único transformador desta versão é `SimpleImputer(strategy="median")`:

```text
Features + targets + split, associados por supplier_id
  ↓
Separar train / validation / test pelas atribuições existentes
  ↓
TRAIN: fit_transform() de um único SimpleImputer(median)
  ↓
VALIDATION: transform() com o mesmo imputador
  ↓
TEST: transform() com o mesmo imputador
  ↓
Validar e salvar X/y separados; nenhum treinamento de modelo
```

As medianas são aprendidas somente nos fornecedores de treino. Validação e teste não participam do ajuste e não provocam novo `fit`. O target também não é utilizado para ajustar a imputação. O método `fit_transform` pode executar internamente a transformação do próprio treino; isso não representa ajuste em holdout.

Se qualquer feature estiver totalmente nula no treino, o processamento é interrompido com os nomes das colunas. Não se buscam medianas em validação/teste, não se aplica um zero arbitrário e não se permite que o imputador descarte a coluna. Uma feature inteiramente ausente apenas em validação ou teste pode ser transformada com a mediana válida do treino.

Não são aplicados `StandardScaler`, `MinMaxScaler`, encoding, seleção estatística de features ou redução de dimensionalidade. Valores já presentes devem permanecer numericamente idênticos, incluindo zeros e valores de domínio ainda pendentes; não há clipping. As únicas substituições permitidas são células ausentes pelas respectivas medianas de TRAIN.

### Saídas e alinhamento

Saídas em `data/processed/supplier_risk/ml_ready/`, verificadas em **2026-09-09**:

| Split | Arquivo X | Arquivo y | Linhas em cada arquivo | Features em X | Nulos antes → depois em X |
|---|---|---|---:|---:|---:|
| `train` | `X_train.parquet` | `y_train.parquet` | 16.894 | 10 | 1.022 → 0 |
| `validation` | `X_validation.parquet` | `y_validation.parquet` | 3.539 | 10 | 231 → 0 |
| `test` | `X_test.parquet` | `y_test.parquet` | 3.679 | 10 | 233 → 0 |

`X` contém somente as dez features em `float64`. A representação numérica uniforme, inclusive de `supplier_record_count`, não é scaling nem altera os valores conhecidos. Cada `y` contém somente `risk_level` em `int8`, binário e não nulo. IDs não são incluídos como coluna nem como índice nos arquivos exportados.

Dentro de cada split, X e y seguem a mesma ordenação textual crescente de `supplier_id`, com `RangeIndex` a partir de zero. A posição de uma linha pode ser rastreada filtrando o arquivo original de atribuições pelo split e ordenando seus IDs. O metadata registra o SHA-256 desse arquivo e um fingerprint da lista ordenada de IDs por partição. Eles devem ser conferidos antes de reconstruir a associação; não se deve alinhar tabelas externas apenas pela ordem física original das linhas.

O arquivo `preprocessing_metadata.json` registra versão, data UTC, features utilizadas/excluídas, método, operações por split, medianas efetivamente aprendidas em TRAIN, quantidades, schemas, nulos antes/depois, reconciliação de IDs, versões de Python/pandas/NumPy/PyArrow/scikit-learn e hashes das três entradas, do script e dos seis Parquets de saída.

Os Parquets são lidos novamente após a gravação para verificar igualdade exata com as tabelas em memória. O metadata é publicado por último. Em uma execução futura que falhe, arquivos anteriores não devem ser considerados resultados da nova entrada: o consumo exige metadata coerente com os hashes das entradas e das saídas atuais.

A base pré-modelagem e os demais inputs continuam inalterados, com seus nulos originais preservados. Os seis Parquets derivados não são versionados no Git; apenas o metadata recebeu uma exceção específica. Nenhum imputador ou modelo foi serializado como artefato adicional nesta tarefa; as medianas ficam registradas para auditoria. Uma integração futura de treinamento/produção deverá persistir e reutilizar o transformador ajustado no treino, sem ajustá-lo em produção.

### Validação, execução e próximos experimentos

```powershell
python ml/supplier_risk/scripts/build_ml_dataset.py
ruff check .
```

Na implementação inicial foram exercitados 39 testes em memória. Agora há uma suíte pytest persistida em `tests/supplier_risk/`, com arquivos para base, target/split e ML-Ready, totalizando **113 testes**. As fixtures usam apenas DataFrames sintéticos, redirecionam I/O para `tmp_path` e não acessam os datasets reais. O caso de leakage usa TRAIN `[1, 2, NaN]`, validation `[1000, NaN]` e test `[2000, NaN]`: a mediana esperada é 1,5 nos três conjuntos. A instrumentação confirma um único `fit` no treino por execução; mudanças nas labels e extremos de holdout não alteram as medianas aprendidas. Também são testados reordenação, alinhamento X/y, entradas inválidas e reexecução equivalente dos Parquets temporários.

As saídas possuem schemas esperados, mesma quantidade de linhas entre X/y, zero nulos, zero infinitos e nenhuma coluna inteiramente nula. Não houve perda de fornecedores. Ruff: `All checks passed!`.

Na etapa original de preparação, o único ajuste foi o do transformador de imputação; nenhum modelo preditivo ou EDA foi criado naquela entrega. Posteriormente foram executadas a EDA TRAIN e rodadas experimentais, sem modificar os Parquets. A preparação numérica e os experimentos não resolvem as pendências de procedência do índice geopolítico, domínio de compliance/lead time ou validade operacional de `Risk_Level`.

Futuras comparações entre modelos devem reutilizar este split, manter qualquer aprendizado de transformações restrito ao treino e reservar teste para avaliação final. A seção 13 define antecipadamente o scaling da Logistic Regression e as ablações; nada disso altera os Parquets atuais. Alternativas de imputação e categorias ficam para fases posteriores, sem usar resultados do teste para escolher a configuração.

## 12. Anomalia, risco e limites de interpretação

**Anomalia** é um perfil estatisticamente incomum. Um fornecedor anormal pode ser excepcionalmente ruim ou excepcionalmente bom. **Risco** é uma classificação atribuída conforme uma definição de risco. Portanto, Supplier Risk não será definido simplesmente como detecção de anomalia: será classificação supervisionada de `Risk_Level`.

O modelo atual não pretende:

- prever acontecimentos futuros;
- prever fraude;
- detectar automaticamente eventos futuros de ruptura;
- medir uma probabilidade real de falha;
- validar risco empresarial real;
- substituir avaliação humana de fornecedores.

O dataset não possui sequência temporal adequada para previsão futura. Essa limitação não é resolvida pelo split por fornecedor, nem pela imputação. Nenhum cenário de previsão de acontecimentos futuros será implementado nesta fase. Também permanecem as incertezas de origem do índice geopolítico, escala de compliance e significado de lead time zero. `supplier_record_count` continua representando somente registros distintos após deduplicação, não histórico temporal.

## 13. Protocolo experimental pré-definido — IMPLEMENTADO EM PARTE

**Protocolo 1.0, registrado em 2026-09-14, antes de EDA ou resultados de classificadores.** Esta seção conserva as regras originais e anota o que já foi executado; os resultados permanecem nas seções 15 e 16. Ela não autoriza mudanças nas fontes e não modifica os artefatos existentes. Qualquer revisão deverá ser registrada antes de observar os resultados afetados, com motivo e versão; nunca será justificada por desempenho no TEST.

### 13.1. Papéis dos conjuntos e sequência

| Conjunto existente | Uso permitido no experimento futuro | Restrições |
|---|---|---|
| TRAIN — 16.894 fornecedores | EDA, ajuste dos transformadores e treinamento; CV interna opcional | Não usar outros conjuntos para aprender imputação/scaling/encoding |
| VALIDATION — 3.539 fornecedores | Comparar modelos e features, selecionar hiperparâmetros e threshold se necessário | Não incorporar suas linhas ao ajuste do classificador no protocolo inicial |
| TEST — 3.679 fornecedores | Avaliação final única da configuração congelada e comparação com a baseline congelada | Proibido usar em EDA, seleção de features/modelo, tuning, threshold ou calibração |

As atribuições SHA-256 por `supplier_id` permanecem congeladas, independentes de `Risk_Level`. Nenhum split será recalculado para favorecer métricas. A auditoria estrutural e de hashes já realizada não é seleção de modelo; estatísticas previamente documentadas do TEST não deverão orientar escolhas futuras.

```text
EDA somente no TRAIN
  ↓
Baseline 0: classe majoritária de TRAIN
  ↓
Baseline 1: Logistic Regression — conjuntos A/B/C/D
  ↓
Primeiro candidato não linear: RandomForestClassifier — conjuntos A/B/C/D
  ↓
Comparação em VALIDATION por F1-macro e critérios mínimos de utilidade
  ↓
Congelar features, transformadores, modelo, hiperparâmetros e threshold
  ↓
Uma avaliação final em TEST, sem realimentar a seleção
```

O protocolo inicial não prevê refit em TRAIN + VALIDATION. Se o resultado final for insatisfatório, relatá-lo como tal; não repetir escolhas com base no mesmo TEST. Uma nova rodada exigiria revisão explícita do protocolo e uma estratégia de avaliação independente.

### 13.2. Ablações obrigatórias

O conjunto A corresponde à lista ordenada das dez features da seção 11. B, C e D removem somente as colunas indicadas, preservando a ordem relativa das demais. Nenhuma coluna será removida dos Parquets nesta tarefa.

| Experimento | Features | Exclusões em relação a A | Pergunta experimental |
|---|---:|---|---|
| A — base completa | 10 | Nenhuma | Qual é a referência usando o contrato atual? |
| B — sem índice geopolítico | 9 | `geopolitical_risk_index` | Quanto o desempenho depende da feature de procedência não comprovada? |
| C — sem contagem | 9 | `supplier_record_count` | A contagem de registros agrega informação útil? |
| D — sem as duas | 8 | `geopolitical_risk_index`, `supplier_record_count` | Como se comporta a alternativa mais conservadora? |

Comparar A/B/C/D dentro de cada família de classificador, com os mesmos fornecedores, tratamento de nulos, protocolo de avaliação e orçamento de tuning. A baseline majoritária é comum às ablações, pois não depende de features. Seleção exclusivamente em VALIDATION; não executar as quatro alternativas em TEST para escolher a melhor. Não trocar a versão da fonte geopolítica no meio de uma comparação.

### 13.3. Baselines e primeiro candidato

**Baseline 0 — classe majoritária:** aprender a classe mais frequente exclusivamente em `y_train` e predizê-la para todos os fornecedores avaliados. Essa classe deve ser calculada, não fixada a partir de validation/test. A referência não demonstra risco real; serve para medir ganho sobre uma estratégia trivial.

**Baseline 1 — Logistic Regression:** primeiro classificador real, com o fluxo conceitual obrigatório abaixo dentro de um `sklearn.pipeline.Pipeline`:

```text
SimpleImputer(strategy="median") → StandardScaler → LogisticRegression
```

**PROTOCOLO ORIGINALMENTE PLANEJADO:** imputador e scaler seriam ajustados somente em TRAIN e, na CV, somente no subtreino de cada fold. **EXECUÇÃO REGISTRADA:** essa regra foi aplicada nos Pipelines experimentais de Logistic Regression da primeira rodada e da CV A/D. O ML-Ready atual continua sem scaling e não foi sobrescrito. Para executar novamente o pipeline completo, usar a base com nulos filtrada pelos IDs de TRAIN e preservar a fronteira por fold.

**Primeiro modelo não linear — RandomForestClassifier:** candidato para relações não lineares em dados tabulares, já disponível no scikit-learn, sem dependência externa. Usará imputação mediana train-only dentro de Pipeline; StandardScaler não é exigido para esse candidato. Importâncias podem apoiar a análise, mas não comprovam causalidade e precisam ser interpretadas com cautela diante de cardinalidade, correlações e proxies.

Gradient Boosting permanece hipótese posterior, não primeiro candidato desta rodada. XGBoost não será incluído; somente uma justificativa experimental futura poderá motivar essa dependência. Hiperparâmetros iniciais, seeds, grades, número de tentativas e critérios de parada deverão ser registrados antes de executar os classificadores. Não são escolhidos nesta tarefa nem há busca aberta guiada por TEST.

### 13.4. ML-Ready e cross-validation

**IMPLEMENTADO:** o ML-Ready tem imputação ajustada no TRAIN completo e aplicada a validation/test. Continua válido para experimentos simples com essa separação fixa e sem novo aprendizado em holdout.

**IMPLEMENTADO na validação científica A/D:** a CV partiu de `supplier_features_base.parquet`, selecionou somente `split == train` por `supplier_id`, associou os targets e passou os valores ainda nulos a um Pipeline contendo imputador, StandardScaler e Logistic Regression. Cada fold aprendeu seus próprios parâmetros exclusivamente no subtreino, com ambas as classes e IDs disjuntos entre ajuste e validação interna.

**PLANEJADO para qualquer CV futura:** reutilizar helpers testáveis com as mesmas fronteiras, registrar previamente o particionamento/orçamento e não ampliar cenários após observar resultados.

Não usar `X_train` previamente imputado como entrada direta dessa CV: as medianas do TRAIN completo já viram os folds que seriam validação interna. Nenhum fold de CV pode incorporar VALIDATION ou TEST oficiais. O mesmo princípio vale para seleção de features, scaling e encoding futuros. Ao terminar a seleção interna, ajustar o pipeline escolhido no TRAIN completo e avaliar em VALIDATION.

### 13.5. Métricas pré-definidas

**Métrica principal: F1-macro**, média não ponderada dos F1 das classes 0 e 1. A distribuição aproximada 30%/70% motiva dar peso equivalente às duas classes. Accuracy pode ser reportada, mas não decide a seleção.

Métricas secundárias obrigatórias:

- precision, recall e F1 da classe 0;
- precision, recall e F1 da classe 1;
- balanced accuracy;
- ROC-AUC;
- PR-AUC, com convenção explícita;
- confusion matrix com linhas = classe real e colunas = classe prevista, ordem `[0, 1]`, além do suporte de cada classe.

Convenções: classe positiva = 1; cálculo binário das métricas de ranking com score contínuo da classe 1, nunca somente com rótulos previstos. Para tornar PR-AUC inequívoca, esta rodada reportará **Average Precision (AP, `average_precision_score`)**, identificada como tal, sem confundi-la com integração trapezoidal da curva precision-recall. Precision/F1 indefinidos por falta de previsões de uma classe serão reportados como zero (`zero_division=0`) e acompanhados da matriz, sem ocultar o problema. F1-macro sempre inclui explicitamente as duas classes. Um conjunto de avaliação com somente uma classe invalida comparações que dependem de ambas; não atribuir um ROC-AUC fictício.

### 13.6. Critério mínimo de utilidade e seleção

Um candidato somente poderá ser considerado útil **no experimento** se, comparado à baseline majoritária nos mesmos fornecedores de VALIDATION:

1. tiver F1-macro superior;
2. tiver balanced accuracy superior;
3. demonstrar identificação de ambas as classes, sem recall/F1 nulo em qualquer uma;
4. não obtiver aparente vantagem apenas prevendo majoritariamente classe 1;
5. apresentar ganho claro, não somente uma diferença nominal possivelmente explicada por variação amostral.

Não é imposto um alvo arbitrário, como F1 de 90%. Para quantificar a clareza do ganho, o primeiro experimento executou bootstrap pareado por fornecedor em VALIDATION, comparando as predições do candidato e da baseline: 2.000 reamostragens, seed 42, IC percentil de 95% para as diferenças de F1-macro e balanced accuracy. Se o intervalo incluir zero em qualquer uma, o ganho será tratado como inconclusivo. Reamostragens sem ambas as classes não terão métricas inventadas; sua frequência deverá ser registrada. Essa análise não refez treinamento e não corrige o viés de uma busca excessiva no mesmo validation; o orçamento de novos experimentos precisa ser limitado e documentado.

Entre candidatos elegíveis, selecionar pelo maior F1-macro em VALIDATION. Em empate exato, considerar balanced accuracy, depois a alternativa mais conservadora na ordem D/B/C/A e, por fim, Logistic Regression antes de Random Forest. Se nenhum satisfizer os critérios, registrar ausência de evidência de utilidade e não declarar um vencedor útil por obrigação. Threshold inicial será 0,5 para a probabilidade da classe 1; qualquer otimização posterior de threshold exige grade/regra registrada antes da comparação, usa somente VALIDATION e respeita os mesmos critérios.

Esses critérios demonstram ganho contra a classificação trivial, não validade empresarial ou um patamar operacional de precisão/recall. Esse último dependeria de custos e consequências dos erros, ainda não definidos. A avaliação final usa a configuração congelada, a mesma definição de métricas e a baseline determinada por TRAIN; não serve para escolher outro candidato.

### 13.7. Probabilidades e calibração — PLANEJADO

`predict_proba()` não será automaticamente interpretado como probabilidade confiável. A única semântica permitida é **probabilidade estimada de pertencimento à classe 1**, não probabilidade real de falha, fraude, ruptura ou outro problema futuro.

Antes de exibir percentuais como "82% de pertencimento à classe de risco", avaliar calibration curve e Brier score; considerar `CalibratedClassifierCV` quando justificado. Brier score isolado não mede apenas calibração. Caso haja ajuste de calibração, registrar o protocolo antes da execução e utilizar somente dados de desenvolvimento: preferencialmente CV dentro de TRAIN com o Pipeline completo, para não calibrar sobre as mesmas predições usadas para treinar o classificador. VALIDATION compara a solução; TEST nunca ajusta calibrador nem escolhe seu método. Nenhuma calibração foi implementada nesta tarefa.

### 13.8. EDA somente no TRAIN — protocolo e execução

Investigar distribuição de `Risk_Level`, estatísticas e distribuições das features, outliers, diferenças entre classes, correlações, possíveis proxies e comportamento do índice geopolítico e da contagem. Analisar ausência e valores de domínio suspeito sem excluí-los automaticamente. Utilizar a base com nulos e apenas os IDs de TRAIN; qualquer associação a campos de contexto deve continuar restrita a esses IDs. Country/Region/Industry/Supplier_Tier não entram automaticamente nas features.

Não observar TEST na EDA. No fechamento original do protocolo não havia sido executada EDA, ablação, calibração ou estimativa de desempenho. **Em 16/09/2026, a primeira EDA foi executada somente nos 16.894 fornecedores TRAIN**, sobre a base pré-imputação. [Relatório e limitações](supplier_risk_eda.md); [notebook executado](../ml/supplier_risk/notebooks/01_supplier_risk_eda.ipynb). A/B/C/D não foram alterados; os dez campos, targets, splits e seis Parquets ML-Ready permanecem intactos. Nenhum classificador foi treinado e nenhuma decisão final de modelo foi tomada.

### 13.9. Referências técnicas do protocolo

- [Prevenção de leakage e Pipeline — scikit-learn](https://scikit-learn.org/stable/common_pitfalls.html): transformadores aprendidos somente no treino, inclusive dentro da CV.
- [Average Precision — scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html): convenção de AP, distinta da integração trapezoidal da curva PR.
- [Calibração de probabilidades — scikit-learn](https://scikit-learn.org/stable/modules/calibration.html): limites de predict_proba, curvas de calibração e avaliação probabilística.

## 14. Qualidade e reprodução do ambiente

`pytest -q` executa os testes sintéticos sem Kaggle e sem treinamento de classificadores. Os testes não dependem da instalação de XGBoost ou matplotlib. Os scripts de produção não precisaram de refatoração; seus resultados e regras foram preservados. A execução local da suíte aprovou 113 testes em aproximadamente 5 segundos, e `ruff check .` aprovou todas as verificações.

Python suportado nesta validação: **3.14.3**, registrado em `.python-version`. Dependências de execução e transitivas são fixadas em `requirements.txt`; pytest, Ruff e transitivas de testes ficam em `requirements-dev.txt`. A correção controlada de 2026-09-16 alterou somente pandas de 2.2.2 para 2.3.3 após instalação e testes em ambiente isolado; não houve atualização automática das demais dependências.

No fechamento de 14–15/09/2026, os mesmos 113 testes sintéticos passaram em 3,74 segundos; Ruff e `git diff --check` passaram. Foi utilizado diretório temporário novo via `PYTEST_ADDOPTS/--basetemp`, sem cache pytest no repositório, devido ao erro de permissão observado anteriormente no diretório temporário padrão do Windows. Não houve alteração de testes ou scripts; apenas o imputador dos casos sintéticos é ajustado pelos testes, nunca um classificador.

Em 2026-09-14, `.python-version` estava versionado, não ignorado e ausente somente no diretório de trabalho; foi restaurado ao conteúdo do HEAD, `3.14.3`. A causa da exclusão local não foi comprovada. Não houve mudança da versão suportada.

**Histórico:** a `.venv` antiga reutiliza pacotes externos (`--system-site-packages`). As sondagens de 14–15/09/2026 com Python 3.14.3 e 3.13.14 falharam ao resolver pandas 2.2.2 por wheels; naquele momento a reprodução limpa não estava comprovada e a CI não havia sido configurada.

**IMPLEMENTADO em 2026-09-16:** instalação completa por wheels em venv temporária nova, Windows x64 / Python 3.14.3, `include-system-site-packages=false`, pandas 2.3.3 e os outros 21 pins preservados. Pacotes pertencentes à venv, user-site desabilitado e `pip check` sem conflitos foram verificados. **113 testes sintéticos passaram em 4,09 segundos**, Ruff aprovado, sem alterações nos scripts ou testes. A `.venv` principal continua intacta com pandas 2.2.2; o novo ambiente não a substituiu automaticamente.

**CI configurada:** `.github/workflows/quality.yml` cria ambiente isolado e executa instalação, `pip check`, Ruff e pytest, sem datasets Kaggle ou treinamento. **PENDENTE:** primeira execução remota após um futuro envio ao GitHub. Python 3.13.14/3.14.4, Linux, macOS e compilação a partir da fonte continuam sem validação do projeto com os requisitos atuais.

**LIMITAÇÃO:** a comprovação do ambiente cobre instalação e suíte sintética, não reprodução integral ou equivalência bit a bit de modelos/datasets reais. A base, targets, splits, ML-Ready e seus metadados históricos não foram alterados. A EDA TRAIN foi concluída posteriormente nesta mesma data, conforme seção 13.8; a primeira rodada de baselines/ablações foi executada depois, conforme seção 15, sem avaliar TEST ou criar modelo definitivo. As ferramentas opcionais de notebook foram instaladas apenas no ambiente isolado. Ver [registro de ambiente no README](../README.md#instalação).

## 15. Primeira rodada experimental — IMPLEMENTADO

O [notebook 02](../ml/supplier_risk/notebooks/02_supplier_risk_baseline_models.ipynb) executou nove fits: baseline majoritária, Logistic Regression A/B/C/D e Random Forest A/B/C/D. Usou somente os quatro Parquets ML-Ready de TRAIN/VALIDATION; TEST permaneceu fechado. Configurações fixas, sem tuning, seleção de threshold, calibração ou serialização de modelos. A seção 13 conserva o protocolo registrado antes dos resultados; esta seção registra a execução, sem reescrever retrospectivamente seus critérios.

**RESULTADO OBSERVADO:** na configuração A, F1-macro de 0,40700 para a baseline, 0,92955 para LR e 0,91538 para RF. As oito configurações superaram a referência trivial em F1-macro e balanced accuracy e reconheceram ambas as classes. Os intervalos bootstrap pareados dos ganhos contra a baseline ficaram acima de zero. RF A não superou LR A nesta rodada.

**INTERPRETAÇÃO/LIMITAÇÃO:** remover o índice geopolítico reduz o F1-macro em aproximadamente 14,30 pontos percentuais na LR e 13,57 na RF; sua procedência segue não comprovada. A contagem não mostrou ganho claro. Estabilidade financeira e índice geopolítico dominam coeficientes/importâncias, compatíveis com as associações da EDA, sem provar causalidade ou a construção da label. Não há vencedor definitivo, validação empresarial ou probabilidade calibrada.

O ML-Ready já estava imputado a partir de TRAIN. O SimpleImputer de cada Pipeline foi fitado apenas em TRAIN, com transformação neutra nesses dados sem nulos; o scaler da LR foi aprendido apenas em TRAIN. Não houve CV nessa primeira rodada; a seção 16 registra a CV posterior que partiu corretamente da base com nulos.

O [relatório completo](supplier_risk_baseline_models.md) contém dados, parâmetros, métricas por classe, ablações, incerteza, limitações e próximos experimentos. A próxima etapa exige revisão da evidência e das pendências de origem; esta rodada não autoriza a abertura de TEST nem a seleção automática de uma versão final.

## 16. Validação científica exploratória — IMPLEMENTADO

O [notebook 03](../ml/supplier_risk/notebooks/03_supplier_risk_validation_analysis.ipynb) e seu [relatório](supplier_risk_validation_analysis.md) executaram uma validação adicional sem TEST:

- CV de cinco folds estratificados somente dentro de TRAIN, comparando LR A e D;
- Pipeline novo por fold, com imputação e scaling ajustados apenas no respectivo subtreino;
- controle negativo com uma permutação de labels;
- reprodução diagnóstica da LR A anterior em VALIDATION e análise pós-hoc de erros;
- 21 fits experimentais, sem tuning, serialização, calibração ou treino final.

**RESULTADO OBSERVADO:** A obteve F1-macro médio `0,92683 ± 0,00624`; D, `0,79729 ± 0,00929`. A foi superior em todos os cinco folds. Com labels embaralhadas, ambos os cenários caíram para balanced accuracy `0,50000` e ROC-AUC aproximadamente `0,50`.

**INTERPRETAÇÃO:** existe evidência adicional de sinal classificatório e de consistência nessa partição interna. O controle negativo é favorável como teste de sanidade, mas não prova ausência absoluta de leakage: a própria label pode ter sido construída a partir das features. A comparação A/D também não isola o efeito de cada variável removida.

**LIMITAÇÕES:** uma fonte, uma estratificação, nenhuma validação temporal/externa, probabilidades não calibradas e diagnóstico de VALIDATION pós-hoc. Predições individuais da primeira rodada não foram persistidas; a reprodução confirmou agregados e coeficientes, não igualdade bit a bit com um vetor histórico inexistente. Nenhum vencedor, feature set final ou threshold foi escolhido. TEST permanece congelado.

## 17. Evidência futura e próximos gates

**IMPLEMENTADO:** o [contrato de registros experimentais](supplier_risk_experiment_records.md) disponibiliza uma API/CLI JSON, somente biblioteca padrão, para gravar e verificar novas predições TRAIN/VALIDATION. Um arquivo representa um estimador/configuração/cenário; schemas, IDs, allowlist, hashes e digest são validados. O helper não carrega dados/modelos, não aceita TEST nesta versão e ainda não possui registros experimentais reais.

**LIMITAÇÃO:** checksum verifica consistência interna, não é assinatura ou atestado de procedência. Hashes esperados são fornecidos pelo chamador e não provam que TEST nunca foi lido. Nenhum registro histórico foi fabricado.

**PLANEJADO antes do próximo experimento:** extrair helpers de cenários, métricas, alinhamento e carregamento allowlisted para módulos testáveis; tornar notebooks futuros consumidores finos; preservar notebooks históricos sem refatoração retroativa. A publicação dos pipelines também deverá evoluir de escritas sequenciais para promoção transacional de conjuntos completos, porque uma falha hoje pode deixar saídas antigas e novas misturadas.

O [roadmap completo](implementation_roadmap.md) define responsáveis e gates. O caminho Supplier conserva: seleção apenas em desenvolvimento → congelamento explícito → ajuste em TRAIN → avaliação final única em TEST, sem refit TRAIN + VALIDATION. Resultado de TEST não realimenta a seleção.

## 18. Configuração final acadêmica — congelada antes de TEST

As seções 15–17 registram o estado histórico antes da autorização final; a
presente seção registra a decisão posterior, ainda sem consultar TEST.
Pela regra previamente definida na seção 13.6, foi selecionada **Logistic
Regression, cenário C**, com nove features, excluindo somente
`supplier_record_count`. A e C possuem a mesma matriz de confusão em VALIDATION
(`[[979, 131], [81, 2348]]`); o desempate D/B/C/A favorece C. A CV anterior avaliou
A e D, não C: não se atribui retrospectivamente validação cruzada ao cenário C.

Configuração: SimpleImputer com mediana → StandardScaler → LogisticRegression,
`C=1.0`, `solver="lbfgs"`, `max_iter=1000`, `random_state=42`, sem pesos de classe,
sem tuning, sem calibração e com `predict()` padrão (corte 0,5; empate favorece 0).
O ajuste permanece **somente em TRAIN**; não haverá refit TRAIN + VALIDATION.
O ML-Ready conserva a imputação aprendida em TRAIN, como na rodada de seleção;
o scaler e o classificador serão ajustados exclusivamente em TRAIN.

**IMPLEMENTADO:** executor testado com dados sintéticos, contrato separado de
evidência final, congelamento com hashes e versão do código, bloqueio de
reexecução e publicação consistente dos registros. Os notebooks e experimentos
históricos não foram refatorados nem reexecutados. O status real, os hashes e
os resultados autorizados são mantidos no
[relatório final acadêmico](supplier_risk_final_evaluation.md).

**LIMITAÇÃO:** a avaliação mede a classificação de Risk_Level dessa fonte, não
risco empresarial comprovado nem previsão de fraude/falha. A label e o índice
geopolítico continuam sem procedência comprovada. TEST não poderá realimentar
nenhuma escolha, mesmo se o resultado for desfavorável.
