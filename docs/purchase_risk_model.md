# Purchase Risk Model

## 1. Objetivo

O **Purchase Risk Model** permanece um domínio independente com uso pretendido pré-aprovação. **Decisão vigente da auditoria: C — não implementar o modelo ainda**, por insuficiência metodológica para demonstrar esse uso. Purchase permanece no gate metodológico, sem iniciar feature engineering ou treinamento.

O nome histórico `purchase_risk_score` não estabelece o significado da saída. A escolha anteriormente pendente entre detecção de anomalias e previsão de um desfecho específico continua sem aprovação. Se a detecção de anomalias vier a ser escolhida, o score deverá representar anomalia/prioridade de investigação: um perfil incomum pode ser uma compra legítima excepcional, não risco ou fraude comprovados. A alternativa supervisionada exigirá desfecho, população, horizonte e protocolo de avaliação próprios. Os resultados continuarão separados dos demais domínios.

Este documento registra a auditoria e as condições para um eventual pipeline. Nenhum modelo, target ou conjunto de features foi aprovado.

## 2. Unidade de análise

**EVIDÊNCIA CONFIRMADA:** a aba `Vocabulary & Notes` define `PO_Number` como identificador único de uma **linha de pedido**. Na aba `Data`, o nome correspondente é `PO Number`; os 5.200 valores distintos identificam linhas, não comprovam a existência de 5.200 cabeçalhos de pedidos completos.

A intenção histórica de modelar pedido completo não está comprovada pela granularidade disponível. Para agregar várias linhas em um pedido será necessária uma chave de cabeçalho e regra justificadas; não inventar agrupamentos. Até essa decisão, a fonte deve ser descrita como linhas de pedido. Não foi executada agregação nem feature engineering.

## 3. Momento de scoring

O uso pretendido mantém a fronteira **antes da aprovação do pedido de compra**, independentemente da alternativa de modelagem que vier a ser escolhida. A fonte ainda não permite demonstrar esse instante: não há timestamp explícito de aprovação nem histórico de alterações ou snapshots dos campos.

`PO Date` não é uma data de aprovação comprovada. Sua relação com a aprovação precisa ser esclarecida, assim como a existência de um timestamp/snapshot pré-aprovação que permita reconstruir as informações disponíveis naquele instante. Somente essas informações poderão participar de futuras features. Resultados de entrega, faturamento e pagamento deverão ser excluídos.

## 4. Fonte de dados

Diretório:

```text
data/external/purchase_orders/
```

Arquivo:

```text
Dataset_Procurement.xlsx
```

Planilhas identificadas:

| Planilha | Papel | Uso planejado |
| --- | --- | --- |
| `Data` | Transacional | Fonte candidata para o pipeline |
| `Calendar` | Auxiliar | Apoio futuro a transformações temporais |
| `Vocabulary & Notes` | Documental | Não deve entrar no pipeline de modelagem |

A planilha `Data` possui 5.200 linhas de pedido, 57 colunas, 15 fornecedores, nenhuma célula nula e nenhuma linha totalmente duplicada. Isso é completude estrutural, não comprovação de representatividade ou validade de risco.

### Evidências do dicionário e limitações — consolidação de 2026-09-14

As definições abaixo foram confirmadas no próprio `Vocabulary & Notes` na auditoria anterior. Essa aba é fonte documental, nunca linhas adicionais da matriz de treinamento. Seus nomes usam underscores; os cabeçalhos da aba `Data` usam espaços.

| Campo do dicionário | Evidência documentada | Consequência |
|---|---|---|
| `PO_Number` | Identificador de linha de pedido | Não assumir cabeçalho/pedido completo |
| `Lead_Time_Days` | Dias entre `PO_Date` e `Actual_Delivery` | Pós-evento; excluir das entradas pré-aprovação |
| `Supplier_ESG_Score` | Score simulado de 0 a 100 | Não representa sustentabilidade ou compliance real comprovados |
| `Currency` | Valores em GBP/EUR/USD/JPY/AUD, sem conversão cambial | Não comparar nem somar montantes brutos entre moedas |

