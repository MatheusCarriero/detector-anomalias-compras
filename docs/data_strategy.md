# Estratégia de Dados

## 1. Visão geral

O projeto **Detector Inteligente de Anomalias em Compras** utiliza fontes distintas para anomalias em faturas, classificação supervisionada de risco de fornecedores e risco de pedidos. A hipótese inicial de enriquecer as features de Invoice com fontes externas foi substituída pela arquitetura de três modelos especializados. Este documento preserva o histórico sem apresentar essa hipótese como plano de implementação vigente.

Atualmente, o Invoice Anomaly Model utiliza exclusivamente o **Procurement Invoice Fraud Dataset**. A decisão arquitetural vigente é **3 domínios principais → 3 modelos especializados**. Supplier Risk e Purchase Risk possuem fontes e responsabilidades próprias; não são fontes de treinamento do Invoice nesta fase. O Procurement KPI permanece apenas auxiliar.

| Domínio / fonte | Local | Responsabilidade | Situação atual |
|---|---|---|---|
| Invoice Dataset | `data/raw/` | Fonte principal do Invoice Anomaly Model: triagem de faturas para auditoria humana | Avaliações VALIDATION concluídas; avaliador acadêmico e validações preservadas; avaliação final única em TEST concluída; uso operacional pendente |
| Supplier Risk Dataset | `data/external/supplier_risk/` | Fonte principal do Supplier Risk Model: classificação supervisionada de `Risk_Level` | Avaliação final acadêmica LR/C concluída; TEST não reutilizável, sem modelo de produção |
| Purchase Orders Dataset | `data/external/purchase_orders/` | Fonte candidata do Purchase: linhas de pedido; disponibilidade pré-aprovação não comprovada | Decisão C: não implementar ainda; gate metodológico, sem feature engineering/modelagem |
| Procurement KPI Dataset | `data/auxiliary/` | Referência complementar, exploração futura de KPIs, análises futuras e possível apoio ao dashboard | Auxiliar; não participa do treinamento dos três modelos principais |

A independência dos três modelos é a estratégia atual. As fontes representam populações diferentes e não possuem chaves reais comuns para integração; identificadores semelhantes não comprovam identidade. Não será realizado merge direto das features desses datasets. Uma eventual camada futura de integração de **scores** exigirá contexto comum verificável, justificativa e avaliação próprias; não está implementada.

Os princípios que orientam a estratégia são:

- separação clara entre dados brutos, externos e processados;
- preservação dos arquivos originais;
- uso exclusivo do conjunto de treino no cálculo de estatísticas históricas;
- prevenção de data leakage;
- rastreabilidade das features e transformações;
- validação da compatibilidade entre fontes antes de qualquer integração;
- evolução incremental, com comparação entre experimentos e manutenção de uma baseline reproduzível.

## Arquitetura atual de dados

A arquitetura separa domínios com maturidades distintas: Invoice com avaliações em VALIDATION e avaliação final em TEST concluídas, Supplier com avaliação final acadêmica concluída e Purchase em definição metodológica.

### Unidades, saídas e maturidade dos modelos

| Modelo | Unidade de análise | Fonte principal | Momento de scoring | Saída planejada | Estado |
| --- | --- | --- | --- | --- | --- |
| Invoice Anomaly Model | Fatura | Procurement Invoice Fraud Dataset | Lote retrospectivo preparado; uso online não validado | `invoice_anomaly_score` | Triagem/comparação VALIDATION e avaliação final única em TEST concluídas; sem uso operacional validado |
| Supplier Risk Model | Fornecedor | Supplier Risk Assessment Dataset | Classificação do perfil representado no dataset, sem previsão temporal | Classe 0/1 e, quando compatível, probabilidade estimada da classe 1 | Avaliação final acadêmica LR/C concluída; sem uso operacional validado |
| Purchase Risk Model | Linha de pedido na fonte; agregação por pedido não comprovada | Purchase Orders & Supplier Performance Dataset | Uso pretendido antes da aprovação; disponibilidade não comprovada | Significado pendente: anomalia ou desfecho específico; `purchase_risk_score` é nome histórico | Decisão C: não implementar ainda; features/modelo não criados |

Os scores devem permanecer separados, versionados e auditáveis. Uma eventual composição em um score geral deverá ocorrer somente depois da validação individual dos modelos e deverá preservar a contribuição de cada componente.

### Fluxo Invoice com modelo existente

```text
Procurement Invoice Fraud Dataset
                 ↓
         Feature Engineering
                 ↓
          Isolation Forest
                 ↓
Invoice Anomaly Score (triagem VALIDATION e avaliação final em TEST concluídas; uso operacional pendente)
```

### Fontes externas — estado por domínio

```text
Purchase Orders Dataset
            ↓
Gate metodológico: disponibilidade pré-aprovação não comprovada

Supplier Risk Dataset
            ↓
Validação, deduplicação e consolidação por fornecedor
            ↓
supplier_features_base.parquet (nulos preservados)
            ↓
Auditoria de Risk_Level e split determinístico por supplier_id (concluídos)
            ↓
Imputação mediana train-only e arquivos ML-Ready (concluídos)
            ↓
EDA TRAIN, baselines TRAIN/VALIDATION e CV A/D em TRAIN (concluídas)
            ↓
Congelamento LR/C e avaliação final única em TEST (concluídos; não repetir)

Procurement KPI Dataset
            ↓
Apoio complementar / KPIs / dashboard (sem treinamento nesta fase)
```

O fluxo declarado do Isolation Forest usa somente o Procurement Invoice Fraud Dataset; isso não certifica retrospectivamente os bytes/IDs do fit legado. Os datasets externos não são fontes desse pipeline.

