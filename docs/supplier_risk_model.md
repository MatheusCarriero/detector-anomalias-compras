# Supplier Risk Model

## 1. Objetivo

O Supplier Risk Model será tratado como um problema de **classificação supervisionada** cujo objetivo é estimar o pertencimento de um fornecedor à classe de risco definida pelo dataset, utilizando características do seu perfil operacional, financeiro e de qualidade.

O target é `Risk_Level`, armazenado como `risk_level`, com a convenção adotada pelo projeto:

- classe `0`: menor risco;
- classe `1`: maior risco.

A saída futura será a classe prevista e, para modelos compatíveis, a **probabilidade estimada de pertencimento à classe de risco**, especificamente à classe 1. Um eventual campo `supplier_risk_score` deverá preservar esse significado e não será chamado de “probabilidade real de ocorrer um problema”. Nenhum modelo ou saída predita foi criado nesta tarefa.

Essa definição substitui a hipótese anterior de tratar Supplier Risk simplesmente como identificação de perfis incomuns. Invoice Anomaly e Purchase Risk conservam seus próprios objetivos e arquiteturas; não há merge direto das features dessas populações distintas.

Esta documentação define o contrato arquitetural do domínio. O pipeline de preparação versão 2.0.0 produz uma base pré-modelagem com nulos preservados. O pipeline ML-Ready versão 1.0.0, descrito na seção 11, deriva conjuntos de treino, validação e teste com imputação aprendida somente no treino, sem alterar essa base. Nenhum modelo preditivo, treinamento de modelo ou EDA foi executado. O contrato detalhado da base está em [Features do Supplier Risk](supplier_risk_features.md).

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

As duas versões compartilham 11 colunas, mas `Geopolitical_Risk_Index` diverge em 26.520 de 28.098 registros. A fonte principal é `supplier_risk_dataset.csv`; o arquivo bruto permanece referência. O valor enriquecido é mantido temporariamente como **feature provisória sujeita à validação da origem**. Fonte do índice, fórmula, data de referência, periodicidade e método de mapeamento por país não estão comprovados.

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

`supplier_record_count` significa: "Quantidade de registros distintos da fonte associados ao fornecedor após a remoção das duplicatas exatas." Não representa profundidade histórica. Os 532 fornecedores repetidos não apresentam variações conhecidas nas nove variáveis numéricas quando preenchidas; as diferenças parecem relacionadas principalmente a preenchimento/incompletude. Sua utilidade será avaliada em experimento COM e SEM a feature.

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

- análise exploratória;
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

O artefato oficial pré-modelagem é `data/processed/supplier_risk/supplier_features_base.parquet`, com nulos preservados. Ele **não é uma matriz pronta para o `fit()`**. Seus derivados numéricos para consumo futuro ficam em `data/processed/supplier_risk/ml_ready/`. O fluxo implementado vai da fonte à base com nulos, reutiliza o split por fornecedor e ajusta apenas o imputador no treino, aplicando-o nos três conjuntos. O treinamento do modelo continua futuro. A base anterior com imputação global foi descontinuada e não participa desse fluxo.

## 10. Critérios de prontidão

O treinamento somente deverá começar depois que:

- a representação por fornecedor estiver definida;
- duplicidades e nulos tiverem tratamento documentado;
- a versão de `Geopolitical_Risk_Index` estiver escolhida;
- indicadores derivados tiverem origem auditada;
- `Risk_Level` estiver excluído da matriz de features;
- a divisão entre treino, validação e teste estiver definida;
- testes confirmarem ausência de leakage e estabilidade do esquema.

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

O único ajuste executado nesta etapa foi o do transformador de imputação; nenhum modelo preditivo foi treinado, nenhuma EDA foi criada e nenhum commit foi realizado. A preparação numérica não resolve as pendências de procedência do índice geopolítico, domínio de compliance/lead time ou validade operacional de `Risk_Level`.

