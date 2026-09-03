# Auditoria dos Datasets para Modelos Externos

## 1. Objetivo e escopo

Este documento registra a auditoria inicial dos datasets externos candidatos aos futuros **Supplier Risk Model** e **Purchase Risk Model**. A análise é exploratória: nenhum modelo foi criado, nenhuma feature foi implementada e os arquivos de dados não foram alterados.

As recomendações distinguem identificação, possíveis labels, variáveis disponíveis no momento da decisão e informações pós-evento. Essa separação é necessária para evitar data leakage e preservar a auditabilidade dos modelos futuros.

## 2. Supplier Risk Dataset

**Diretório:** `data/external/supplier_risk/`

### 2.1. Arquivos e qualidade geral

| Arquivo | Registros | Colunas | Fornecedores | Células nulas | Linhas duplicadas |
| --- | --- | --- | --- | --- | --- |
| `raw_supplier_risk_dataset_1.csv` | 28.098 | 11 | 24.112 | 2.057 | 3.447 |
| `supplier_risk_dataset.csv` | 28.098 | 17 | 24.112 | 2.057 | 3.447 |

Os dois arquivos possuem o mesmo número de registros e compartilham 11 colunas. A versão enriquecida acrescenta contexto de localização, indústria, tier, qualidade de entrega e dependência do fornecedor.

#### Consistência entre as versões

| Coluna compartilhada | Valores iguais | Valores diferentes | % de igualdade | Comparação |
| --- | --- | --- | --- | --- |
| `Supplier_ID` | 28.098 | 0 | 100.00% | `raw_supplier_risk_dataset_1.csv` × `supplier_risk_dataset.csv` |
| `Financial_Stability_Score` | 28.098 | 0 | 100.00% | `raw_supplier_risk_dataset_1.csv` × `supplier_risk_dataset.csv` |
| `On_Time_Delivery_Rate` | 28.098 | 0 | 100.00% | `raw_supplier_risk_dataset_1.csv` × `supplier_risk_dataset.csv` |
| `Defect_Rate` | 28.098 | 0 | 100.00% | `raw_supplier_risk_dataset_1.csv` × `supplier_risk_dataset.csv` |
| `Geopolitical_Risk_Index` | 1.578 | 26.520 | 5.62% | `raw_supplier_risk_dataset_1.csv` × `supplier_risk_dataset.csv` |
| `Lead_Time_Days` | 28.098 | 0 | 100.00% | `raw_supplier_risk_dataset_1.csv` × `supplier_risk_dataset.csv` |
| `Alternative_Suppliers_Available` | 28.098 | 0 | 100.00% | `raw_supplier_risk_dataset_1.csv` × `supplier_risk_dataset.csv` |
| `Contract_Length_Months` | 28.098 | 0 | 100.00% | `raw_supplier_risk_dataset_1.csv` × `supplier_risk_dataset.csv` |
| `Environmental_Compliance` | 28.098 | 0 | 100.00% | `raw_supplier_risk_dataset_1.csv` × `supplier_risk_dataset.csv` |
| `Previous_Disruptions` | 28.098 | 0 | 100.00% | `raw_supplier_risk_dataset_1.csv` × `supplier_risk_dataset.csv` |
| `Risk_Level` | 28.098 | 0 | 100.00% | `raw_supplier_risk_dataset_1.csv` × `supplier_risk_dataset.csv` |

A comparação mostra que `Geopolitical_Risk_Index` não é equivalente entre as duas versões, embora as demais colunas compartilhadas coincidam. A versão autoritativa desse indicador deve ser definida antes do treinamento; as duas variantes não devem ser misturadas no mesmo experimento.

### 2.2. Auditoria de `raw_supplier_risk_dataset_1.csv`

#### Colunas, tipos, categorias e qualidade