Supplier Risk concluiu preparação, experimentos independentes e avaliação final acadêmica, sem artefato de produção. Purchase Risk possui auditoria e estratégia, mas ainda não possui feature engineering ou modelagem.

## 2. Papel dos datasets

### 2.1. Dataset principal — Procurement Invoice Fraud Dataset

**Local:** `data/raw/`

O Procurement Invoice Fraud Dataset é a fonte principal do Invoice Anomaly Model e contém 300.000 registros relacionados a faturas, fornecedores, departamentos, valores, condições de pagamento e tipos conhecidos de fraude.

Seu papel é sustentar a primeira versão do sistema de detecção de anomalias. Ele oferece volume suficiente para separar os dados em treino, validação e teste e permite comparar os padrões encontrados pelo modelo com informações de fraude conhecidas.

Os labels não fazem parte das entradas do modelo. A coluna `is_fraud` é reservada para avaliação posterior, enquanto `fraud_type` pode ser utilizada em análises complementares. Campos que representam risco previamente conhecido, explicações ou informações derivadas do resultado também não devem ser utilizados como features.

O objetivo vigente foi formalizado em **27/09/2026**: priorizar faturas de comportamento incomum para auditoria humana. O enquadramento da avaliação mudou, sem alterar o treinamento. O score não é classificação automática nem probabilidade de fraude.

#### Features atuais

O pipeline atual gera 19 features:

1. `invoice_amount`
2. `log_invoice_amount`
3. `supplier_age_days`
4. `supplier_frequency`
5. `country_frequency`
6. `amount_vs_supplier_mean`
7. `supplier_amount_zscore`
8. `department_frequency`
9. `amount_vs_department_mean`
10. `supplier_department_frequency`
11. `payment_terms_days`
12. `invoice_type_encoded`
13. `submission_hour_sin`
14. `submission_hour_cos`
15. `day_of_week_sin`
16. `day_of_week_cos`
17. `month_sin`
18. `month_cos`
19. `is_weekend`

As estatísticas relacionadas a fornecedores, países, departamentos e relações entre fornecedor e departamento são calculadas somente com o conjunto de treino. Essa restrição deve ser mantida em todas as evoluções do pipeline.

**LIMITAÇÃO:** usar apenas TRAIN não significa construir estatísticas ponto-a-ponto temporais. O código atual agrega todo o período de TRAIN, inclusive observações posteriores à fatura dentro desse período e a própria fatura. O experimento existente avalia principalmente novas faturas de fornecedores já conhecidos; não comprova desempenho com fornecedores inéditos. A auditoria registrou os mesmos 2.000 fornecedores em treino e nos conjuntos posteriores. Essas observações não são uma afirmação de uso de TEST no ajuste, nem uma mudança metodológica nesta tarefa.

**IMPLEMENTADO:** Isolation Forest com `contamination=0.22` como configuração inicial, validação explícita das 19 features e `main` guard para importação inerte. A avaliação consolidada e por `fraud_type`, a triagem e a comparação IF × valor em VALIDATION foram concluídas. O protocolo atual mantém orçamentos 1%/5%/10%, sem escolha de threshold operacional ou novo treino. `contamination` não mede precisão nem probabilidade de fraude.

**CONCLUÍDO em 18/10/2026:** avaliação final em TEST realizada em execução única, com 60.000 registros, uma única chamada de scoring e as mesmas 19 features, sem fit, tuning ou ajuste de threshold, conforme o [protocolo](invoice_academic_evaluation_protocol.md). O resultado oficial está em [invoice_test_final_v1.json](../ml/experiments/invoice_test_final_v1.json), separado dos resultados históricos de VALIDATION. O avaliador já recebe dados e modelo explicitamente, preserva validações de schema, IDs, partições, features, labels, moeda e valores, e registra um JSON novo sem sobrescrita.

Na comparação final, valor apresentou maior Precision@K e captura no top 1%; no top 5%, os resultados foram próximos, com pequena vantagem do IF; no top 10%, o IF apresentou maior Precision@K e captura. Não houve superioridade uniforme nem definição de uma política operacional. Custos, capacidade de revisão, utilidade humana e disponibilidade das informações precisam de validação própria.

Os raw compartilhados não isolam TEST por filtros. `source_reconciled=false` e a origem não certificada do fit legado continuam acompanhando o resultado final.

#### Justificativa de utilização

O dataset principal reúne atributos transacionais e contexto suficiente para construir uma baseline de Machine Learning não supervisionado. O algoritmo atual é o **Isolation Forest**, escolhido por sua capacidade de identificar observações que apresentam combinações pouco frequentes de valores sem utilizar labels durante o treinamento.

#### Preservação dos arquivos tabulares e situação das imagens

O projeto utiliza dados tabulares. A pasta `data/raw/images/` não participa dos pipelines atuais. Sua remoção só é permitida quando um ZIP original íntegro em `DataBase/` comprovar o backup completo e todos os arquivos tabulares necessários estiverem preservados.

Verificação do ambiente em 2026-09-07:

- `data/raw/images/` não existe; nenhuma imagem foi removida nesta revisão;
- `DataBase/` não existe e não foi possível comprovar um ZIP original íntegro nesse local; `data/raw/archive.zip` também não foi encontrado;
- presentes e preservados: `invoices.parquet`, `labels.parquet`, `suppliers.parquet`, `splits.parquet`, `images_metadata.parquet` e `manifest.json`;
- `departments.parquet` e `behavioural_features.parquet` não estavam presentes; não foram removidos nem reconstruídos nesta tarefa;
- os oito arquivos tabulares citados devem ser preservados quando disponíveis. A ausência de dois arquivos não foi interpretada como autorização para remover outros dados.

Não há comprovação de backup completo neste checkout. Qualquer futura remoção de imagens exigirá nova verificação do ZIP e da integridade dos dados tabulares. O `images_metadata.parquet` permanece preservado independentemente da situação das imagens.

