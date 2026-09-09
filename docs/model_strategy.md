# Estratégia dos Modelos Especializados

## 1. Objetivo

O projeto **Detector Inteligente de Anomalias em Compras** adota **3 domínios → 3 modelos especializados**. Cada componente usa sua própria fonte e mantém resultados independentes. As populações dos datasets são diferentes e não possuem chaves reais comuns para integração: não haverá merge direto de suas features. Uma eventual camada futura de integração de scores precisará de contexto verificável, avaliação própria e rastreabilidade, sem assumir que IDs semelhantes representam a mesma entidade.

A fase inicial criou a estrutura dos domínios externos. O Supplier Risk agora possui base consolidada, auditoria de target, split, pipeline ML-Ready e testes sintéticos persistidos. Purchase continua com auditoria/estratégia e implementação pendente. A consolidação atual não treinou modelos, não criou EDA e não alterou os artefatos ou a arquitetura Invoice/Purchase.

## 2. Arquitetura dos modelos

| Modelo | Unidade de análise | Fonte principal | Momento de scoring | Saída planejada | Estado |
| --- | --- | --- | --- | --- | --- |
| Invoice Anomaly Model | Fatura | Procurement Invoice Fraud Dataset | Após preparação da fatura | `invoice_anomaly_score` | Existente; não alterado nesta etapa |
| Supplier Risk Model | Fornecedor | Supplier Risk Assessment Dataset | Classificação do perfil representado no dataset, sem previsão temporal | Classe 0/1 e, quando compatível, probabilidade estimada da classe 1 | Base, targets, split e ML-Ready concluídos; EDA/treinamento/avaliação pendentes |
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

O Supplier Risk será tratado como **classificação supervisionada de `Risk_Level`** na unidade fornecedor, com características de perfil operacional, financeiro e de qualidade. `Risk_Level` será o target de treino e avaliação, nunca uma feature. A convenção adotada é `0 = menor risco`, `1 = maior risco`; modelos compatíveis poderão produzir a probabilidade estimada de pertencimento à classe 1.

A origem/regra de construção da label não foi comprovada: ela pode decorrer de avaliação humana, regra sintética ou outro processo desconhecido. A conclusão permitida será a **capacidade de reproduzir padrões associados à classificação de risco fornecida pelo dataset**, não capacidade comprovada de prever risco real. Não há previsão de acontecimentos futuros, fraude, rupturas ou probabilidade real de falha; o sistema não substitui avaliação humana.

Anomalia é perfil estatisticamente incomum, que pode ser excepcionalmente bom ou ruim. Risco é classificação segundo uma definição de risco. A hipótese histórica de definir Supplier Risk simplesmente como detector de anomalias foi substituída; o Invoice continua não supervisionado, sem alteração de sua arquitetura.

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

No Supplier, a preparação, o split e a imputação mediana train-only já estão implementados; treino e avaliação não. Seus testes usam exclusivamente DataFrames sintéticos e `tmp_path`, sem reprocessar dados reais. Não é necessário refatorar os scripts para expor funções: eles já possuem funções reutilizáveis e blocos `main` protegidos.

## 6. Controles contra data leakage

Os controles mínimos são:

- excluir labels, classificações finais e resultados derivados do target da matriz de features; permitir `Risk_Level` apenas como y supervisionado;
- definir explicitamente o instante em que cada score é calculado;
- excluir informações indisponíveis nesse instante;
- calcular agregações históricas somente com dados anteriores ao evento quando existir histórico comprovado; não atribuir temporalidade à consolidação atual de Supplier;
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

## 8. Critérios de prontidão e decisões históricas

A fase inicial definiu os seguintes critérios para receber pipelines; o Supplier já concluiu a preparação, enquanto Purchase mantém implementação futura:

- os três diretórios de cada domínio existirem;
- os limites entre os modelos estiverem documentados;
- a unidade de análise estiver definida;
- o instante de scoring estiver definido;
- as exclusões por identificação, label e temporalidade estiverem registradas;
- as features candidatas estiverem documentadas e sua implementação corresponder ao estado declarado de cada domínio;
- os diretórios de modelos estiverem protegidos contra versionamento de binários;
- nenhuma alteração tiver sido realizada nos datasets originais.

As ideias antigas “V2 = Invoice + Purchase” e “V3 = Invoice + Purchase + Supplier” foram substituídas. São hipóteses históricas, não arquitetura vigente nem junções diretas planejadas. O versionamento e as baselines serão separados por domínio; comparar scores futuramente não autoriza fundir features ou comparar métricas de populações diferentes.

## 9. Próxima fase do Supplier Risk

O fluxo futuro será: EDA somente em TRAIN → baseline ingênua majoritária e Logistic Regression → Random Forest / Gradient Boosting candidatos → avaliação em validation → escolha → avaliação final única em test. XGBoost somente se sua dependência externa for necessária e justificada; não foi adicionado ao ambiente nesta tarefa.

Accuracy isolada não é suficiente diante de aproximadamente 30% classe 0 e 70% classe 1. Estão planejadas confusion matrix, precision, recall, F1-score, ROC-AUC e PR-AUC quando aplicável, com comparação explícita contra predizer sempre a classe majoritária. Nenhuma métrica de modelo ou experimento foi executado nesta consolidação.

As dependências foram fixadas conforme o ambiente instalado, sem upgrades, e a suíte pytest foi persistida. A instalação limpa de pandas 2.2.2 em Python 3.14 por wheels não pôde ser resolvida; não há CI criada ou alegação de reprodução completa em um ambiente novo. Ver [README](../README.md) e [Supplier Risk Model](supplier_risk_model.md).
