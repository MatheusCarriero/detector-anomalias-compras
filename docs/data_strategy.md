# Estratégia de Dados

## 1. Visão geral

O projeto **Detector Inteligente de Anomalias em Compras** utiliza dados de faturas, pedidos de compra e risco de fornecedores para estudar comportamentos incomuns em processos de aquisição. A estratégia de dados foi organizada para permitir uma evolução gradual: primeiro, estabelecer uma linha de base confiável com o dataset principal; depois, avaliar fontes externas como contexto operacional e como suporte a análises complementares.

Atualmente, o modelo utiliza exclusivamente o **Procurement Invoice Fraud Dataset**. Os datasets externos estão organizados e disponíveis para exploração, mas ainda não participam do treinamento, da geração das 19 features atuais nem da avaliação do modelo.

Os princípios que orientam a estratégia são:

- separação clara entre dados brutos, externos e processados;
- preservação dos arquivos originais;
- uso exclusivo do conjunto de treino no cálculo de estatísticas históricas;
- prevenção de data leakage;
- rastreabilidade das features e transformações;
- validação da compatibilidade entre fontes antes de qualquer integração;
- evolução incremental, com comparação entre experimentos e manutenção de uma baseline reproduzível.

## Arquitetura atual de dados

A arquitetura atual separa o fluxo que já participa do treinamento das fontes que ainda estão em análise e preparação.

### Fluxo principal em operação

```text
Procurement Invoice Fraud Dataset
                 ↓
         Feature Engineering
                 ↓
          Isolation Forest
                 ↓
       Invoice Anomaly Score
```

### Fontes externas em preparação

```text
Purchase Orders Dataset
            ↓
Features operacionais futuras

Supplier Risk Dataset
            ↓
Features de risco futuras
```

Atualmente, somente o Procurement Invoice Fraud Dataset participa do treinamento do Isolation Forest. Os datasets externos não alimentam o modelo atual: eles permanecem em fase de análise, validação de qualidade e definição metodológica das futuras features.

## 2. Papel dos datasets

### 2.1. Dataset principal — Procurement Invoice Fraud Dataset

**Local:** `data/raw/`

O Procurement Invoice Fraud Dataset é a fonte principal do projeto e contém 300.000 registros relacionados a faturas, fornecedores, departamentos, valores, condições de pagamento e tipos conhecidos de fraude.

Seu papel é sustentar a primeira versão do sistema de detecção de anomalias. Ele oferece volume suficiente para separar os dados em treino, validação e teste e permite comparar os padrões encontrados pelo modelo com informações de fraude conhecidas.

Os labels não fazem parte das entradas do modelo. A coluna `is_fraud` é reservada para avaliação posterior, enquanto `fraud_type` pode ser utilizada em análises complementares. Campos que representam risco previamente conhecido, explicações ou informações derivadas do resultado também não devem ser utilizados como features.

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

#### Justificativa de utilização

O dataset principal reúne atributos transacionais e contexto suficiente para construir uma baseline de Machine Learning não supervisionado. O algoritmo atual é o **Isolation Forest**, escolhido por sua capacidade de identificar observações que apresentam combinações pouco frequentes de valores sem utilizar labels durante o treinamento.

### 2.2. Dataset externo — Purchase Orders & Supplier Performance Dataset

**Local:** `data/external/purchase_orders/`  
**Arquivo:** `Dataset_Procurement.xlsx`

O dataset possui 5.200 registros e 57 colunas. Ele reúne informações de pedidos de compra, fornecedores, preços, orçamento, descontos, tributos, entregas, compliance, contratos, status e desempenho operacional.

#### Papel no projeto

Sua principal contribuição potencial é adicionar contexto anterior e posterior à emissão de uma fatura. Enquanto o dataset principal descreve a transação faturada, os pedidos de compra podem representar a intenção de compra, os limites orçamentários, as condições negociadas e o desempenho da entrega.

Esse contexto pode ajudar a identificar situações como:

- preços realizados muito acima do orçamento;
- variações atípicas de preço para itens semelhantes;
- atrasos incompatíveis com o histórico do fornecedor;
- compras emergenciais ou com status incomum;
- concentração de pedidos em fornecedores de baixo desempenho;
- divergências entre condições contratadas e resultados observados.

#### Features planejadas

- `budget_deviation`: diferença absoluta ou relativa entre o valor realizado e o orçamento correspondente;
- `price_variation`: desvio do preço unitário em relação ao histórico do item, categoria ou fornecedor;
- `delivery_delay_score`: medida normalizada de atraso entre a data solicitada e a data efetiva de entrega;
- `supplier_performance_score`: indicador agregado de entrega, economia, compliance e consistência operacional;
- `lead_time_anomaly`: grau de desvio do lead time em relação ao comportamento histórico comparável;
- `purchase_status_risk`: representação do risco associado ao status e ao fluxo do pedido de compra.