### 2.2. Dataset externo — Purchase Orders & Supplier Performance Dataset

**Local:** `data/external/purchase_orders/`  
**Arquivo:** `Dataset_Procurement.xlsx`

O dataset possui 5.200 linhas de pedido, 57 colunas e 15 fornecedores. Ele reúne preços, orçamento, descontos, tributos, entregas, contratos, status e indicadores operacionais. Não há comprovação de uma medida real de compliance; ESG é simulado.

**EVIDÊNCIAS CONFIRMADAS no Vocabulary & Notes:** `PO_Number` identifica linha de pedido; `Lead_Time_Days` depende da entrega efetiva e é pós-evento; `Supplier_ESG_Score` é simulado; valores monetários estão em moedas locais (GBP/EUR/USD/JPY/AUD), sem conversão cambial. A aba Data usa nomes com espaços, enquanto o dicionário usa underscores. Esses fatos são documentais, não novas transformações dos dados.

#### Papel no projeto

Essa fonte permite descrever retrospectivamente valores de compra, orçamento, condições registradas e desempenho da entrega na sua própria população. Não comprova quais desses valores estavam disponíveis antes da aprovação. A ideia anterior de adicionar esse contexto às faturas do outro dataset é apenas histórica: não existem chaves reais comuns que sustentem essa associação.

Na arquitetura vigente, essa fonte pertence ao **Purchase Risk Model independente**. A auditoria definiu **C: não implementar o modelo ainda**, por insuficiência metodológica para demonstrar o uso pré-aprovação pretendido. Não há timestamp explícito de aprovação nem histórico de alterações/snapshots; `PO Date` não comprova aprovação. O [contrato Purchase](purchase_risk_model.md) registra os esclarecimentos necessários antes de feature engineering ou treinamento.

Não há target aprovado. `Days Late`, `On Time Delivery` e `Lead Time Days` são candidatos a desfechos pós-evento; `Maverick Spend` depende de comprovação de regra e procedência. `Supplier Risk` é classificação preexistente, não desfecho comprovado. A semântica de status, `Contract ID` e `NO-CONTRACT` continua pendente. Nenhuma lista de features pré-aprovação está aprovada, e detecção de anomalias permanece uma possibilidade não escolhida; anomalia não comprova risco ou fraude.

A intenção histórica de modelar pedido completo exigiria uma chave de cabeçalho e agregação justificadas; a fonte confirma apenas linhas. Nenhuma junção direta de features entre domínios está planejada.

As hipóteses anteriores de análise incluem situações como:

- preços realizados muito acima do orçamento;
- variações atípicas de preço para itens semelhantes;
- atrasos incompatíveis com o histórico do fornecedor;
- compras emergenciais ou com status incomum;
- concentração de pedidos em fornecedores de baixo desempenho;
- divergências entre condições contratadas e resultados observados.

#### Hipóteses de features — não implementadas

- `budget_deviation`: diferença absoluta ou relativa entre o valor realizado e o orçamento correspondente;
- `price_variation`: desvio do preço unitário em relação ao histórico do item, categoria ou fornecedor;
- `delivery_delay_score`: medida normalizada de atraso entre a data solicitada e a data efetiva de entrega;
- `supplier_performance_score`: indicador agregado de entrega, economia, compliance e consistência operacional;
- `lead_time_anomaly`: grau de desvio do lead time em relação ao comportamento histórico comparável;
- `purchase_status_risk`: representação do risco associado ao status e ao fluxo do pedido de compra.

Essas features são hipóteses históricas de pesquisa, não uma lista aprovada. Suas fórmulas, janelas históricas e métodos de normalização só poderão ser definidos para modelagem depois de esclarecer disponibilidade temporal e superar o gate metodológico.

Hipóteses que dependem de entrega ou status pós-evento não integram as entradas pré-aprovação definidas em [Purchase Risk Model](purchase_risk_model.md). `delivery_delay_score` ou lead time realizado da própria linha não podem ser features nesse instante; seriam no máximo análises pós-evento ou possíveis desfechos futuros, mediante definição específica.

Indicadores históricos exigiriam datas e eventos disponíveis antes da decisão. Essa delimitação foi registrada na documentação, sem criação ou alteração de pipeline Purchase.

### 2.3. Dataset externo — Supplier Risk Assessment Dataset

**Local:** `data/external/supplier_risk/`

**Arquivos:**

- `raw_supplier_risk_dataset_1.csv`
- `supplier_risk_dataset.csv`

O pacote contém 28.098 registros. A versão enriquecida possui 17 colunas e adiciona contexto geográfico, industrial, qualidade de entrega e dependência do fornecedor aos indicadores presentes na versão bruta.

#### Papel no projeto

Esse dataset é a fonte principal do **Supplier Risk Model independente**, definido como classificação supervisionada de `Risk_Level` a partir do perfil operacional, financeiro e de qualidade. A convenção adotada no projeto é `0 = menor risco`, `1 = maior risco`, sem comprovação da origem ou da regra de construção da label. Não existe dimensão temporal adequada para prever acontecimentos futuros.

A fonte operacional é `supplier_risk_dataset.csv`; `raw_supplier_risk_dataset_1.csv` permanece apenas como referência. O pipeline versão 2.0.0 produz `data/processed/supplier_risk/supplier_features_base.parquet`, com uma linha por fornecedor e nulos preservados. Não aplica imputação, normalização, padronização ou encoding. A matriz numérica contém dez features candidatas e `supplier_id` separado para rastreabilidade. O contrato detalhado está em [Features do Supplier Risk](supplier_risk_features.md).

