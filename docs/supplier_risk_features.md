# Feature Engineering do Supplier Risk Model

## Objetivo

Este documento descreve a primeira versão do pipeline de preparação de dados do **Supplier Risk Model**. O objetivo é transformar os registros de risco de fornecedores em uma base consolidada, com uma linha por fornecedor e somente variáveis aprovadas para um treinamento futuro.

Esta etapa não executa treinamento, não instancia modelos de Machine Learning e não produz scores de risco. O pipeline limita-se ao carregamento, à validação, à consolidação e ao tratamento das features.

## Fontes de dados

A fonte principal é:

`data/external/supplier_risk/supplier_risk_dataset.csv`

O arquivo abaixo é mantido exclusivamente como referência e não participa da geração das features:

`data/external/supplier_risk/raw_supplier_risk_dataset_1.csv`

Os arquivos de origem são tratados como imutáveis. O pipeline calcula o hash SHA-256 da fonte principal antes e depois do processamento e interrompe a execução caso detecte alteração.

## Unidade de análise

A unidade de análise é o **fornecedor**, identificado na fonte por `Supplier_ID`. A inspeção inicial encontrou 28.098 registros, 24.112 fornecedores únicos, 3.447 linhas totalmente duplicadas e 532 fornecedores com mais de um registro distinto após a deduplicação.

A consolidação segue estas etapas:

1. remoção de linhas totalmente duplicadas;
2. conversão das features aprovadas para valores numéricos;
3. substituição de valores infinitos por nulos;
4. agrupamento por `Supplier_ID`;
5. cálculo da mediana de cada feature para cada fornecedor;
6. cálculo de `supplier_record_count` com a quantidade de registros distintos utilizados na consolidação.

A mediana foi escolhida por ser menos sensível a observações extremas do que a média. O identificador é preservado no arquivo final apenas para rastreabilidade e não integra o vetor de entrada do futuro modelo.

A feature `supplier_record_count` registra quantos registros distintos, após a remoção de duplicatas exatas, contribuíram para o perfil consolidado. Ela fornece ao modelo futuro um indicador explícito da profundidade histórica disponível para cada fornecedor e permite distinguir perfis baseados em uma única observação daqueles sustentados por múltiplas observações. Na execução atual, 23.580 fornecedores possuem um registro, 525 possuem dois e 7 possuem três registros distintos.

## Features aprovadas

O dataset final contém dez features numéricas. Os nomes foram normalizados para `snake_case`:

| Dimensão | Coluna de origem | Feature final | Interpretação |
|---|---|---|---|
| Financeira | `Financial_Stability_Score` | `financial_stability_score` | Estabilidade financeira do fornecedor |
| Operacional | `On_Time_Delivery_Rate` | `on_time_delivery_rate` | Taxa de entregas realizadas no prazo |
| Qualidade | `Defect_Rate` | `defect_rate` | Taxa observada de defeitos |
| Risco | `Geopolitical_Risk_Index` | `geopolitical_risk_index` | Exposição a risco geopolítico |
| Operacional | `Lead_Time_Days` | `lead_time_days` | Prazo de fornecimento em dias |
| Capacidade | `Alternative_Suppliers_Available` | `alternative_suppliers_available` | Quantidade de fornecedores alternativos disponíveis |
| Capacidade | `Contract_Length_Months` | `contract_length_months` | Duração contratual em meses |
| Qualidade e compliance | `Environmental_Compliance` | `environmental_compliance` | Indicador de conformidade ambiental |
| Operacional | `Previous_Disruptions` | `previous_disruptions` | Quantidade de disrupções anteriores |
| Histórico | Contagem derivada por `Supplier_ID` | `supplier_record_count` | Quantidade de registros distintos usados na consolidação do fornecedor |

O arquivo também contém `supplier_id` como chave de rastreabilidade. Assim, possui onze colunas físicas, mas somente as dez colunas listadas como features podem ser fornecidas a um modelo.

## Features removidas ou adiadas

### Campos proibidos e risco de data leakage

- `Risk_Level` foi excluída por representar uma classificação final de risco e poder introduzir vazamento de informação.
- `Risk_Category`, caso exista em versões futuras da fonte, deve receber o mesmo tratamento.
- `Supplier_ID` não é feature por ser apenas um identificador. Sua versão `supplier_id` permanece como metadado de rastreabilidade.

Esses campos não devem ser selecionados como entrada de modelos não supervisionados ou supervisionados que tenham como objetivo reproduzir ou avaliar o risco do fornecedor.

### Índices derivados

As duas variáveis adicionais avaliadas não foram incluídas:

- `Delivery_Quality_Index` reproduz `On_Time_Delivery_Rate * (1 - Defect_Rate / 100)` em 100% dos valores válidos;
- `Supplier_Dependency_Score` reproduz `1 / (Alternative_Suppliers_Available + 1)` em 100% dos valores válidos.

Como são transformações determinísticas de features já aprovadas, sua inclusão adicionaria redundância e atribuiria peso duplicado às mesmas informações. Elas podem ser recalculadas posteriormente para interpretação, sem fazer parte desta versão do dataset de treinamento.

### Variáveis categóricas

`Country`, `Region`, `Industry` e `Supplier_Tier` foram avaliadas, mas adiadas nesta primeira versão. A fonte possui, respectivamente, 69, 6, 5 e 3 categorias. A decisão evita aplicar encoding global antes da definição formal das partições de treino, validação e teste, além de impedir que alta cardinalidade, categorias raras ou códigos de origem ainda não auditados sejam incorporados prematuramente.

Em uma versão futura, essas variáveis poderão ser testadas com um encoder ajustado exclusivamente no conjunto de treino. A adoção deverá ser condicionada a uma comparação controlada com a baseline numérica e a uma política para categorias desconhecidas.