| Coluna | Tipo | Categoria | Nulos | % nulos | Únicos | Orientação inicial |
| --- | --- | --- | --- | --- | --- | --- |
| `Supplier_ID` | object | identificação | 0 | 0.00% | 24.112 | Não usar diretamente; manter apenas para junção, agrupamento e rastreabilidade. |
| `Financial_Stability_Score` | float64 | financeiras | 404 | 1.44% | 23.776 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `On_Time_Delivery_Rate` | float64 | entrega | 230 | 0.82% | 23.142 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Defect_Rate` | float64 | qualidade | 328 | 1.17% | 21.510 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Geopolitical_Risk_Index` | int64 | risco | 0 | 0.00% | 98 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Lead_Time_Days` | float64 | entrega | 237 | 0.84% | 83 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Alternative_Suppliers_Available` | float64 | risco | 271 | 0.96% | 11 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Contract_Length_Months` | int64 | risco | 0 | 0.00% | 65 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Environmental_Compliance` | float64 | qualidade | 381 | 1.36% | 5.765 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Previous_Disruptions` | float64 | risco | 206 | 0.73% | 7 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Risk_Level` | int64 | possíveis labels | 0 | 0.00% | 2 | Excluir das features; reservar para avaliação ou futuro modelo supervisionado. |

#### Estatísticas numéricas

| Coluna | Contagem | Média | Desvio-padrão | Mínimo | Mediana | Máximo |
| --- | --- | --- | --- | --- | --- | --- |
| `Financial_Stability_Score` | 27.694 | 56.7427 | 14.5556 | 2.6717 | 56.5844 | 100.0000 |
| `On_Time_Delivery_Rate` | 27.868 | 77.6772 | 11.6958 | 30.8370 | 77.8594 | 100.0000 |
| `Defect_Rate` | 27.770 | 4.7084 | 3.2277 | 0.0000 | 4.5469 | 19.2480 |
| `Geopolitical_Risk_Index` | 28.098 | 33.2985 | 17.1710 | 0.0000 | 33.0000 | 100.0000 |
| `Lead_Time_Days` | 27.861 | 25.6021 | 14.3606 | 0.0000 | 25.0000 | 88.0000 |
| `Alternative_Suppliers_Available` | 27.827 | 2.8541 | 1.8786 | 0.0000 | 3.0000 | 10.0000 |
| `Contract_Length_Months` | 28.098 | 19.0000 | 11.2771 | 1.0000 | 19.0000 | 68.0000 |
| `Environmental_Compliance` | 27.717 | 71.0453 | 17.2529 | 1.5200 | 71.5400 | 100.9500 |
| `Previous_Disruptions` | 27.892 | 0.9630 | 0.9809 | 0.0000 | 1.0000 | 6.0000 |
| `Risk_Level` | 28.098 | 0.7002 | 0.4582 | 0.0000 | 1.0000 | 1.0000 |

### 2.3. Auditoria de `supplier_risk_dataset.csv`

#### Colunas, tipos, categorias e qualidade

| Coluna | Tipo | Categoria | Nulos | % nulos | Únicos | Orientação inicial |
| --- | --- | --- | --- | --- | --- | --- |
| `Supplier_ID` | object | identificação | 0 | 0.00% | 24.112 | Não usar diretamente; manter apenas para junção, agrupamento e rastreabilidade. |
| `Country` | object | localização | 0 | 0.00% | 69 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Region` | object | localização | 0 | 0.00% | 6 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Industry` | object | risco | 0 | 0.00% | 5 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Supplier_Tier` | int64 | risco | 0 | 0.00% | 3 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Financial_Stability_Score` | float64 | financeiras | 404 | 1.44% | 23.776 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `On_Time_Delivery_Rate` | float64 | entrega | 230 | 0.82% | 23.142 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Defect_Rate` | float64 | qualidade | 328 | 1.17% | 21.510 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Geopolitical_Risk_Index` | float64 | risco | 0 | 0.00% | 17 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Lead_Time_Days` | float64 | entrega | 237 | 0.84% | 83 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Alternative_Suppliers_Available` | float64 | risco | 271 | 0.96% | 11 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Contract_Length_Months` | int64 | risco | 0 | 0.00% | 65 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Environmental_Compliance` | float64 | qualidade | 381 | 1.36% | 5.765 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Previous_Disruptions` | float64 | risco | 206 | 0.73% | 7 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Delivery_Quality_Index` | float64 | qualidade | 0 | 0.00% | 23.456 | Uso condicionado à auditoria da fórmula e da origem temporal do indicador. |
| `Supplier_Dependency_Score` | float64 | risco | 0 | 0.00% | 11 | Uso condicionado à auditoria da fórmula e da origem temporal do indicador. |
| `Risk_Level` | int64 | possíveis labels | 0 | 0.00% | 2 | Excluir das features; reservar para avaliação ou futuro modelo supervisionado. |

