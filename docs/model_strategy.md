# Estratégia dos Modelos Especializados

## 1. Objetivo

O projeto **Detector Inteligente de Anomalias em Compras** adotará uma arquitetura de modelos especializados, na qual cada modelo representa um domínio de risco e produz um score independente. Essa separação reduz o acoplamento entre fontes heterogêneas, facilita a auditoria e permite avaliar cada componente antes de qualquer combinação de resultados.

Esta etapa prepara somente a estrutura dos futuros **Supplier Risk Model** e **Purchase Risk Model**. Nenhum modelo, pipeline de feature engineering ou artefato de treinamento é criado neste momento.

## 2. Arquitetura dos modelos

| Modelo | Unidade de análise | Fonte principal | Momento de scoring | Saída planejada | Estado |
| --- | --- | --- | --- | --- | --- |
| Invoice Anomaly Model | Fatura | Procurement Invoice Fraud Dataset | Após preparação da fatura | `invoice_anomaly_score` | Existente; não alterado nesta etapa |
| Supplier Risk Model | Fornecedor | Supplier Risk Assessment Dataset | Conforme snapshot de risco disponível | `supplier_risk_score` | Estrutura preparada; modelo não criado |
| Purchase Risk Model | Pedido de compra | Purchase Orders & Supplier Performance Dataset | Antes da aprovação | `purchase_risk_score` | Estrutura preparada; modelo não criado |

Os scores devem permanecer separados, versionados e auditáveis. Uma eventual composição em um score geral deverá ocorrer somente depois da validação individual dos modelos e deverá preservar a contribuição de cada componente.

## 3. Estrutura de diretórios

```text
ml/
├── supplier_risk/
│   ├── scripts/
│   ├── models/
│   └── notebooks/
└── purchase_risk/
    ├── scripts/
    ├── models/
    └── notebooks/
```

Responsabilidades planejadas:

- `scripts/`: validação, preparação de dados, feature engineering, treinamento e avaliação do domínio correspondente;
- `models/`: artefatos locais dos modelos treinados e metadados permitidos;
- `notebooks/`: exploração e experimentação acadêmica, sem substituir os pipelines reproduzíveis em scripts.

Arquivos binários de modelo nos formatos `.joblib` e `.pkl` permanecem fora do versionamento Git.

## 4. Separação de responsabilidades

### 4.1. Invoice Anomaly Model

O modelo existente continua responsável pela detecção de anomalias transacionais em faturas. Sua metodologia, suas 19 features e seus artefatos não fazem parte desta refatoração.

### 4.2. Supplier Risk Model

O modelo de fornecedores deverá representar risco estrutural e operacional na unidade de análise **fornecedor**. Ele deverá utilizar somente informações permitidas e disponíveis no snapshot de risco, sem receber classificações finais como `Risk_Level`.

### 4.3. Purchase Risk Model

O modelo de pedidos deverá analisar cada **pedido de compra** antes da aprovação. Consequentemente, informações produzidas após aprovação, entrega, faturamento ou pagamento não poderão participar do score prospectivo.

## 5. Contrato dos futuros pipelines

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

Nenhuma dessas etapas de implementação é realizada nesta fase. A estrutura criada apenas define os limites onde os pipelines serão desenvolvidos.

## 6. Controles contra data leakage

Os controles mínimos são:

- excluir labels, classificações finais e resultados derivados do target;
- definir explicitamente o instante em que cada score é calculado;
- excluir informações indisponíveis nesse instante;
- calcular agregações históricas somente com dados anteriores ao evento;
- ajustar transformações exclusivamente no conjunto de treino;
- reservar validação para decisões de modelagem e teste para avaliação final;
- documentar a origem e a fórmula de scores externos antes de utilizá-los.

## 7. Versionamento e auditabilidade

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

## 8. Critérios de prontidão para feature engineering

A estrutura estará pronta para receber os pipelines quando:

- os três diretórios de cada domínio existirem;
- os limites entre os modelos estiverem documentados;
- a unidade de análise estiver definida;
- o instante de scoring estiver definido;
- as exclusões por identificação, label e temporalidade estiverem registradas;
- as features candidatas estiverem documentadas, sem implementação antecipada;
- os diretórios de modelos estiverem protegidos contra versionamento de binários;
- nenhuma alteração tiver sido realizada nos datasets originais.

## 9. Estado desta fase

Ao final desta refatoração, os módulos estão estruturalmente preparados, mas ainda vazios. A próxima fase poderá implementar primeiro os pipelines de validação e feature engineering, mantendo treinamento e avaliação como etapas posteriores e explicitamente controladas.
