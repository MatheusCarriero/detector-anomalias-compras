# Estratégia dos Modelos Especializados

## 1. Objetivo

O projeto **Detector Inteligente de Anomalias em Compras** adota **3 domínios → 3 modelos especializados**. Cada componente usa sua própria fonte e mantém resultados independentes. As populações dos datasets são diferentes e não possuem chaves reais comuns para integração: não haverá merge direto de suas features. Uma eventual camada futura de integração de scores precisará de contexto verificável, avaliação própria e rastreabilidade, sem assumir que IDs semelhantes representam a mesma entidade.

A fase inicial criou a estrutura dos domínios externos. O Supplier Risk concluiu preparação, experimentos e avaliação final acadêmica única com Logistic Regression cenário C, conforme [registro final](supplier_risk_final_evaluation.md); não há modelo de produção nem autorização para reutilizar TEST. Purchase continua com auditoria/estratégia e implementação pendente. Invoice permanece independente, com avaliação final pendente.

## 2. Arquitetura dos modelos

| Modelo | Unidade de análise | Fonte principal | Momento de scoring | Saída planejada | Estado |
| --- | --- | --- | --- | --- | --- |
| Invoice Anomaly Model | Fatura | Procurement Invoice Fraud Dataset | Lote retrospectivo preparado; uso online não validado | `invoice_anomaly_score` | Triagem/comparação VALIDATION concluídas; avaliador e validações com fixtures; avaliação final pendente |
| Supplier Risk Model | Fornecedor | Supplier Risk Assessment Dataset | Classificação do perfil representado no dataset, sem previsão temporal | Classe 0/1 e, quando compatível, probabilidade estimada da classe 1 | Avaliação final acadêmica LR/C concluída; sem uso operacional validado |
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

O objetivo vigente, formalizado em 27/09/2026, é **priorizar faturas de comportamento incomum para auditoria humana**. Não é classificação automática de fraude nem probabilidade de fraude. Isolation Forest permanece não supervisionado, com as mesmas 19 features, parâmetros e artefatos; mudou o enquadramento da avaliação, não o treinamento.

**IMPLEMENTADO:** Isolation Forest com `contamination=0.22` como configuração inicial; validação explícita das 19 features e `main` guard no treino. A [avaliação histórica](invoice_validation_results.md) consolidada e por `fraud_type` e a [auditoria](invoice_methodological_audit.md) foram preservadas. O [diagnóstico de triagem](invoice_triage_results.md), pré-definido por [protocolo](invoice_triage_protocol.md), mede Precision@K, captura e lift nos orçamentos 1%/5%/10%, usando `is_fraud` apenas como referência secundária não verificada. Não houve novo fit, tuning ou escolha de threshold.

**IMPLEMENTADO posteriormente (28/09/2026):** [comparação IF versus valor](invoice_value_comparison_results.md), com ganho líquido de positivos −40/+7/+192 em 1%/5%/10%, sem vantagem uniforme ou orçamento escolhido. O teste técnico com avaliadores artificiais foi encerrado e excluído da evidência acadêmica; não houve revisão humana válida.

**IMPLEMENTADO:** avaliador acadêmico, adaptador e validações de inputs, com dados/modelo explícitos e resultado JSON protegido contra sobrescrita. A verificação dos três JSONs históricos permanece uma ferramenta independente de rastreabilidade. Testes somente com fixtures sintéticas; responsabilidades descritas na [documentação técnica](invoice_final_executor.md). **PENDENTE:** avaliação final em tarefa futura explícita conforme o [protocolo acadêmico](invoice_academic_evaluation_protocol.md), sem uso de TEST para desenvolvimento, tuning ou seleção. Não executar a rota real como ensaio. Separadamente, validar utilidade humana, capacidade, custos e disponibilidade de informações antes de uso operacional. **LIMITAÇÕES:** estatísticas sobre todo TRAIN sem reconstrução ponto-a-ponto; avaliação anterior em fornecedores conhecidos e períodos parciais; referência ambígua e procedência histórica incompleta. `source_reconciled=false` permanece explícito; consistência de linhas não certifica o fit legado. Enriquecimento de INFLATED no top 1% e ganho condicionado ao orçamento não comprovam detecção geral de fraude. TEST continua fechado; nenhum threshold operacional é necessário para este benchmark retrospectivo.

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

No Supplier, preparação, split, imputação train-only, EDA, baselines e CV exploratória foram seguidos por congelamento LR/C e avaliação final acadêmica, sem refit TRAIN+VALIDATION. Os testes dos pipelines usam exclusivamente fixtures sintéticas e diretórios temporários, sem reprocessar dados reais. Os scripts de preparação já possuem funções reutilizáveis e blocos `main` protegidos.