#### Estatísticas numéricas

| Coluna | Contagem | Média | Desvio-padrão | Mínimo | Mediana | Máximo |
| --- | --- | --- | --- | --- | --- | --- |
| `Supplier_Tier` | 28.098 | 2.1939 | 0.6712 | 1.0000 | 2.0000 | 3.0000 |
| `Financial_Stability_Score` | 27.694 | 56.7427 | 14.5556 | 2.6717 | 56.5844 | 100.0000 |
| `On_Time_Delivery_Rate` | 27.868 | 77.6772 | 11.6958 | 30.8370 | 77.8594 | 100.0000 |
| `Defect_Rate` | 27.770 | 4.7084 | 3.2277 | 0.0000 | 4.5469 | 19.2480 |
| `Geopolitical_Risk_Index` | 28.098 | 33.3159 | 15.4331 | 11.0000 | 31.0000 | 87.0000 |
| `Lead_Time_Days` | 27.861 | 25.6021 | 14.3606 | 0.0000 | 25.0000 | 88.0000 |
| `Alternative_Suppliers_Available` | 27.827 | 2.8541 | 1.8786 | 0.0000 | 3.0000 | 10.0000 |
| `Contract_Length_Months` | 28.098 | 19.0000 | 11.2771 | 1.0000 | 19.0000 | 68.0000 |
| `Environmental_Compliance` | 27.717 | 71.0453 | 17.2529 | 1.5200 | 71.5400 | 100.9500 |
| `Previous_Disruptions` | 27.892 | 0.9630 | 0.9809 | 0.0000 | 1.0000 | 6.0000 |
| `Delivery_Quality_Index` | 28.098 | 74.0247 | 11.3930 | 30.1643 | 74.1115 | 100.0000 |
| `Supplier_Dependency_Score` | 28.098 | 0.3642 | 0.2614 | 0.0909 | 0.2500 | 1.0000 |
| `Risk_Level` | 28.098 | 0.7002 | 0.4582 | 0.0000 | 1.0000 | 1.0000 |

### 2.4. Riscos de data leakage e uso indevido

`Risk_Level` representa uma classificação final de risco e não deve entrar como feature em um modelo não supervisionado. O campo deve ser reservado para análise exploratória, avaliação ou como possível target de um experimento supervisionado futuro. A mesma regra se aplica a eventuais campos como `Risk_Category`, `Risk_Class` ou classificações derivadas.

`Delivery_Quality_Index` e `Supplier_Dependency_Score` podem ser úteis, mas são indicadores derivados. Suas fórmulas, dados de origem e disponibilidade temporal devem ser auditados antes do uso para evitar redundância ou vazamento indireto.

`Supplier_ID` deve permanecer apenas como chave de rastreabilidade, agrupamento e separação dos dados. Seu valor nominal não deve ser apresentado diretamente ao modelo.

### 2.5. Recomendação inicial para o Supplier Risk Model

#### Candidatos principais

- `Financial_Stability_Score`
- `On_Time_Delivery_Rate`
- `Defect_Rate`
- `Geopolitical_Risk_Index`
- `Lead_Time_Days`
- `Alternative_Suppliers_Available`
- `Contract_Length_Months`
- `Environmental_Compliance`
- `Previous_Disruptions`

#### Contexto categórico sujeito a codificação

- `Country`
- `Region`
- `Industry`
- `Supplier_Tier`