`supplier_record_count` conta registros distintos da fonte após duplicatas exatas, sem significar profundidade histórica. O índice geopolítico da fonte enriquecida é mantido provisoriamente, com origem ainda não validada. Cobertura e alertas de domínio são armazenados em artefato próprio, fora da matriz.

O split já precede a imputação: `prepare_target_and_split.py` estabelece partições de 16.894 / 3.539 / 3.679 fornecedores; `build_ml_dataset.py` ajusta `SimpleImputer(strategy="median")` somente em TRAIN e transforma validation/test. Os seis Parquets ML-Ready têm dez features em X e targets separados, sem alterar a base com nulos.

**LIMITAÇÕES preservadas:** o índice geopolítico diverge em cerca de 94,38% dos registros entre fontes e tem forte associação observada com Country; origem, fórmula e data de referência não estão comprovadas. A contagem pode refletir o processo de coleta, não histórico temporal. Os 1.386 fornecedores com `environmental_compliance > 100` e os 1.134 com `lead_time_days = 0` permanecem sem clipping ou remoção automática: escala/origem de compliance e significado de zero ainda não estão confirmados.

**CONCLUÍDO:** seguindo o protocolo [Supplier Risk](supplier_risk_model.md), foram comparados A (10 features), B (sem índice geopolítico), C (sem contagem) e D (sem ambas) em VALIDATION. Depois houve CV exploratória A/D dentro de TRAIN, congelamento LR/C com nove features e avaliação final única. O [relatório final](supplier_risk_final_evaluation.md) registra a execução, sem alteração dos arquivos de features nem refit TRAIN+VALIDATION.

Procedência e validade externa continuam pendentes; não são motivo para reutilizar TEST.

A saída definida para o domínio é a classe prevista e, para modelos compatíveis, a probabilidade estimada de pertencimento à classe 1. Não é probabilidade real de falha, previsão de fraude ou de rupturas. Não se afirma que esses fornecedores correspondam aos fornecedores dos datasets de Invoice/Purchase. As conclusões devem se limitar à capacidade de reproduzir padrões associados à classificação fornecida pelo dataset.

#### Hipóteses históricas de features, fora do contrato atual

As ideias abaixo não substituem as dez features atuais nem são implementadas nesta fase:

- `financial_risk_score`: síntese de estabilidade financeira e demais indicadores financeiros disponíveis;
- `delivery_risk_score`: combinação de pontualidade, lead time e histórico de interrupções;
- `quality_risk_score`: representação de defeitos, qualidade de entrega e consistência operacional;
- `compliance_risk_score`: indicador associado ao cumprimento de requisitos ambientais ou regulatórios;
- `supplier_dependency_score`: medida de dependência e disponibilidade de fornecedores alternativos.

Os scores dessas hipóteses históricas não devem ser tratados como equivalentes a labels de fraude. Antes de qualquer uso futuro, será necessário investigar a origem, a escala, a distribuição e a construção de cada variável.

Anomalia é um perfil estatisticamente incomum, que pode ser excepcionalmente bom ou ruim; classificação de risco depende da definição da referência. Não se comprovou se `Risk_Level` decorre de avaliação humana, regra sintética ou outro processo. O modelo não substitui avaliação humana.

#### Controle sobre features de risco

`Risk_Level` é o target da classificação supervisionada do Supplier Risk, nunca uma feature. `Risk_Category` e classificações equivalentes também permanecem fora de X. A definição antiga de Supplier Risk como simples detecção de anomalias foi substituída; Isolation Forest permanece no domínio Invoice.

Esses campos devem ser reservados para:

- análise exploratória somente no TRAIN;
- avaliação;
- comparação de resultados;
- target supervisionado, no caso de `Risk_Level`, já utilizado no Supplier com as limitações de origem documentadas.

Essa separação evita que o modelo receba uma representação direta ou indireta do resultado que se pretende analisar, reduzindo o risco de data leakage e preservando a validade dos experimentos.

### 2.4. Fonte auxiliar — Procurement KPI Analysis Dataset

O dataset identificado no projeto como **Procurement KPI Analysis Dataset** permanece em `data/auxiliary/dataset_auxiliar_kpi_compras.csv`, com nome de saída definido pelo extrator `ml/scripts/extrair_dataset_auxiliar.py`. O nome `data/auxiliary/Procurement KPI Analysis Dataset.csv` citado na decisão não corresponde a um arquivo presente neste checkout; o arquivo local não foi renomeado nem removido.

Sua finalidade é referência complementar, exploração futura de KPIs, possíveis análises futuras e possível apoio ao dashboard. Ele **não participa do treinamento de Invoice Anomaly, Supplier Risk ou Purchase Risk nesta fase**. Nenhuma EDA ou integração do KPI é implementada nesta revisão.

### 2.5. Procedência conhecida e não comprovada — fechamento de 2026-09-14

| Fonte | Evidência disponível no projeto | Limites de procedência |
|---|---|---|
| Invoice | Parquets locais, `manifest.json` com versão/contagens, split oficial e modelo existente | Regra de construção/validação dos labels e representatividade operacional não comprovadas; backup completo não comprovado |
| Supplier | CSV principal e CSV de referência, hashes, auditoria de consistência de target e de consolidação | Origem/regra de Risk_Level, construção do índice geopolítico, janelas/denominadores dos indicadores e validade empresarial não comprovados |
| Purchase | Workbook e Vocabulary & Notes: linha, lead time efetivo, ESG simulado e moedas sem câmbio | Simulação ESG não prova que toda a fonte seja sintética; regras das demais classificações e disponibilidade pré-aprovação ainda precisam de evidência |
| Procurement KPI | CSV auxiliar identificado na inspeção histórica; extrator preservado | Finalidade restrita a apoio; não é fonte de treinamento nem evidência de validação dos três modelos |