Não se conclui que a fonte inteira seja sintética apenas porque ESG é simulado. Fórmula de simulação, procedência de outras classificações e validade operacional continuam não comprovadas. A definição de `Local_International` tem referência ao Reino Unido, não a qualquer país de implantação. Não foi identificada uma coluna explícita de data/hora de aprovação na auditoria: a disponibilidade pré-decisão deverá ser comprovada antes de desenvolver o modelo.

## 5. Grupos de variáveis candidatas

Os grupos abaixo são hipóteses anteriores preservadas para análise. Nenhuma variável desta lista está aprovada para uso pré-aprovação; a disponibilidade temporal deve ser demonstrada antes de qualquer seleção ou transformação.

### 5.1. Operação

- tipo do pedido;
- categoria e subcategoria;
- quantidade e unidade de medida;
- condições de pagamento;
- departamento e centro de custo;
- tipo de contrato;
- indicador de fonte única;
- data solicitada de entrega, após transformação temporal apropriada.

### 5.2. Financeiras

- preço unitário;
- percentual de desconto;
- percentual de imposto;
- preço unitário orçado;
- moeda.

Valores totais e montantes calculados deverão ser auditados para evitar redundância matemática com preço, quantidade, desconto, imposto e orçamento.

### 5.3. Fornecedor

- tier do fornecedor;
- indicador de fornecedor preferencial;
- classificação local ou internacional.

`Supplier ESG Score` é **explicitamente simulado** segundo o dicionário. Não será evidência de qualidade/conformidade real. Qualquer eventual uso exclusivamente experimental exigirá justificativa e auditoria de disponibilidade pré-aprovação; não é feature aprovada neste fechamento.

## 6. Variáveis pós-evento proibidas

As seguintes variáveis não devem entrar no modelo calculado antes da aprovação:

1. `Actual Delivery`
2. `Days Late`
3. `On Time Delivery`
4. `Invoice Status`
5. `Payment Status`
6. `Invoice Match Type`

Esses campos descrevem resultados posteriores à decisão e causariam data leakage temporal.

`Lead Time Days` também permanece fora da primeira versão: o dicionário confirma que utiliza a entrega efetiva. Um prazo planejado seria outra variável, cuja origem e disponibilidade precisariam ser comprovadas; não reinterpretar esse campo realizado como planejado.

## 7. Outros campos que não devem ser usados diretamente

### 7.1. Identificadores e textos de alta cardinalidade

- `PO Number`;
- `Supplier ID`;
- `Supplier Name`;
- `Item Code`;
- `Item Description`;
- `Requestor Name`;
- `Approver Name`;
- `Contract ID`.

Esses campos devem servir para rastreabilidade, junções ou agregações, não como valores nominais apresentados diretamente ao modelo.

Isso não aprova junções nem uso temporal: `Approver Name` não comprova disponibilidade antes da aprovação. A interpretação de `Contract ID` e do marcador `NO-CONTRACT` ainda precisa ser esclarecida; sua presença, ausência ou preenchimento não certifica vínculo contratual válido nem irregularidade.

### 7.2. Classificações e resultados existentes

Os campos abaixo devem ser excluídos inicialmente e reservados para análise ou avaliação até que sua origem seja auditada:

- `Supplier Risk`;
- `Supplier Status`;
- `PO Status`;
- `Maverick Spend`.

`Supplier Risk` é uma classificação preexistente do workbook Purchase, não um desfecho comprovado nem a saída do modelo do domínio Supplier. A semântica e o instante de atribuição dos status administrativos e de `Maverick Spend` permanecem pendentes; não devem ser convertidos automaticamente em labels de risco ou fraude.

`Days Late`, `On Time Delivery` e `Lead Time Days` são candidatos a desfechos de entrega, mas continuam proibidos como entradas pré-aprovação da própria linha. `Maverick Spend` é outro candidato a target, condicionado à comprovação da regra, procedência e momento de classificação. Nenhum deles é target aprovado. A falta de um target aprovado também não torna a detecção de anomalias uma decisão metodológica nem resolve o leakage temporal.