Essas features são hipóteses de pesquisa. Suas fórmulas, janelas históricas e métodos de normalização deverão ser definidos e documentados antes de qualquer uso no modelo.

### 2.3. Dataset externo — Supplier Risk Assessment Dataset

**Local:** `data/external/supplier_risk/`

**Arquivos:**

- `raw_supplier_risk_dataset_1.csv`
- `supplier_risk_dataset.csv`

O pacote contém 28.098 registros. A versão enriquecida possui 17 colunas e adiciona contexto geográfico, industrial, qualidade de entrega e dependência do fornecedor aos indicadores presentes na versão bruta.

#### Papel no projeto

Esse dataset pode sustentar uma camada independente de análise de risco de fornecedores. Em vez de observar somente uma transação, essa camada representaria características estruturais e históricas do fornecedor, incluindo estabilidade financeira, qualidade, entregas, compliance, risco geopolítico e dependência operacional.

Uma pontuação de fornecedor pode ser utilizada futuramente como contexto para investigação, segmentação de alertas ou priorização de casos. Entretanto, qualquer indicador que tenha sido calculado a partir de fraude conhecida, eventos futuros ou informações indisponíveis no momento da transação deve ser excluído do treinamento para evitar data leakage.

#### Features planejadas

- `financial_risk_score`: síntese de estabilidade financeira e demais indicadores financeiros disponíveis;
- `delivery_risk_score`: combinação de pontualidade, lead time e histórico de interrupções;
- `quality_risk_score`: representação de defeitos, qualidade de entrega e consistência operacional;
- `compliance_risk_score`: indicador associado ao cumprimento de requisitos ambientais ou regulatórios;
- `supplier_dependency_score`: medida de dependência e disponibilidade de fornecedores alternativos.

Os scores planejados não devem ser tratados como equivalentes a labels de fraude. Antes do uso, será necessário investigar a origem, a escala, a distribuição e a construção de cada variável.

#### Controle sobre features de risco

Campos que representam o resultado final ou uma classificação consolidada de risco, como `Risk_Level`, `Risk_Category` e outras classificações derivadas, não devem ser utilizados diretamente como features no treinamento do Isolation Forest.

Esses campos devem ser reservados para:

- análise exploratória;
- avaliação;
- comparação de resultados;
- possíveis modelos supervisionados futuros.

Essa separação evita que o modelo receba uma representação direta ou indireta do resultado que se pretende analisar, reduzindo o risco de data leakage e preservando a validade dos experimentos.

## 3. Estratégias possíveis de integração

### 3.1. Integração transacional

Uma integração direta poderia relacionar faturas e pedidos de compra por identificadores como número do pedido, fornecedor, item ou contrato. Essa abordagem somente será válida se houver chaves compatíveis, cobertura suficiente e correspondência semântica entre as fontes.

Não se deve assumir que identificadores de datasets externos representam as mesmas entidades do dataset principal. Caso não exista correspondência verificável, os dados devem permanecer separados.

### 3.2. Integração por fornecedor

Se for possível criar um mapeamento confiável de fornecedores, atributos agregados de desempenho e risco poderão enriquecer as transações. Exemplos incluem médias históricas de atraso, frequência de defeitos, estabilidade financeira e dependência do fornecedor.

Todo agregado temporal deverá utilizar apenas informações disponíveis até a data da observação. Para treino, validação e teste, as estatísticas deverão ser ajustadas exclusivamente no conjunto de treino ou calculadas por janelas temporais que respeitem a ordem dos eventos.

### 3.3. Experimentos independentes

Na ausência de chaves compatíveis, os datasets externos ainda podem ser utilizados em experimentos independentes:

- detecção de anomalias em pedidos de compra;
- identificação de fornecedores com perfil de risco incomum;
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

A evolução recomendada deve ocorrer em etapas controladas.

### Etapa 1 — Baseline atual

- manter as 19 features do dataset principal;
- treinar o Isolation Forest somente com o conjunto de treino;
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
- definir chaves ou declarar formalmente a impossibilidade de integração direta;
- testar datasets externos primeiro em pipelines independentes;
- criar features agregadas utilizando somente informações permitidas;
- comparar cada experimento com a baseline, sem substituir automaticamente o modelo atual.

### Etapa 4 — Modelo enriquecido

- integrar somente features externas que apresentem justificativa metodológica e ganho mensurável;
- reavaliar contaminação, hiperparâmetros e threshold;
- verificar drift, estabilidade temporal e sensibilidade a categorias não vistas;
- versionar metadados, transformações e modelos de maneira reproduzível.

### Etapa 5 — Camadas especializadas

O sistema poderá evoluir para combinar diferentes sinais:

- anomalia transacional de faturas;
- anomalia operacional de pedidos;
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

Como o Isolation Forest é treinado de forma não supervisionada, os labels conhecidos devem ser utilizados somente após o treinamento, para avaliação. A escolha de threshold e o ajuste de hiperparâmetros devem ocorrer no conjunto de validação; o conjunto de teste deve permanecer reservado para a estimativa final de desempenho.

## Arquitetura futura de modelos especializados

A evolução prevista considera camadas independentes, cada uma responsável por um tipo de sinal. Essa separação facilita a auditoria, a comparação de desempenho e a identificação da origem de cada alerta.

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

- `supplier_risk_score`.

Essa camada deverá sintetizar indicadores permitidos de estabilidade financeira, qualidade, entrega, compliance e dependência, sem utilizar classificações finais de risco como features.

### Modelo 3 — Análise de performance operacional

**Entrada:**

- Purchase Orders & Supplier Performance Dataset.

**Saída:**

- `purchase_risk_score`.

Essa camada deverá representar desvios de preço, orçamento, prazo, status e desempenho observados nos pedidos de compra.

Os três scores devem permanecer separados, versionados e auditáveis antes de qualquer combinação em um score geral. Uma futura composição deverá possuir regra explícita, justificativa metodológica, pesos documentados e avaliação própria, sem ocultar as saídas individuais dos modelos especializados.

## Versionamento dos experimentos

Os experimentos serão organizados em versões evolutivas para permitir comparação objetiva e reprodução dos resultados.

### Modelo V1 — Baseline

**Características:**

- somente o Procurement Invoice Fraud Dataset;
- 19 features atuais;
- Isolation Forest inicial.

### Modelo V2 — Modelo enriquecido operacional

**Características:**

- features do dataset principal;
- features derivadas de Purchase Orders;
- comparação direta contra a V1.

### Modelo V3 — Modelo completo de risco

**Características:**

- features de invoices;
- features de pedidos;
- features permitidas de risco de fornecedores.

A implementação das versões V2 e V3 depende da validação de compatibilidade, qualidade, temporalidade e ausência de data leakage nas fontes externas. Caso não seja possível realizar uma integração confiável, os modelos especializados deverão permanecer como experimentos independentes.

Cada versão deve possuir:

- conjunto de features documentado;
- parâmetros registrados;
- métricas comparáveis;
- modelo versionado.

Além do artefato do modelo, o registro do experimento deve identificar os datasets utilizados, a data de execução, as transformações aplicadas e a versão do código responsável pelo treinamento.

## 5. Limitações atuais

As principais limitações identificadas são:

- os datasets externos ainda não foram integrados ao pipeline de Machine Learning;
- não há confirmação de que os identificadores de fornecedores ou transações sejam compatíveis entre as três fontes;
- as fontes podem representar populações, períodos, moedas e processos de negócio diferentes;
- o dataset de risco de fornecedores contém valores nulos e linhas duplicadas que precisarão de tratamento metodológico;
- os scores externos podem ter regras de construção desconhecidas e precisam ser auditados antes de virar features;
- datas e eventos devem ser alinhados para impedir o uso de informações futuras;
- diferenças de escala e distribuição exigirão transformações ajustadas somente no treino;
- a baseline atual cobre faturas, mas ainda não representa todo o ciclo de compras;
- os labels conhecidos do dataset principal podem conter inconsistências e são reservados para avaliação;
- o uso de uma taxa fixa de contaminação no Isolation Forest é uma hipótese inicial que ainda precisa ser validada;
- os resultados ainda não devem ser interpretados como evidência conclusiva de fraude, mas como sinais para investigação.

## 6. Diretrizes de governança e reprodutibilidade

Para preservar a qualidade acadêmica do projeto, cada nova etapa deverá registrar:

- fonte e versão do dataset;
- arquivos utilizados e seus hashes, quando necessário;
- critérios de limpeza e exclusão;
- definição exata das features;
- conjunto utilizado para ajustar cada transformação;
- parâmetros do modelo;
- data do experimento;
- métricas e resultados;
- limitações e decisões metodológicas.

Os datasets devem permanecer fora do versionamento Git. O repositório deve armazenar apenas scripts, documentação, configurações, metadados permitidos e arquivos necessários para reproduzir a estrutura do projeto.

## 7. Conclusão

A estratégia atual prioriza uma baseline simples, verificável e livre de vazamento de dados. O Procurement Invoice Fraud Dataset permanece como fonte principal do modelo, enquanto os datasets de pedidos de compra e risco de fornecedores ampliam as possibilidades de pesquisa.

A incorporação dessas fontes deverá ocorrer somente após validação de compatibilidade, qualidade e temporalidade. Essa abordagem permite expandir o sistema sem comprometer a rastreabilidade dos experimentos nem a validade dos resultados.