Autoria, URL da publicação original, versão/data de obtenção e condições de uso de cada fonte ainda precisam ser consolidadas a partir de evidência verificável; essas informações não foram inventadas no fechamento registrado acima.

Nome de arquivo, quantidade de linhas e hash comprovam identidade/integridade de uma cópia, não autenticidade dos fatos ou validade do target. Os hashes já registrados permanecem preservados; nenhum dataset ou resultado é regenerado nesta revisão documental.

## 3. Integração de scores e histórico das hipóteses

### 3.1. Hipótese histórica de integração transacional — não adotada

A proposta inicial cogitava relacionar faturas e pedidos por número do pedido, fornecedor, item ou contrato. Ela foi substituída: as fontes atuais não possuem chaves reais comuns e pertencem a populações diferentes. Não se realizará essa junção, nem será inferida identidade a partir de IDs semelhantes.

### 3.2. Hipótese histórica de enriquecimento por fornecedor — não adotada

A ideia de enriquecer as faturas deste dataset com atributos dos fornecedores do dataset externo é mantida somente como registro histórico, não como experimento planejado. Na arquitetura atual, cada domínio prepara suas próprias features. A única possibilidade conceitual de integração preservada é uma camada de scores independentes, sujeita a contexto verificável e avaliação própria; nem mesmo scores devem ser associados a uma mesma entidade sem evidência dessa identidade.

### 3.3. Experimentos independentes

A decisão arquitetural prevê pipelines e modelos independentes para os domínios externos. As possibilidades abaixo incluem a classificação Supplier já avaliada e trabalhos ainda futuros:

- possível detecção de anomalias em linhas de pedido, sem escolha metodológica aprovada e condicionada ao gate Purchase;
- classificação supervisionada da classe de risco fornecida pelo dataset de fornecedores, cuja avaliação acadêmica já foi concluída;
- demonstrações adicionais do sistema;
- comparação de diferentes conjuntos de features;
- desenvolvimento de regras de negócio e visualizações complementares.

Essa alternativa preserva a validade metodológica e evita junções artificiais entre populações distintas.

### 3.4. Arquitetura futura de dados

Em uma evolução para banco de dados, as fontes poderão ser representadas por entidades separadas, como:

- faturas;
- pedidos de compra;
- fornecedores;
- contratos;
- entregas;
- avaliações de risco;
- resultados de detecção de anomalias.

Essa organização permitiria manter os dados originais, registrar transformações e disponibilizar diferentes visões analíticas sem misturar labels, features e resultados do modelo.

## 4. Estratégia de evolução do modelo

A evolução ocorre por domínio, sem fusão das features das três fontes. Os cenários antigos V2/V3 foram substituídos. A preparação Supplier foi seguida por experimentos e avaliação final acadêmica LR/C, documentada sem recálculo dos datasets preparados. Invoice concluiu os diagnósticos em VALIDATION e também a avaliação final única em TEST.

As etapas abaixo preservam diretrizes de evolução e etapas já percorridas. Não são uma lista de tarefas a repetir nem autorizam tuning, reprocessamento ou novas consultas a TEST no fechamento atual.

### Etapa 1 — Baseline atual

- manter as 19 features do dataset principal;
- preservar o Isolation Forest legado: o script prevê uso somente de TRAIN, mas os bytes/IDs do fit original não estão certificados;
- definir métricas e protocolo de avaliação com validação e teste;
- registrar parâmetros, features e artefatos do experimento.

### Etapa 2 — Avaliação da baseline

- analisar scores de anomalia;
- estudar diferentes thresholds sem utilizar o teste para ajuste;
- medir precisão, recall, F1, PR-AUC e comportamento por tipo de fraude, quando aplicável;
- investigar falsos positivos e falsos negativos;
- documentar limitações e estabilidade dos resultados.

### Etapa 3 — Experimentos com dados externos

- validar qualidade, duplicidades, valores nulos e escalas;
- manter a decisão de não realizar integração direta das fontes atuais;
- testar datasets externos primeiro em pipelines independentes;
- criar features agregadas utilizando somente informações permitidas;
- comparar cada experimento com a baseline do próprio domínio, sem comparar diretamente métricas de populações e objetivos distintos.

### Etapa 4 — Evolução independente de cada modelo

- comparar somente features justificadas da fonte do próprio domínio, sem merge entre os datasets atuais;
- reavaliar hiperparâmetros e threshold em validação; contaminação é uma questão do Invoice, não do classificador Supplier Risk;
- verificar estabilidade e sensibilidade a categorias não vistas, sem alegar estabilidade temporal no Supplier sem sequência temporal adequada;
- versionar metadados, transformações e modelos de maneira reproduzível.

### Etapa 5 — Camadas especializadas

O sistema poderá evoluir para combinar diferentes sinais:

- anomalia transacional de faturas;
- eventual sinal Purchase, cujo significado ainda depende do gate metodológico;
- risco estrutural de fornecedores;
- regras de negócio explicáveis;
- priorização final de alertas.

Essas camadas devem manter saídas separadas e auditáveis. Uma eventual combinação deverá informar a contribuição de cada componente para o alerta final.

## Critérios de avaliação e sucesso

A evolução do modelo será considerada positiva quando demonstrar ganho mensurável e consistente em relação à baseline atual. A inclusão de novas fontes ou features não será considerada uma melhoria apenas por aumentar a complexidade do sistema.

Os principais critérios de sucesso são:

- apresentar melhora comparativa contra a baseline atual;
- aumentar a capacidade de identificar anomalias relacionadas às fraudes conhecidas;
- reduzir falsos positivos sem comprometer de forma desproporcional a identificação de casos relevantes;
- manter estabilidade entre os conjuntos de treino, validação e teste;
- apresentar comportamento coerente por categoria de fraude;
- manter rastreabilidade completa das features utilizadas.