### 7.3. Campos calculados ou redundantes

Exigem validação de fórmula, disponibilidade e redundância:

- `Discount Amount`;
- `Tax Amount`;
- `Line Total Gross`;
- `Line Net`;
- `Line Total Inc Tax`;
- `Budget Total`;
- `Savings Amount`;
- `Savings Pct`.

## 8. Compliance e qualidade

Não foi identificada uma coluna explicitamente denominada compliance na planilha transacional. `Supplier ESG Score` é um score simulado e não deve ser interpretado como comprovação de compliance, sustentabilidade ou qualidade real do fornecedor. Classificações existentes, como `Maverick Spend`, também requerem validação antes de qualquer uso como referência de avaliação.

Caso novos indicadores sejam incorporados, será necessário confirmar:

- origem e metodologia;
- instante de disponibilidade;
- faixa e significado do score;
- relação com classificações finais;
- risco de duplicar informações já presentes em outras variáveis.

## 9. Preparação futura

As diretrizes abaixo só se aplicam depois de superar o gate metodológico. Não autorizam iniciar o pipeline de feature engineering, que deverá:

- respeitar a unidade de linha confirmada pela fonte ou justificar agregação por chave real de pedido;
- aplicar o corte temporal anterior à aprovação;
- remover campos pós-evento da matriz de entrada;
- preservar identificadores apenas para rastreabilidade;
- interpretar datas com formato explícito;
- tratar moedas locais sem câmbio antes de comparar valores financeiros; eventual conversão exige fonte e data de referência, ou comparações restritas a grupos homogêneos;
- ajustar codificações exclusivamente no treino;
- lidar com categorias não observadas;
- calcular estatísticas históricas sem utilizar validação ou teste;
- manter os dados originais imutáveis.

Possíveis conceitos futuros incluem desvio de orçamento, variação de preço, concentração por fornecedor e anomalia de prazo planejado. Suas fórmulas ainda não estão definidas e não são implementadas nesta etapa.

## 10. Contrato do pipeline futuro

**Entrada:** planilha transacional `Data`, após validação.  
**Unidade disponível:** linha de pedido; agregação por pedido completo ainda não comprovada.

**Instante de scoring pretendido:** antes da aprovação, ainda não demonstrável pela fonte.

**Features:** nenhuma lista aprovada; somente informações com disponibilidade comprovada até esse instante poderão ser escolhidas.

**Saída planejada:** significado pendente da escolha entre anomalia e desfecho específico; `purchase_risk_score` é nome histórico, não validação de risco.

**Artefatos futuros:** `ml/purchase_risk/models/`.

O pipeline deverá registrar a lista ordenada de features, a política temporal, as categorias aprendidas, os parâmetros e os metadados de cada execução.

## 11. Critérios de prontidão

Feature engineering e treinamento permanecem bloqueados até que:

- a linha de pedido confirmada seja mantida como unidade, ou uma agregação tenha chave e justificativa verificáveis;
- a relação entre `PO Date` e aprovação seja esclarecida, com evidência de timestamp/snapshot pré-aprovação e disponibilidade temporal de cada variável;
- a semântica dos status administrativos, de `Contract ID` e de `NO-CONTRACT` seja esclarecida;
- a procedência, regra e momento de atribuição de `Supplier Risk`, `Maverick Spend` e demais classificadores sejam documentados;
- a alternativa anomalia vs. desfecho específico seja escolhida, com significado da saída e avaliação definidos; no caso supervisionado, com população, horizonte de observação e target aprovados;
- todas as variáveis pós-evento sejam excluídas das entradas, com controle de leakage temporal e semântico;
- moeda, datas e divisão entre treino, validação e teste tenham tratamento documentado.

Antes de treinar, testes deverão verificar as regras de prevenção de leakage definidas nesse contrato. Testes técnicos não substituem a evidência de disponibilidade temporal hoje ausente.