#### Uso condicionado à auditoria da origem

- `Delivery_Quality_Index`
- `Supplier_Dependency_Score`

#### Exclusão inicial

- `Supplier_ID`
- `Risk_Level`

Antes do treinamento futuro, recomenda-se remover ou investigar as linhas totalmente duplicadas, definir uma política de imputação ajustada somente no treino e decidir se a validação deve medir generalização para fornecedores já observados ou para fornecedores inéditos.

## 3. Purchase Orders Dataset

**Diretório:** `data/external/purchase_orders/`

### 3.1. Arquivos e classificação das planilhas

| Arquivo | Planilha | Papel | Registros | Colunas | Células nulas | Linhas duplicadas |
| --- | --- | --- | --- | --- | --- | --- |
| `Dataset_Procurement.xlsx` | `Data` | transacional | 5.200 | 57 | 0 | 0 |
| `Dataset_Procurement.xlsx` | `Calendar` | auxiliar | 1.096 | 21 | 0 | 0 |
| `Dataset_Procurement.xlsx` | `Vocabulary & Notes` | documental | 87 | 6 | 172 | 11 |

Planilhas documentais são inventariadas, mas não entram na auditoria de variáveis para o modelo. Planilhas auxiliares, como calendários, podem apoiar transformações futuras, porém não constituem a tabela transacional.

### 3.2. Planilha transacional `Data`

Foram identificados 5.200 registros, 57 colunas e 15 fornecedores.

#### Colunas, tipos, categorias e qualidade

