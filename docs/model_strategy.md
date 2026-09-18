# Estratégia dos Modelos Especializados

## 1. Objetivo

O projeto **Detector Inteligente de Anomalias em Compras** adota **3 domínios → 3 modelos especializados**. Cada componente usa sua própria fonte e mantém resultados independentes. As populações dos datasets são diferentes e não possuem chaves reais comuns para integração: não haverá merge direto de suas features. Uma eventual camada futura de integração de scores precisará de contexto verificável, avaliação própria e rastreabilidade, sem assumir que IDs semelhantes representam a mesma entidade.

A fase inicial criou a estrutura dos domínios externos. O Supplier Risk agora possui base consolidada, auditoria de target, split, pipeline ML-Ready, testes sintéticos, EDA TRAIN, baselines em VALIDATION e CV exploratória A/D dentro de TRAIN. Purchase continua com auditoria/estratégia e implementação pendente. Esses ajustes Supplier são experimentais: não há modelo final, avaliação TEST ou mudança da arquitetura Invoice/Purchase.

## 2. Arquitetura dos modelos

| Modelo | Unidade de análise | Fonte principal | Momento de scoring | Saída planejada | Estado |
| --- | --- | --- | --- | --- | --- |
| Invoice Anomaly Model | Fatura | Procurement Invoice Fraud Dataset | Após preparação da fatura | `invoice_anomaly_score` | Existente; não alterado nesta etapa |
| Supplier Risk Model | Fornecedor | Supplier Risk Assessment Dataset | Classificação do perfil representado no dataset, sem previsão temporal | Classe 0/1 e, quando compatível, probabilidade estimada da classe 1 | Preparação, EDA e experimentos TRAIN/VALIDATION concluídos; seleção final e TEST pendentes |
| Purchase Risk Model | Linha de pedido na fonte; agregação por pedido não comprovada | Purchase Orders & Supplier Performance Dataset | Antes da aprovação | Significado pendente: anomalia ou desfecho específico; `purchase_risk_score` é nome histórico | Somente auditoria/documentação; features/modelo não criados |

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

O modelo existente continua responsável pela detecção de anomalias transacionais em faturas. Sua metodologia, suas 19 features, seus parâmetros e seus artefatos foram preservados nesta refatoração.

**IMPLEMENTADO:** Isolation Forest com `contamination=0.22` como configuração inicial; neste fechamento, o comando de treino recebeu validação explícita das 19 features e `main` guard, tornando a importação inerte. **PLANEJADO:** avaliação consolidada e por `fraud_type`, com escolha de threshold somente em validação. **LIMITAÇÕES:** as estatísticas usam todo o TRAIN, sem reconstrução ponto-a-ponto do histórico; o experimento atual avalia principalmente novas faturas de fornecedores já conhecidos. Não comprova generalização para fornecedores inéditos. A mudança de código foi apenas de segurança da fronteira de execução: metodologia, features, parâmetros, caminhos, metadata e modelo foram preservados, sem treino real, retraining ou uso de TEST.

### 4.2. Supplier Risk Model

O Supplier Risk será tratado como **classificação supervisionada de `Risk_Level`** na unidade fornecedor, com características de perfil operacional, financeiro e de qualidade. `Risk_Level` será o target de treino e avaliação, nunca uma feature. A convenção adotada é `0 = menor risco`, `1 = maior risco`; modelos compatíveis poderão produzir a probabilidade estimada de pertencimento à classe 1.

A origem/regra de construção da label não foi comprovada: ela pode decorrer de avaliação humana, regra sintética ou outro processo desconhecido. A conclusão permitida será a **capacidade de reproduzir padrões associados à classificação de risco fornecida pelo dataset**, não capacidade comprovada de prever risco real. Não há previsão de acontecimentos futuros, fraude, rupturas ou probabilidade real de falha; o sistema não substitui avaliação humana.

Anomalia é perfil estatisticamente incomum, que pode ser excepcionalmente bom ou ruim. Risco é classificação segundo uma definição de risco. A hipótese histórica de definir Supplier Risk simplesmente como detector de anomalias foi substituída; o Invoice continua não supervisionado, sem alteração de sua arquitetura.

### 4.3. Purchase Risk Model

O domínio mantém a fronteira **pré-aprovação**, mas precisa escolher entre detecção de anomalias e previsão de um desfecho específico. Anomalia não equivale automaticamente a risco. O dicionário confirma linhas de pedido (`PO_Number`), lead time efetivo pós-entrega, ESG simulado e moedas locais sem câmbio. A agregação em pedido completo requer chave real e regra justificadas; nenhum pipeline Purchase foi iniciado. O [contrato Purchase](purchase_risk_model.md) consolida essas evidências e pendências.

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

No Supplier, a preparação, o split e a imputação mediana train-only já estão implementados; EDA, baselines e CV exploratória também foram executadas. Isso não equivale a treino final ou avaliação TEST. Os testes dos pipelines usam exclusivamente DataFrames sintéticos e `tmp_path`, sem reprocessar dados reais. Os scripts de preparação já possuem funções reutilizáveis e blocos `main` protegidos.