## Tratamentos aplicados

### Valores nulos

Após a consolidação por fornecedor, os valores ausentes foram imputados pela mediana de cada feature no conjunto consolidado:

| Feature de origem | Valores imputados | Mediana utilizada |
|---|---:|---:|
| `Financial_Stability_Score` | 286 | 56,583856 |
| `On_Time_Delivery_Rate` | 160 | 77,783524 |
| `Defect_Rate` | 240 | 4,557380 |
| `Geopolitical_Risk_Index` | 0 | 31,000000 |
| `Lead_Time_Days` | 176 | 25,000000 |
| `Alternative_Suppliers_Available` | 196 | 3,000000 |
| `Contract_Length_Months` | 0 | 19,000000 |
| `Environmental_Compliance` | 270 | 71,480000 |
| `Previous_Disruptions` | 158 | 1,000000 |

Essa estratégia fornece uma base sem valores nulos e mantém robustez em relação a extremos. Entretanto, ela caracteriza uma preparação inicial. Em experimentos formais, a divisão dos dados deve ocorrer antes do ajuste do imputador, e as medianas aprendidas somente no conjunto de treino devem ser reaplicadas à validação e ao teste.

### Escalas e outliers

Foi aplicada uma análise exploratória pelo critério de 1,5 vezes o intervalo interquartil, após a consolidação e antes da imputação:

| Feature de origem | Observações fora dos limites do IQR |
|---|---:|
| `Financial_Stability_Score` | 186 |
| `On_Time_Delivery_Rate` | 92 |
| `Defect_Rate` | 97 |
| `Geopolitical_Risk_Index` | 65 |
| `Lead_Time_Days` | 89 |
| `Alternative_Suppliers_Available` | 55 |
| `Contract_Length_Months` | 62 |
| `Environmental_Compliance` | 86 |
| `Previous_Disruptions` | 11 |

Os outliers foram preservados porque podem representar sinais legítimos de risco. Também não foi aplicada padronização ou normalização nesta etapa: a transformação de escala deve pertencer ao pipeline do modelo futuro, ser ajustada apenas no treino e ser escolhida de acordo com o algoritmo avaliado.

## Dataset gerado

O resultado é salvo em:

`data/processed/supplier_risk/supplier_features.parquet`

O contrato e as informações de geração do dataset são salvos em:

`data/processed/supplier_risk/supplier_features_metadata.json`

Resumo da execução validada:

| Indicador | Resultado |
|---|---:|
| Fornecedores | 24.112 |
| Features aprovadas | 10 |
| Colunas de rastreabilidade | 1 |
| Valores nulos nas features | 0 |
| Valores infinitos nas features | 0 |
| Identificadores de fornecedor duplicados | 0 |
| Perfis de features duplicados | 0 |

## Decisões de governança

- O arquivo Parquet processado é um artefato reproduzível e permanece ignorado pelo Git.
- Os datasets externos não são alterados pelo pipeline.
- O contrato de features é explícito no código; o aparecimento de colunas novas não as adiciona automaticamente.
- A ausência de qualquer coluna obrigatória interrompe o processamento.
- Labels e classificações finais de risco não são propagadas para o dataset de features.
- A chave `supplier_id` deve ser separada das features antes de qualquer chamada futura a `fit`, `predict` ou equivalente.
- O metadata registra a lista completa de features, as exclusões, os tratamentos aplicados, a data de geração e o hash da fonte principal.

## Preparação para treinamento futuro

O dataset atual representa uma **preparação inicial** e um contrato de features consolidado. Ele permite validar schema, tipos, completude e rastreabilidade antes da criação do primeiro experimento, mas não substitui um pipeline de transformação ajustado dentro do ciclo de treinamento.

No treinamento futuro, a separação entre treino, validação e teste deverá ocorrer antes de qualquer operação que aprenda parâmetros dos dados. Em particular:

1. os parâmetros de imputação, como as medianas, devem ser aprendidos exclusivamente no conjunto de treino;
2. validação e teste devem somente aplicar os parâmetros aprendidos no treino, sem recalcular medianas próprias ou globais;
3. qualquer normalização, padronização ou encoding futuro deve seguir a mesma separação;
4. o `supplier_id` deve permanecer fora da matriz de entrada;
5. as dez features deverão ser selecionadas a partir do contrato registrado no metadata.

Essa estratégia evita leakage estatístico e garante que as métricas futuras representem o comportamento do modelo diante de fornecedores não utilizados no ajuste dos transformadores.

## Limitações e próximos cuidados

- A base não apresenta uma dimensão temporal adequada para uma divisão cronológica ou para determinar qual registro representa o estado mais recente de cada fornecedor.
- A mediana entre registros distintos pode ocultar variações importantes. Versões futuras devem avaliar medidas de dispersão, tendência ou pior caso quando houver histórico temporal confiável.
- A imputação atual usa o conjunto consolidado completo; para avaliação sem leakage estatístico, o transformador deverá ser ajustado somente no treino.
- As variáveis categóricas ainda não participam da baseline e exigem avaliação específica de encoding e cardinalidade.
- `Geopolitical_Risk_Index` apresenta diferenças relevantes entre o arquivo enriquecido e o arquivo bruto de referência. Esta versão usa os valores do dataset principal conforme definido para o projeto, mas a origem do enriquecimento deve ser documentada antes de uso em produção.
- O valor máximo observado de `Environmental_Compliance` ultrapassa ligeiramente 100, o que exige confirmação da regra de negócio antes de eventual limitação de faixa.
- A base final está pronta para um treinamento futuro do ponto de vista estrutural, mas a estratégia de particionamento e todos os transformadores dependentes dos dados ainda devem ser definidos no pipeline experimental.