| Coluna | Tipo | Categoria | Nulos | % nulos | Únicos | Orientação inicial |
| --- | --- | --- | --- | --- | --- | --- |
| `PO Number` | object | identificação | 0 | 0.00% | 5.200 | Não usar diretamente; manter para rastreabilidade, junções ou agregações. |
| `PO Date` | object | operação | 0 | 0.00% | 1.086 | Não usar como texto bruto; considerar somente transformações temporais definidas no futuro. |
| `PO Year` | int64 | operação | 0 | 0.00% | 3 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `PO Quarter` | object | operação | 0 | 0.00% | 4 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `PO Month` | object | operação | 0 | 0.00% | 12 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `PO Type` | object | operação | 0 | 0.00% | 4 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `PO Status` | object | possíveis labels | 0 | 0.00% | 4 | Possível classificação ou resultado; excluir inicialmente e reservar para avaliação. |
| `Supplier ID` | object | identificação | 0 | 0.00% | 15 | Não usar diretamente; manter para rastreabilidade, junções ou agregações. |
| `Supplier Name` | object | identificação | 0 | 0.00% | 15 | Não usar diretamente; manter para rastreabilidade, junções ou agregações. |
| `Supplier Country` | object | fornecedor | 0 | 0.00% | 14 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Supplier Region` | object | fornecedor | 0 | 0.00% | 4 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Supplier Tier` | int64 | fornecedor | 0 | 0.00% | 3 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Supplier Status` | object | possíveis labels | 0 | 0.00% | 3 | Possível classificação ou resultado; excluir inicialmente e reservar para avaliação. |
| `Supplier Risk` | object | possíveis labels | 0 | 0.00% | 3 | Possível classificação ou resultado; excluir inicialmente e reservar para avaliação. |
| `Supplier Latitude` | float64 | fornecedor | 0 | 0.00% | 14 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Supplier Longitude` | float64 | fornecedor | 0 | 0.00% | 14 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Payment Terms` | object | financeira | 0 | 0.00% | 3 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Item Code` | object | identificação | 0 | 0.00% | 51 | Não usar diretamente; manter para rastreabilidade, junções ou agregações. |
| `Item Description` | object | identificação | 0 | 0.00% | 51 | Não usar diretamente; manter para rastreabilidade, junções ou agregações. |
| `Category` | object | operação | 0 | 0.00% | 10 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Sub Category` | object | operação | 0 | 0.00% | 51 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Unit of Measure` | object | operação | 0 | 0.00% | 10 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Unit Price` | float64 | financeira | 0 | 0.00% | 4.944 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Quantity` | int64 | operação | 0 | 0.00% | 200 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Discount Pct` | int64 | financeira | 0 | 0.00% | 4 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Discount Amount` | float64 | financeira | 0 | 0.00% | 1.349 | Indicador calculado ou redundante; auditar fórmula e colinearidade antes do uso. |
| `Tax Pct` | int64 | financeira | 0 | 0.00% | 3 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Tax Amount` | float64 | financeira | 0 | 0.00% | 3.460 | Indicador calculado ou redundante; auditar fórmula e colinearidade antes do uso. |
| `Line Total Gross` | float64 | financeira | 0 | 0.00% | 5.186 | Indicador calculado ou redundante; auditar fórmula e colinearidade antes do uso. |
| `Line Net` | float64 | financeira | 0 | 0.00% | 5.190 | Indicador calculado ou redundante; auditar fórmula e colinearidade antes do uso. |
| `Line Total Inc Tax` | float64 | financeira | 0 | 0.00% | 5.189 | Indicador calculado ou redundante; auditar fórmula e colinearidade antes do uso. |
| `Currency` | object | financeira | 0 | 0.00% | 5 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Budget Unit Price` | float64 | financeira | 0 | 0.00% | 4.973 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Budget Total` | float64 | financeira | 0 | 0.00% | 5.192 | Indicador calculado ou redundante; auditar fórmula e colinearidade antes do uso. |
| `Savings Amount` | float64 | financeira | 0 | 0.00% | 5.147 | Indicador calculado ou redundante; auditar fórmula e colinearidade antes do uso. |
| `Savings Pct` | float64 | financeira | 0 | 0.00% | 601 | Indicador calculado ou redundante; auditar fórmula e colinearidade antes do uso. |
| `Requested Delivery` | object | operação | 0 | 0.00% | 1.122 | Não usar como texto bruto; considerar somente transformações temporais definidas no futuro. |
| `Actual Delivery` | object | possíveis labels | 0 | 0.00% | 1.119 | Informação pós-evento; não usar em um score calculado no momento da criação ou aprovação do pedido. |
| `Days Late` | int64 | possíveis labels | 0 | 0.00% | 36 | Informação pós-evento; não usar em um score calculado no momento da criação ou aprovação do pedido. |
| `On Time Delivery` | object | possíveis labels | 0 | 0.00% | 2 | Informação pós-evento; não usar em um score calculado no momento da criação ou aprovação do pedido. |
| `Lead Time Days` | int64 | operação | 0 | 0.00% | 91 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Department` | object | operação | 0 | 0.00% | 10 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Cost Centre` | object | operação | 0 | 0.00% | 10 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Requestor Name` | object | identificação | 0 | 0.00% | 15 | Não usar diretamente; manter para rastreabilidade, junções ou agregações. |
| `Approver Name` | object | identificação | 0 | 0.00% | 5 | Não usar diretamente; manter para rastreabilidade, junções ou agregações. |
| `Contract ID` | object | identificação | 0 | 0.00% | 2.817 | Não usar diretamente; manter para rastreabilidade, junções ou agregações. |
| `Contract Type` | object | operação | 0 | 0.00% | 4 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Contract Start` | object | operação | 0 | 0.00% | 1.327 | Não usar como texto bruto; considerar somente transformações temporais definidas no futuro. |
| `Contract End` | object | operação | 0 | 0.00% | 1.694 | Não usar como texto bruto; considerar somente transformações temporais definidas no futuro. |
| `Invoice Status` | object | possíveis labels | 0 | 0.00% | 4 | Informação pós-evento; não usar em um score calculado no momento da criação ou aprovação do pedido. |
| `Payment Status` | object | possíveis labels | 0 | 0.00% | 4 | Informação pós-evento; não usar em um score calculado no momento da criação ou aprovação do pedido. |
| `Invoice Match Type` | object | possíveis labels | 0 | 0.00% | 3 | Informação pós-evento; não usar em um score calculado no momento da criação ou aprovação do pedido. |
| `Maverick Spend` | object | possíveis labels | 0 | 0.00% | 2 | Possível classificação ou resultado; excluir inicialmente e reservar para avaliação. |
| `Single Source Flag` | object | operação | 0 | 0.00% | 2 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Preferred Supplier` | object | fornecedor | 0 | 0.00% | 2 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Local International` | object | fornecedor | 0 | 0.00% | 2 | Candidato inicial, sujeito à validação e ao pré-processamento. |
| `Supplier ESG Score` | float64 | qualidade | 0 | 0.00% | 15 | Score externo; auditar metodologia e temporalidade antes de utilizar. |

#### Estatísticas numéricas

| Coluna | Contagem | Média | Desvio-padrão | Mínimo | Mediana | Máximo |
| --- | --- | --- | --- | --- | --- | --- |
| `PO Year` | 5.200 | 2,022.9933 | 0.8171 | 2,022.0000 | 2,023.0000 | 2,024.0000 |
| `Supplier Tier` | 5.200 | 1.8723 | 0.7149 | 1.0000 | 2.0000 | 3.0000 |
| `Supplier Latitude` | 5.200 | 34.6099 | 24.3126 | -25.2744 | 37.0902 | 60.1282 |
| `Supplier Longitude` | 5.200 | 41.5293 | 70.0656 | -95.7129 | 18.6435 | 138.2529 |
| `Unit Price` | 5.200 | 1,825.1700 | 4,979.5403 | 0.5400 | 272.2750 | 49,879.4200 |
| `Quantity` | 5.200 | 100.4085 | 57.3493 | 1.0000 | 100.0000 | 200.0000 |
| `Discount Pct` | 5.200 | 2.2154 | 4.2335 | 0.0000 | 0.0000 | 15.0000 |
| `Discount Amount` | 5.200 | 3,978.9170 | 27,014.3062 | 0.0000 | 0.0000 | 707,016.6300 |
| `Tax Pct` | 5.200 | 8.1808 | 8.4143 | 0.0000 | 5.0000 | 20.0000 |
| `Tax Amount` | 5.200 | 13,577.3337 | 57,853.7792 | 0.0000 | 360.6450 | 1,525,706.2800 |
| `Line Total Gross` | 5.200 | 178,747.2408 | 533,376.7037 | 4.2000 | 20,842.4400 | 8,195,891.6000 |
| `Line Net` | 5.200 | 174,768.3238 | 521,376.0948 | 4.2000 | 20,285.7250 | 8,195,891.6000 |
| `Line Total Inc Tax` | 5.200 | 188,345.6576 | 561,316.8058 | 4.6200 | 21,973.5900 | 9,154,237.6800 |
| `Budget Unit Price` | 5.200 | 1,973.5824 | 5,396.6667 | 0.5800 | 293.4850 | 61,981.9300 |
| `Budget Total` | 5.200 | 194,819.6598 | 592,031.5521 | 4.5400 | 21,912.4950 | 9,022,375.9600 |
| `Savings Amount` | 5.200 | 20,051.3359 | 98,035.5238 | -636,739.9700 | 1,366.4850 | 2,420,355.8000 |
| `Savings Pct` | 5.200 | 8.5003 | 12.8620 | -33.7000 | 11.7000 | 31.9000 |
| `Days Late` | 5.200 | 4.0788 | 10.2546 | -5.0000 | -1.0000 | 30.0000 |
| `Lead Time Days` | 5.200 | 36.3813 | 18.9662 | 0.0000 | 36.0000 | 90.0000 |
| `Supplier ESG Score` | 5.200 | 60.3381 | 15.5832 | 41.4000 | 55.1000 | 89.1000 |

### 3.3. Riscos de data leakage e uso indevido

A definição do instante de scoring é obrigatória. Para um score calculado na criação ou aprovação do pedido, campos como `Actual Delivery`, `Days Late`, `On Time Delivery`, `Lead Time Days`, `Invoice Status`, `Payment Status` e `Invoice Match Type` ainda não estariam disponíveis e, portanto, causariam data leakage temporal.

Classificações existentes como `Supplier Risk`, `Supplier Status`, `PO Status` e `Maverick Spend` não devem ser usadas diretamente na primeira versão. Elas podem representar regras ou resultados já consolidados e devem ser reservadas para avaliação exploratória até que sua origem seja compreendida.

Identificadores e nomes não devem entrar diretamente no modelo. Datas em texto precisam de uma estratégia temporal explícita. Totais e valores derivados devem ser auditados para evitar redundância matemática com preço, quantidade, desconto, imposto e orçamento.

Não foi encontrada uma coluna explícita de compliance na planilha transacional. `Supplier ESG Score` é o indicador mais próximo de qualidade ou conformidade do fornecedor, mas sua metodologia deve ser auditada antes do uso.

### 3.4. Recomendação inicial para o Purchase Risk Model

#### Candidatos disponíveis no momento do pedido

- `PO Type`
- `Supplier Tier`
- `Payment Terms`
- `Category`
- `Sub Category`
- `Unit of Measure`
- `Unit Price`
- `Quantity`
- `Discount Pct`
- `Tax Pct`
- `Currency`
- `Budget Unit Price`
- `Requested Delivery`
- `Department`
- `Cost Centre`
- `Contract Type`
- `Single Source Flag`
- `Preferred Supplier`
- `Local International`

#### Variáveis pós-evento para análise separada

- `Actual Delivery`
- `Days Late`
- `On Time Delivery`
- `Lead Time Days`
- `Invoice Status`
- `Payment Status`
- `Invoice Match Type`

#### Uso condicionado à auditoria ou redundância

- `Discount Amount`
- `Tax Amount`
- `Line Total Gross`
- `Line Net`
- `Line Total Inc Tax`
- `Budget Total`
- `Savings Amount`
- `Savings Pct`
- `Supplier ESG Score`

#### Exclusão inicial

- `PO Number`
- `PO Status`
- `Supplier ID`
- `Supplier Name`
- `Supplier Status`
- `Supplier Risk`
- `Item Code`
- `Item Description`
- `Requestor Name`
- `Approver Name`
- `Contract ID`
- `Maverick Spend`

As futuras features derivadas podem representar desvio de orçamento, variação de preço, anomalia de lead time, concentração por fornecedor e risco de status. Essas transformações ainda não foram implementadas e deverão ser ajustadas exclusivamente no conjunto de treino.

## 4. Recomendação para os modelos futuros

### 4.1. Supplier Risk Model

A primeira versão deve priorizar indicadores elementares financeiros, de qualidade, entrega, compliance e risco contextual. `Risk_Level` deve permanecer fora das features. O tratamento de nulos, duplicidades e variáveis categóricas deve ser aprendido apenas com o treino.

### 4.2. Purchase Risk Model

A primeira versão deve adotar um instante de decisão claro, preferencialmente a criação ou aprovação do pedido. Isso permite excluir resultados posteriores e construir um score operacional prospectivo. Uma análise pós-entrega poderá ser desenvolvida como camada separada.

### 4.3. Controles obrigatórios

- preservar os datasets originais;
- documentar a unidade de observação e o instante de scoring;
- remover duplicidades somente em uma camada processada;
- ajustar imputação e codificação exclusivamente no treino;
- manter possíveis labels fora das features;
- validar a origem de scores e índices derivados;
- registrar features, parâmetros, métricas e versões;
- manter `supplier_risk_score` e `purchase_risk_score` separados e auditáveis.

## 5. Conclusão

Os dois datasets possuem variáveis relevantes para modelos especializados, mas exigem controles diferentes. Supplier Risk demanda tratamento de duplicidades, nulos e exclusão de classificações finais. Purchase Orders apresenta boa completude, mas requer uma separação rigorosa entre dados disponíveis no pedido e resultados observados posteriormente.

A recomendação é iniciar cada modelo com um conjunto conservador de variáveis, manter indicadores derivados sob auditoria e comparar todas as evoluções contra uma baseline reproduzível.