Antes de qualquer novo experimento real, a lógica hoje concentrada nos notebooks deverá ser extraída para helpers experimentais testáveis, incluindo um carregador com allowlist explícita de splits. Os notebooks futuros deverão tornar-se consumidores finos desses módulos. **PLANEJADO:** essa refatoração; os notebooks históricos não foram alterados neste fechamento.

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

## 9. Estado e próxima fase do Supplier Risk

**PROTOCOLO 1.0 de 2026-09-14 — IMPLEMENTADO EM PARTE:** EDA em TRAIN → baseline 0 majoritária → baseline 1 Logistic Regression → RandomForestClassifier como primeiro candidato não linear → comparação em VALIDATION → congelamento → avaliação final única em TEST. EDA, comparação A/B/C/D e CV exploratória LR A/D dentro de TRAIN foram concluídas. Congelamento e TEST permanecem planejados. Gradient Boosting fica para fase posterior; XGBoost exige justificativa futura e não foi adicionado. O [protocolo detalhado do Supplier](supplier_risk_model.md#13-protocolo-experimental-pré-definido--implementado-em-parte) é a referência experimental, evitando regras divergentes entre documentos.

As ablações pré-definidas são A (10 features), B (sem `geopolitical_risk_index`), C (sem `supplier_record_count`) e D (sem ambas). As quatro já foram comparadas em VALIDATION; a CV posterior comparou A/D sem selecionar uma versão final. O conjunto mais completo não é presumido superior: índice provisório e contagem potencialmente associada à coleta exigem decisão de procedência, não escolha automática pelo maior valor pontual.

Métrica principal: **F1-macro**. Secundárias: precision/recall/F1 das classes 0 e 1, balanced accuracy, ROC-AUC, PR-AUC reportada como Average Precision e confusion matrix; accuracy é complementar. Utilidade mínima exige ganho claro sobre a classe majoritária de TRAIN em F1-macro e balanced accuracy, com identificação de ambas as classes. Os resultados observados e suas limitações estão nos relatórios de [baselines](supplier_risk_baseline_models.md) e [validação científica](supplier_risk_validation_analysis.md); não constituem escolha final.

Logistic Regression usa `SimpleImputer → StandardScaler → LogisticRegression` dentro de Pipeline, aprendido somente no TRAIN. Na CV interna concluída, cada fold aprendeu seus próprios transformadores a partir da base com nulos e dos IDs de TRAIN; o X_train já imputado sobre todo o TRAIN não foi usado. O ML-Ready atual continua válido para experimentos simples train/validation, sem alteração de artefatos. Qualquer CV futura deve preservar esse isolamento.

TRAIN explora/ajusta/treina; VALIDATION seleciona features, modelos, hiperparâmetros e threshold; TEST somente avalia ao final. Não usar TEST para EDA, tuning ou calibração. `predict_proba()` não garante probabilidades confiáveis: calibration curve, Brier score e possível CalibratedClassifierCV serão avaliados futuramente com dados de desenvolvimento. A saída significa somente pertencimento à classe 1, não falha real ou futura.

`.python-version` permanece em **3.14.3**, após restauração da exclusão local no fechamento anterior; a causa da exclusão não foi comprovada. As sondagens antigas com pandas 2.2.2 não resolveram wheels em Python 3.14.3/3.13.14. Em **2026-09-16**, foi comprovada uma instalação nova e isolada em Windows x64 / Python 3.14.3 com **pandas 2.3.3**; somente esse pin mudou. `pip check`, Ruff e os 113 testes sintéticos passaram. A `.venv` antiga foi preservada e não deve ser confundida com esse ambiente validado.

**IMPLEMENTADO:** correção controlada dos requisitos e CI configurada com instalação isolada e testes sintéticos. **PENDENTE:** primeira execução no GitHub e validação em outras plataformas. Isso não comprova equivalência de resultados de modelos entre ambientes; modelos, dados e metadados existentes não foram alterados. A EDA e os ajustes experimentais foram executados depois dessa validação de ambiente, mas treino final e TEST continuam pendentes. O [README](../README.md#instalação) registra o procedimento e os limites da comprovação.

## 10. Evidência, publicação e caminho de produto

**IMPLEMENTADO:** o [contrato JSON de evidência Supplier](supplier_risk_experiment_records.md) registra e verifica novas predições TRAIN/VALIDATION por estimador/configuração/cenário. Ele não contém predições históricas reais, não aceita TEST nesta versão e não transforma checksum em prova de procedência.

**PLANEJADO:** publicação transacional dos múltiplos artefatos de preparação e experimento. Hoje os produtores escrevem saídas sequencialmente e publicam metadata por último; uma falha pode deixar arquivos antigos e novos misturados. Consumidores precisam conferir hashes/metadata, e a evolução deverá promover atomicamente apenas conjuntos completos já validados.

O [roadmap](implementation_roadmap.md) define os gates para congelamento Supplier, avaliação TEST única sem refit TRAIN+VALIDATION, fechamento Invoice, decisão formal Purchase, contratos de inferência, backend/frontend, segurança, monitoramento e reprodutibilidade. Nenhum modelo, conjunto final de features, threshold, objetivo Purchase ou score combinado é escolhido nesta documentação.
