# Supplier Risk Model

## 1. Objetivo

O **Supplier Risk Model** será um modelo especializado na identificação de fornecedores com perfil de risco incomum. Sua finalidade é produzir um `supplier_risk_score` independente do score de anomalia de faturas e do score de risco de pedidos de compra.

Esta documentação define o contrato arquitetural e metodológico inicial. Nenhum modelo ou feature é implementado nesta etapa.

## 2. Unidade de análise

A unidade de análise será o **fornecedor**.

O dataset contém mais registros do que fornecedores únicos, além de linhas totalmente duplicadas. Antes do treinamento futuro, será necessário definir como produzir uma representação única por fornecedor. Essa decisão poderá envolver seleção de registros válidos, snapshots ou agregações, mas não deverá modificar os arquivos originais.

## 3. Fontes de dados

Diretório:

```text
data/external/supplier_risk/
```

Arquivos disponíveis:

- `raw_supplier_risk_dataset_1.csv`;
- `supplier_risk_dataset.csv`.

A versão enriquecida possui 28.098 registros, 17 colunas e 24.112 fornecedores únicos. A auditoria identificou 2.057 células nulas e 3.447 linhas totalmente duplicadas.

As duas versões compartilham 11 colunas, mas `Geopolitical_Risk_Index` apresenta valores diferentes na maior parte dos registros. Antes do treinamento, será necessário definir qual versão é autoritativa para esse indicador.

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

Essas colunas são candidatas, não uma especificação final de features. Tipos, escalas, distribuições, valores extremos, disponibilidade temporal e significado de negócio ainda deverão ser validados.

## 5. Campos de contexto

A versão enriquecida também contém:

- `Country`;
- `Region`;
- `Industry`;
- `Supplier_Tier`.

Esses campos poderão oferecer contexto categórico, mas exigirão uma estratégia de codificação ajustada somente no conjunto de treino. Também será necessário verificar cardinalidade, categorias raras e comportamento de categorias não observadas.

## 6. Campos proibidos ou condicionados

### 6.1. Possível label

`Risk_Level` **não deve ser utilizado como feature**.

Esse campo representa uma classificação final de risco e deve ser reservado para:

- análise exploratória;
- avaliação do score produzido;
- comparação entre grupos;
- possível target de um modelo supervisionado futuro.

A mesma restrição deverá ser aplicada a eventuais campos equivalentes, como `Risk_Category`, `Risk_Class`, targets ou classificações derivadas.

### 6.2. Identificação

`Supplier_ID` não deve ser apresentado diretamente ao modelo. Ele deverá ser mantido apenas para:

- consolidar a unidade fornecedor;
- detectar duplicidades;
- construir grupos de separação;
- relacionar scores e resultados;
- garantir rastreabilidade.

### 6.3. Indicadores derivados

Os campos abaixo exigem auditoria de fórmula e temporalidade antes do uso:

- `Delivery_Quality_Index`;
- `Supplier_Dependency_Score`.

Eles podem ser redundantes em relação a variáveis elementares ou incorporar conhecimento não disponível no momento do scoring.

## 7. Qualidade e preparação futura

O pipeline de feature engineering deverá considerar:

- investigação e tratamento das 3.447 linhas duplicadas;
- política de imputação para valores nulos;
- validação de limites, incluindo scores acima das faixas esperadas;
- escolha da versão autoritativa de `Geopolitical_Risk_Index`;
- análise de distribuições e outliers;
- codificação de variáveis categóricas;
- padronização ou transformação somente quando justificada;
- persistência da ordem das features;
- preservação dos arquivos de origem.

Qualquer remoção, imputação ou transformação deverá acontecer em dados processados, nunca nos CSVs originais.

## 8. Estratégia futura de separação

Como a unidade de análise é fornecedor, a divisão de treino, validação e teste deverá impedir que duplicatas ou múltiplas representações equivalentes do mesmo fornecedor atravessem os conjuntos sem controle.

A estratégia deverá responder explicitamente se o objetivo é:

- avaliar novos registros de fornecedores já observados; ou
- generalizar o score para fornecedores inéditos.

Na segunda hipótese, a separação deverá ser feita por grupos de `Supplier_ID`. Como o dataset não apresenta uma dimensão temporal evidente, uma divisão temporal não deve ser inventada sem fonte confiável.

## 9. Contrato do pipeline futuro

**Entrada:** registros validados do Supplier Risk Assessment Dataset.  
**Unidade:** fornecedor.  
**Features:** conjunto aprovado após auditoria e preparação.  
**Campo de avaliação:** `Risk_Level`, nunca como feature.  
**Saída planejada:** `supplier_risk_score`.  
**Artefatos futuros:** `ml/supplier_risk/models/`.

O pipeline deverá salvar junto ao modelo a lista ordenada de features, parâmetros, estratégia de imputação, categorias aprendidas e metadados da execução.

## 10. Critérios de prontidão

O treinamento somente deverá começar depois que:

- a representação por fornecedor estiver definida;
- duplicidades e nulos tiverem tratamento documentado;
- a versão de `Geopolitical_Risk_Index` estiver escolhida;
- indicadores derivados tiverem origem auditada;
- `Risk_Level` estiver excluído da matriz de features;
- a divisão entre treino, validação e teste estiver definida;
- testes confirmarem ausência de leakage e estabilidade do esquema.