As métricas e análises possíveis incluem:

- Precision;
- Recall;
- F1-score;
- PR-AUC;
- análise de falsos positivos;
- análise de falsos negativos.

No Invoice, treinado de forma não supervisionada, os labels conhecidos são usados após o treinamento como referência não comprovada de avaliação. No Supplier Risk, `Risk_Level` foi usado como target supervisionado, nunca como feature. Os critérios por categoria de fraude acima são específicos de Invoice, não do Supplier. Escolhas usam dados de desenvolvimento; TEST não retroalimenta decisões, inclusive após a avaliação Supplier já concluída.

**Supplier — protocolo 1.0 de 2026-09-14, sequência acadêmica concluída:** EDA em TRAIN → baseline majoritária → Logistic Regression/RandomForestClassifier → comparação em VALIDATION → congelamento LR/C → avaliação final única em TEST. As ablações e a CV exploratória precederam essa escolha. O [protocolo detalhado](supplier_risk_model.md) preserva as decisões anteriores aos resultados; o [relatório final](supplier_risk_final_evaluation.md) registra a execução. Não há nova rodada autorizada, XGBoost ou modelo de produção. RandomForestClassifier foi o primeiro modelo não linear do protocolo.

As ablações pré-definidas foram A (10 features), B (sem `geopolitical_risk_index`), C (sem `supplier_record_count`) e D (sem ambas). As quatro foram comparadas em VALIDATION; a CV posterior comparou A/D sem selecionar uma versão final nessa etapa.

Permanece a ressalva de que o conjunto mais completo não é presumido superior: o índice provisório e a contagem potencialmente associada à coleta exigem decisão de procedência, não escolha automática pelo maior valor pontual.

Métrica principal: **F1-macro**. Secundárias: precision/recall/F1 das classes 0 e 1, balanced accuracy, ROC-AUC, PR-AUC reportada como Average Precision e confusion matrix; accuracy é complementar. Utilidade mínima exige ganho claro sobre a classe majoritária de TRAIN em F1-macro e balanced accuracy, com identificação de ambas as classes, sem meta arbitrária de F1. Os relatórios de [baselines](supplier_risk_baseline_models.md) e [validação científica](supplier_risk_validation_analysis.md) registram as etapas anteriores; a escolha final LR/C está documentada separadamente no relatório final, sem seleção por TEST.

Logistic Regression usa `SimpleImputer → StandardScaler → LogisticRegression` dentro de Pipeline, aprendido somente no TRAIN. Na CV interna concluída, cada fold aprendeu seus próprios transformadores a partir da base com nulos e dos IDs de TRAIN; o X_train já imputado sobre todo o TRAIN não foi usado.

O ML-Ready atual continua válido para experimentos simples train/validation, sem alteração de artefatos. Qualquer CV futura deve preservar esse isolamento.

O protocolo reserva TRAIN à exploração, ao ajuste e ao treinamento; VALIDATION à seleção de features, modelos, hiperparâmetros e threshold; TEST somente à avaliação final. Não usar TEST para EDA, tuning ou calibração.

`predict_proba()` não garante probabilidades confiáveis. A avaliação de calibration curve, Brier score e possível CalibratedClassifierCV permanece planejada para uma etapa futura, com dados de desenvolvimento. Esse planejamento deve preceder a exibição de percentuais de pertencimento à classe 1 e não permite ajuste em TEST. A saída significa somente pertencimento à classe 1, não falha real ou futura.

O protocolo atual não prevê refit em TRAIN + VALIDATION.

A EDA TRAIN já investigou classes, distribuições, estatísticas, outliers, diferenças entre classes, correlações e possíveis proxies; suas observações não resolvem a procedência das features ou da label.

## Arquitetura futura de modelos especializados

A separação em camadas independentes já é a decisão arquitetural vigente; sua implementação evolui por domínio. Essa separação facilita a auditoria, a comparação de desempenho e a identificação da origem de cada alerta.

### Modelo 1 — Detecção de anomalias transacionais

**Entrada:**

- invoices.

**Saída:**

- `invoice_anomaly_score`.

Esse modelo representa a baseline atual e busca identificar faturas com comportamento incomum em relação ao histórico transacional.

### Modelo 2 — Avaliação de risco de fornecedor

**Entrada:**

- Supplier Risk Assessment Dataset.

**Saída:**

- classe prevista (`0 = menor risco`, `1 = maior risco`);
- para modelos compatíveis, probabilidade estimada de pertencimento à classe 1 (eventual `supplier_risk_score`, sem significado de probabilidade real de falha).

Essa camada é uma classificação supervisionada de `Risk_Level`, não detecção genérica de anomalias nem previsão de eventos futuros. A label permanece fora das features e sua procedência não está comprovada.

### Modelo 3 — Análise de performance operacional

**Entrada:**

- Purchase Orders & Supplier Performance Dataset.

**Saída:**

- `purchase_risk_score`.

Esse é um nome histórico: o significado da saída ainda depende de escolher anomalia ou um desfecho específico. As entradas pré-aprovação não podem conter prazo realizado, status pós-evento ou resultados da própria entrega. A granularidade disponível é linha de pedido; não se presume risco real a partir de um perfil incomum.

Os três scores devem permanecer separados, versionados e auditáveis antes de qualquer combinação em um score geral. Uma futura composição deverá possuir regra explícita, justificativa metodológica, pesos documentados e avaliação própria, sem ocultar as saídas individuais dos modelos especializados.

## Versionamento dos experimentos

Os experimentos serão organizados em versões evolutivas para permitir comparação objetiva e reprodução dos resultados.

O versionamento dos três modelos especializados é independente. Métricas entre populações e objetivos diferentes não são diretamente comparáveis. A nomenclatura V1/V2/V3 abaixo registra uma decisão antiga substituída; não constitui sequência de implementação ou autorização para juntar fontes.