Helpers e contrato final Supplier já existem; não se presume que isso tenha refatorado todos os produtores históricos. Notebooks futuros deverão consumir módulos testáveis com allowlist de splits, sem reescrever evidência histórica nem reabrir TEST. As alterações locais preexistentes dos notebooks 01/02 estão preservadas; a distinção entre bytes atuais e congelados consta na nota de rastreabilidade do relatório final.

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

**PROTOCOLO 1.0 de 2026-09-14 — sequência acadêmica concluída:** EDA em TRAIN → baseline majoritária → Logistic Regression/RandomForestClassifier → comparação em VALIDATION → congelamento LR/C → avaliação final única em TEST. As ablações e a CV exploratória precederam essa escolha. O [protocolo detalhado](supplier_risk_model.md) preserva as decisões anteriores aos resultados; o [relatório final](supplier_risk_final_evaluation.md) registra a execução. Não há nova rodada autorizada, XGBoost ou modelo de produção.

As ablações pré-definidas são A (10 features), B (sem `geopolitical_risk_index`), C (sem `supplier_record_count`) e D (sem ambas). As quatro já foram comparadas em VALIDATION; a CV posterior comparou A/D sem selecionar uma versão final. O conjunto mais completo não é presumido superior: índice provisório e contagem potencialmente associada à coleta exigem decisão de procedência, não escolha automática pelo maior valor pontual.

Métrica principal: **F1-macro**. Secundárias: precision/recall/F1 das classes 0 e 1, balanced accuracy, ROC-AUC, PR-AUC reportada como Average Precision e confusion matrix; accuracy é complementar. Utilidade mínima exige ganho claro sobre a classe majoritária de TRAIN em F1-macro e balanced accuracy, com identificação de ambas as classes. Os relatórios de [baselines](supplier_risk_baseline_models.md) e [validação científica](supplier_risk_validation_analysis.md) registram as etapas anteriores; a escolha final LR/C está documentada separadamente no relatório final, sem seleção por TEST.

Logistic Regression usa `SimpleImputer → StandardScaler → LogisticRegression` dentro de Pipeline, aprendido somente no TRAIN. Na CV interna concluída, cada fold aprendeu seus próprios transformadores a partir da base com nulos e dos IDs de TRAIN; o X_train já imputado sobre todo o TRAIN não foi usado. O ML-Ready atual continua válido para experimentos simples train/validation, sem alteração de artefatos. Qualquer CV futura deve preservar esse isolamento.

TRAIN explora/ajusta/treina; VALIDATION seleciona features, modelos, hiperparâmetros e threshold; TEST somente avalia ao final. Não usar TEST para EDA, tuning ou calibração. `predict_proba()` não garante probabilidades confiáveis: calibration curve, Brier score e possível CalibratedClassifierCV serão avaliados futuramente com dados de desenvolvimento. A saída significa somente pertencimento à classe 1, não falha real ou futura.

`.python-version` permanece em **3.14.3**, após restauração da exclusão local no fechamento anterior; a causa da exclusão não foi comprovada. As sondagens antigas com pandas 2.2.2 não resolveram wheels em Python 3.14.3/3.13.14. Em **2026-09-16**, foi comprovada uma instalação nova e isolada em Windows x64 / Python 3.14.3 com **pandas 2.3.3**; somente esse pin mudou. `pip check`, Ruff e os 113 testes sintéticos passaram. A `.venv` antiga foi preservada e não deve ser confundida com esse ambiente validado.

**IMPLEMENTADO:** correção controlada dos requisitos e CI configurada com instalação isolada e testes sintéticos. O estado remoto da CI não foi consultado nesta auditoria; outras plataformas permanecem sem comprovação. Isso não garante equivalência de modelos entre ambientes. A avaliação final Supplier foi concluída posteriormente, conforme seu registro próprio. O [README](../README.md#instalação) registra o procedimento e os limites da comprovação.

## 10. Evidência, publicação e caminho de produto

**IMPLEMENTADO:** o [contrato JSON de evidência Supplier](supplier_risk_experiment_records.md) registra e verifica novas predições TRAIN/VALIDATION por estimador/configuração/cenário. Ele não contém predições históricas reais, não aceita TEST nesta versão e não transforma checksum em prova de procedência.

**IMPLEMENTADO separadamente:** contrato e manifest da avaliação final Supplier, descritos na seção 9 dos registros experimentais. **PLANEJADO:** publicação transacional dos produtores de preparação ainda sequenciais; uma falha pode deixar arquivos antigos e novos misturados. Consumidores precisam conferir hashes/metadata, e a evolução deverá promover apenas conjuntos completos validados. Isso não exige repetir a avaliação final concluída.

O [roadmap](implementation_roadmap.md) preserva os gates Supplier concluídos e ordena fechamento Invoice, decisão formal Purchase e etapas posteriores de produto. Este documento referencia a configuração Supplier já congelada; não escolhe nova configuração, objetivo Purchase ou score combinado.
