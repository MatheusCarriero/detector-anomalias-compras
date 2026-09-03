# Purchase Risk Model

## 1. Objetivo

O **Purchase Risk Model** será um modelo especializado na identificação de pedidos de compra com perfil operacional ou financeiro incomum. Sua saída planejada é o `purchase_risk_score`, mantido separadamente dos scores de fornecedores e faturas.

Esta etapa documenta somente o contrato arquitetural. Nenhum modelo ou feature é criado.

## 2. Unidade de análise

A unidade de análise será o **pedido de compra**.

Antes do desenvolvimento, o pipeline deverá confirmar se cada linha representa um pedido completo ou uma linha de item. Caso um pedido possa conter várias linhas, será necessário definir formalmente o nível de agregação sem alterar o arquivo original.

## 3. Momento de scoring

O `purchase_risk_score` será calculado **antes da aprovação do pedido de compra**.

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

A planilha `Data` possui 5.200 registros, 57 colunas, 15 fornecedores, nenhuma célula nula e nenhuma linha totalmente duplicada.

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

`Supplier ESG Score` poderá representar contexto de qualidade ou conformidade, mas sua metodologia e disponibilidade no instante do scoring deverão ser auditadas antes do uso.

## 6. Variáveis pós-evento proibidas

As seguintes variáveis não devem entrar no modelo calculado antes da aprovação:

1. `Actual Delivery`
2. `Days Late`
3. `On Time Delivery`
4. `Invoice Status`
5. `Payment Status`
6. `Invoice Match Type`

Esses campos descrevem resultados posteriores à decisão e causariam data leakage temporal.

`Lead Time Days` também deverá permanecer fora da primeira versão enquanto representar o tempo efetivamente observado entre o pedido e a entrega. Ele só poderá ser utilizado antes da aprovação se houver uma definição comprovadamente planejada e disponível naquele instante.

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

Não foi identificada uma coluna explicitamente denominada compliance na planilha transacional. `Supplier ESG Score` é o indicador mais próximo de qualidade, sustentabilidade ou conformidade do fornecedor, mas não deve ser interpretado automaticamente como compliance.

Caso novos indicadores sejam incorporados, será necessário confirmar:

- origem e metodologia;
- instante de disponibilidade;
- faixa e significado do score;
- relação com classificações finais;
- risco de duplicar informações já presentes em outras variáveis.

## 9. Preparação futura

O pipeline de feature engineering deverá:

- validar a unidade pedido ou linha de pedido;
- aplicar o corte temporal anterior à aprovação;
- remover campos pós-evento da matriz de entrada;
- preservar identificadores apenas para rastreabilidade;
- interpretar datas com formato explícito;
- tratar moedas antes de comparar valores financeiros;
- ajustar codificações exclusivamente no treino;
- lidar com categorias não observadas;
- calcular estatísticas históricas sem utilizar validação ou teste;
- manter os dados originais imutáveis.

Possíveis conceitos futuros incluem desvio de orçamento, variação de preço, concentração por fornecedor e anomalia de prazo planejado. Suas fórmulas ainda não estão definidas e não são implementadas nesta etapa.

## 10. Contrato do pipeline futuro

**Entrada:** planilha transacional `Data`, após validação.  
**Unidade:** pedido de compra.  
**Instante de scoring:** antes da aprovação.  
**Features:** somente informações disponíveis até esse instante.  
**Saída planejada:** `purchase_risk_score`.  
**Artefatos futuros:** `ml/purchase_risk/models/`.

O pipeline deverá registrar a lista ordenada de features, a política temporal, as categorias aprendidas, os parâmetros e os metadados de cada execução.

## 11. Critérios de prontidão

O treinamento somente deverá começar depois que:

- a unidade de análise estiver confirmada;
- o instante de aprovação estiver representado ou metodologicamente definido;
- todas as variáveis pós-evento estiverem excluídas;
- moeda e datas tiverem tratamento documentado;
- classificações existentes tiverem origem auditada;
- a divisão entre treino, validação e teste estiver definida;
- testes confirmarem ausência de data leakage temporal.