### Modelo V1 — Baseline

**Características:**

- somente o Procurement Invoice Fraud Dataset;
- 19 features atuais;
- Isolation Forest inicial.

### Hipótese histórica V2 — substituída

O desenho antigo combinava Invoice e Purchase Orders. Não será implementado com esses datasets, que não possuem chaves reais comuns. O Purchase evolui como domínio independente; não se prevê comparação direta de suas métricas com a V1 do Invoice.

### Hipótese histórica V3 — substituída

O desenho antigo combinava features de Invoice, Purchase e Supplier. Foi substituído por três modelos especializados, com fontes separadas. Somente uma eventual camada conceitual de integração de **scores**, com contexto comum verificável, poderá ser estudada no futuro. Não é junção direta das features desses datasets.

Cada versão deve possuir:

- conjunto de features documentado;
- parâmetros registrados;
- métricas comparáveis;
- modelo versionado.

Além do artefato do modelo, o registro do experimento deve identificar os datasets utilizados, a data de execução, as transformações aplicadas e a versão do código responsável pelo treinamento.

## 5. Limitações atuais

As principais limitações identificadas são:

- Supplier Risk já possui pipeline ML-Ready, EDA e experimentos TRAIN/VALIDATION; Purchase ainda não possui preparação de features ou modelagem;
- os identificadores das três fontes não possuem correspondência real comum que permita integração direta;
- as fontes podem representar populações, períodos, moedas e processos de negócio diferentes;
- Supplier Risk preserva nulos na base e possui split/imputação train-only, experimentos e avaliação final concluídos; validade externa/temporal e uso operacional permanecem sem comprovação;
- a origem e a regra de `Risk_Level` não foram comprovadas; consistência por ID não comprova validade operacional e o objetivo é reproduzir a classificação do dataset, não prever risco real;
- os scores externos podem ter regras de construção desconhecidas e precisam ser auditados antes de virar features;
- datas e eventos devem ser alinhados para impedir o uso de informações futuras;
- StandardScaler foi aplicado somente dentro dos Pipelines experimentais de Logistic Regression, ajustado em TRAIN ou no subtreino de cada fold; os artefatos ML-Ready continuam sem scaling e não foram sobrescritos;
- a baseline atual cobre faturas, mas ainda não representa todo o ciclo de compras;
- os labels conhecidos do dataset principal podem conter inconsistências e são reservados para avaliação;
- o uso de uma taxa fixa de contaminação no Isolation Forest é uma hipótese inicial que ainda precisa ser validada;
- os resultados ainda não devem ser interpretados como evidência conclusiva de fraude, mas como sinais para investigação.

## 6. Diretrizes de governança e reprodutibilidade

Cada experimento futuro deverá registrar:

- domínio e versão do modelo;
- fonte e versão dos dados;
- unidade de análise;
- momento de scoring;
- conjunto e ordem das features;
- critérios de exclusão;
- estratégia de divisão dos dados;
- parâmetros e semente aleatória;
- métricas de treino, validação e teste;
- data de execução;
- hash ou versão do código responsável pelo treinamento.

Os artefatos de Supplier Risk e Purchase Risk não devem compartilhar diretórios ou nomes de arquivo. Essa separação evita sobrescritas e permite restaurar cada experimento de maneira independente.

O registro também identifica os arquivos utilizados e seus hashes quando previstos, o conjunto usado para ajustar cada transformação, as fórmulas, os resultados, as limitações e as decisões metodológicas.

Os datasets devem permanecer fora do versionamento Git. O repositório deve armazenar apenas scripts, documentação, configurações, metadados permitidos e arquivos necessários para reproduzir a estrutura do projeto.

**IMPLEMENTADO:** o [contrato de registros experimentais Supplier](supplier_risk_experiment_records.md) oferece API/CLI JSON verificável para predições de novas execuções TRAIN/VALIDATION por estimador/configuração/cenário. Não contém predições históricas reais nem aceita TEST nessa versão; checksum não comprova procedência. O contrato e manifest da avaliação final são separados, conforme a seção 9 dos registros experimentais.

**LIMITAÇÃO:** as predições individuais das rodadas históricas não foram persistidas e não foram fabricadas retroativamente; hashes e checksums comprovam coerência interna, não procedência nem ausência de leitura de TEST.

**IMPLEMENTADO separadamente:** helpers, contrato final e manifest Supplier. Isso não refatora retroativamente os notebooks históricos nem todos os produtores.

**PLANEJADO:** publicação transacional dos pipelines de preparação ainda sequenciais e notebooks futuros como consumidores de módulos testáveis. Hoje uma falha intermediária de preparação pode deixar arquivos antigos e novos misturados; metadata publicada por último não constitui transação multi-arquivo. Não reprocessar artefatos para resolver essa limitação nesta etapa.

A suíte pytest persistida em `tests/supplier_risk/` usa apenas dados sintéticos e diretórios temporários. As dependências permanecem fixadas em `requirements.txt` e `requirements-dev.txt`.

No histórico do ambiente, em 2026-09-14, `.python-version` foi restaurado ao conteúdo versionado 3.14.3 após confirmar exclusão apenas local, não causada por regra de ignore; não há evidência de qual processo o excluiu. Naquele fechamento, os requirements e a `.venv` principal não foram modificados.

As sondagens anteriores de venvs isoladas em Python 3.14.3 e 3.13.14 não resolveram pandas 2.2.2 por wheels. Em **2026-09-16**, uma instalação completa em Windows x64 / Python 3.14.3 foi comprovada ao substituir somente pandas por **2.3.3**, preservando os outros 21 pins. Isolamento, `pip check`, Ruff e 113 testes sintéticos foram aprovados. Naquela validação, a `.venv` principal antiga foi preservada; nenhuma fonte, Parquet, target, split, metadata de dados ou modelo foi reprocessado.

