# Purchase Risk Model

## 1. Objetivo

O **Purchase Risk Model** permanece um domínio independente para análise pré-aprovação de compras. **PLANEJADO / decisão pendente:** escolher entre (A) detecção de anomalias, isto é, perfis estatisticamente incomuns, e (B) previsão de um desfecho específico, que exigirá target, horizonte e protocolo de avaliação próprios. Nenhuma dessas alternativas foi escolhida neste fechamento.

O nome histórico `purchase_risk_score` não estabelece o significado da saída. Anomalia não será chamada automaticamente de risco: pode representar uma compra legítima excepcional. Se a opção A for adotada, o score deverá ser apresentado como anomalia/prioridade de investigação; se a opção B for adotada, será necessário especificar qual desfecho ele estima. Os resultados continuarão separados dos demais domínios.

Esta etapa documenta somente o contrato arquitetural. Nenhum modelo ou feature é criado.

## 2. Unidade de análise

**EVIDÊNCIA CONFIRMADA:** a aba `Vocabulary & Notes` define `PO_Number` como identificador único de uma **linha de pedido**. Na aba `Data`, o nome correspondente é `PO Number`; os 5.200 valores distintos identificam linhas, não comprovam a existência de 5.200 cabeçalhos de pedidos completos.

A intenção histórica de modelar pedido completo não está comprovada pela granularidade disponível. Para agregar várias linhas em um pedido será necessária uma chave de cabeçalho e regra justificadas; não inventar agrupamentos. Até essa decisão, a fonte deve ser descrita como linhas de pedido. Não foi executada agregação nem feature engineering.

## 3. Momento de scoring

O scoring futuro terá como fronteira **antes da aprovação do pedido de compra**, independentemente da alternativa de modelagem que vier a ser escolhida.

Essa decisão define a fronteira temporal do modelo: somente informações disponíveis até o instante anterior à aprovação poderão participar das features. Resultados de entrega, faturamento e pagamento não estarão disponíveis e deverão ser excluídos.

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

### 7.2. Classificações e resultados existentes

Os campos abaixo devem ser excluídos inicialmente e reservados para análise ou avaliação até que sua origem seja auditada:

- `Supplier Risk`;
- `Supplier Status`;
- `PO Status`;
- `Maverick Spend`.

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

O pipeline de feature engineering deverá:

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

**Instante de scoring:** antes da aprovação.  
**Features:** somente informações disponíveis até esse instante.  
**Saída planejada:** significado pendente da escolha entre anomalia e desfecho específico; `purchase_risk_score` é nome histórico, não validação de risco.

**Artefatos futuros:** `ml/purchase_risk/models/`.

O pipeline deverá registrar a lista ordenada de features, a política temporal, as categorias aprendidas, os parâmetros e os metadados de cada execução.

## 11. Critérios de prontidão

O treinamento somente deverá começar depois que:

- a unidade de análise estiver confirmada;
- a alternativa anomalia vs. desfecho específico estiver escolhida, com significado do score e avaliação definidos;
- o instante de aprovação estiver representado ou metodologicamente definido;
- todas as variáveis pós-evento estiverem excluídas;
- moeda e datas tiverem tratamento documentado;
- classificações existentes tiverem origem auditada;
- a divisão entre treino, validação e teste estiver definida;
- testes confirmarem ausência de data leakage temporal.