Futuras comparações entre modelos devem reutilizar este split, manter qualquer aprendizado de transformações restrito ao treino e reservar teste para avaliação final. Scaling, alternativas de imputação, categorias e comparação COM/SEM `supplier_record_count` serão experimentos posteriores, sem usar resultados do teste para escolher a configuração.

## 12. Anomalia, risco e limites de interpretação

**Anomalia** é um perfil estatisticamente incomum. Um fornecedor anormal pode ser excepcionalmente ruim ou excepcionalmente bom. **Risco** é uma classificação atribuída conforme uma definição de risco. Portanto, Supplier Risk não será definido simplesmente como detecção de anomalia: será classificação supervisionada de `Risk_Level`.

O modelo atual não pretende:

- prever acontecimentos futuros;
- prever fraude;
- detectar automaticamente eventos futuros de ruptura;
- medir uma probabilidade real de falha;
- substituir avaliação humana de fornecedores.

O dataset não possui sequência temporal adequada para previsão futura. Essa limitação não é resolvida pelo split por fornecedor, nem pela imputação. Nenhum cenário de previsão de acontecimentos futuros será implementado nesta fase. Também permanecem as incertezas de origem do índice geopolítico, escala de compliance e significado de lead time zero. `supplier_record_count` continua representando somente registros distintos após deduplicação, não histórico temporal.

## 13. Protocolo dos experimentos futuros

```text
EDA somente no TRAIN
  ↓
Baseline ingênua: predizer a classe majoritária de TRAIN
e baseline inicial: Logistic Regression
  ↓
Modelos candidatos: Random Forest / Gradient Boosting
  ↓
Avaliação em validation
  ↓
Escolha do modelo, hiperparâmetros e threshold
  ↓
Avaliação final única em test
```

Nenhuma etapa desse fluxo foi executada nesta consolidação. XGBoost só será considerado se a dependência externa for necessária e justificada; não foi adicionado aos requirements. A imputação mediana e o split existentes não foram alterados. Eventual scaling para modelos candidatos deverá ser uma decisão posterior, sempre ajustada somente no treino.

A distribuição observada é aproximadamente **30% classe 0 e 70% classe 1**. Accuracy isolada não será suficiente, pois predizer sempre a classe majoritária já pode produzir acurácia próxima de 70% nessa população. A baseline ingênua identificará a maioria apenas em TRAIN, sem consultar holdout para escolher a classe.

Métricas planejadas:

- confusion matrix;
- precision e recall por classe;
- F1-score por classe, com visão agregada quando útil;
- ROC-AUC para modelos com scores adequados;
- PR-AUC quando aplicável, explicitando a classe positiva e a convenção de cálculo.

A classe positiva convencionada será 1. As métricas de ranking usam scores/probabilidades, não apenas a classe prevista. Os resultados deverão ser comparados com a baseline ingênua, avaliados em validation para seleção e medidos uma única vez no test após a escolha final. Não se utilizarão resultados do teste para ajustar features, transformadores, modelos ou thresholds.

## 14. Qualidade e reprodução do ambiente

`pytest -q` executa os testes sintéticos sem Kaggle e sem treinamento de classificadores. Os testes não dependem da instalação de XGBoost ou matplotlib. Os scripts de produção não precisaram de refatoração; seus resultados e regras foram preservados. A execução local da suíte aprovou 113 testes em aproximadamente 5 segundos, e `ruff check .` aprovou todas as verificações.

Python suportado nesta validação: **3.14.3**, registrado em `.python-version`. Dependências de execução e transitivas foram fixadas em `requirements.txt`; pytest, Ruff e transitivas de testes ficam em `requirements-dev.txt`. As versões foram confirmadas no ambiente instalado, não inventadas ou atualizadas automaticamente.

Existe uma limitação explícita: a resolução limpa por wheels não encontra pandas 2.2.2 para Python 3.14. A `.venv` usada nos testes reutiliza os pacotes funcionais existentes (`--system-site-packages`); não é comprovação de instalação integral nova. Não foi criada CI enquanto a combinação não puder ser reproduzida de forma confiável. Ver [instalação e limitações no README](../README.md).