**IMPLEMENTADO:** requisitos corrigidos e CI configurada para instalação limpa e testes sintéticos. Sua execução remota não foi consultada nesta auditoria; outras plataformas/versões e reprodução de resultados reais não são comprovadas pela suíte sintética. Metadados dos artefatos mantêm suas versões históricas. O [registro de ambiente no README](../README.md#instalação) concentra comandos, versões e limites.

### Organização dos artefatos e pipelines

```text
ml/
├── scripts/         # Invoice e inspeções históricas
├── models/          # Invoice: metadata e artefato local
├── notebooks/       # EDA Invoice
├── experiments/     # Evidências Invoice
└── supplier_risk/
    ├── scripts/
    ├── notebooks/
    └── experiments/
```

Responsabilidades dos diretórios existentes:

- `scripts/`: validação, preparação de dados, feature engineering, treinamento e avaliação do domínio correspondente;
- `models/`: artefatos locais dos modelos treinados e metadados permitidos;
- `notebooks/`: exploração e experimentação acadêmica, sem substituir os pipelines reproduzíveis em scripts.

Arquivos binários de modelo nos formatos `.joblib` e `.pkl` permanecem fora do versionamento Git. Purchase está documentado em [purchase_risk_model.md](purchase_risk_model.md); não possui pipeline implementado e não depende de diretórios vazios para representar seu planejamento.

### Responsabilidades dos pipelines

Cada pipeline especializado deverá ser independente e executar, no mínimo, as seguintes responsabilidades:

1. localizar e validar os arquivos de entrada;
2. confirmar esquema, unidade de análise e período de referência;
3. separar treino, validação e teste antes do ajuste de transformações;
4. tratar duplicidades e valores nulos em uma camada processada;
5. ajustar codificação, imputação e estatísticas exclusivamente no treino;
6. gerar a matriz de features com ordem e tipos documentados;
7. treinar o modelo somente após aprovação metodológica;
8. avaliar o score sem utilizar labels como features;
9. salvar modelo, parâmetros, lista de features e metadados de execução;
10. manter os datasets originais imutáveis.

No Supplier, preparação, split, imputação train-only, EDA, baselines e CV exploratória foram seguidos por congelamento LR/C e avaliação final acadêmica, sem refit TRAIN+VALIDATION. Os testes dos pipelines usam exclusivamente fixtures sintéticas e diretórios temporários, sem reprocessar dados reais. Os scripts de preparação já possuem funções reutilizáveis e blocos `main` protegidos.

Helpers e contrato final Supplier já existem; não se presume que isso tenha refatorado todos os produtores históricos. Notebooks futuros deverão consumir módulos testáveis com allowlist de splits, sem reescrever evidência histórica nem reabrir TEST. As alterações locais preexistentes dos notebooks 01/02 estão preservadas; a distinção entre bytes atuais e congelados consta na nota de rastreabilidade do relatório final.

### Controles contra data leakage

Os controles mínimos são:

- excluir labels, classificações finais e resultados derivados do target da matriz de features; permitir `Risk_Level` apenas como y supervisionado;
- definir explicitamente o instante em que cada score é calculado;
- excluir informações indisponíveis nesse instante;
- calcular agregações históricas somente com dados anteriores ao evento quando existir histórico comprovado; não atribuir temporalidade à consolidação atual de Supplier;
- ajustar transformações exclusivamente no conjunto de treino;
- reservar validação para decisões de modelagem e teste para avaliação final;
- documentar a origem e a fórmula de scores externos antes de utilizá-los.

### Recursos externos após clonagem

O clone não contém os datasets nem os modelos binários. Diretórios vazios não
são versionados: ao provisionar uma fonte autorizada, crie seu diretório conforme
os caminhos da seção 1 e coloque somente os arquivos da versão correspondente.
Por exemplo, a preparação manual dos diretórios auxiliares/externos em PowerShell
pode usar:

```powershell
New-Item -ItemType Directory -Force -Path data/auxiliary, data/external/purchase_orders, data/external/supplier_risk
```

Esse comando cria somente diretórios; não baixa, valida ou autoriza uso dos dados.
O extrator auxiliar já cria seu diretório de destino. Os produtores Supplier
criam os diretórios de saída ao executar, mas não devem ser chamados apenas para
recriar pastas ou repetir um estudo encerrado. `ml/supplier_risk/models/` continua
sendo um destino futuro possível, não um modelo de produção fornecido no clone.

Para reproduzir o uso dos artefatos acadêmicos, são necessários os arquivos e
versões externas, o modelo Invoice compatível com sua metadata e as dependências
adequadas. Disponibilidade da fonte e procedência do fit legado não são provadas
por um clone bem-sucedido; retreinar não substitui automaticamente esse artefato.
As avaliações finais concluídas não devem ser repetidas para testar a instalação.

## 7. Conclusão

A estratégia atual define três domínios independentes, com Purchase ainda sem modelo, com prevenção de vazamento e rastreabilidade como requisitos metodológicos. O Procurement Invoice Fraud Dataset permanece como fonte principal do Invoice Anomaly; Supplier Risk e Purchase Orders são fontes principais dos respectivos modelos. O Procurement KPI permanece exclusivamente auxiliar nesta fase.

As fontes permanecem independentes. A evolução se dará por experimentos dentro de cada domínio; uma integração de scores não implica identidade entre registros nem comprovação de risco operacional. As conclusões do Supplier ficam limitadas à classificação de risco fornecida pelo dataset. Gates e responsabilidades até a implementação operacional estão no [roadmap](implementation_roadmap.md).
