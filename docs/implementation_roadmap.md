# Roadmap de implementação

## Estado vigente — infraestrutura e estudos acadêmicos

Invoice e Supplier concluíram suas avaliações finais acadêmicas. Purchase mantém
a decisão C: sem modelagem até esclarecer a fronteira pré-aprovação e as demais
pendências metodológicas. Nenhum desses estudos representa um serviço de
inferência integrado ao backend ou uso empresarial validado.

A infraestrutura atual utiliza NestJS 12, TypeScript/ESM e Node 24, com Prisma
7.10.0 e PostgreSQL 18. O primeiro incremento possui 11 tabelas de domínio no
schema `app`, funções SQL transacionais, versões, snapshots e auditoria. A CI
offline está implementada; os contratos e procedimentos estão nos guias do
[backend](../backend/README.md) e do [banco](../prisma/README.md).

As etapas de identidade e inspeção de permissões/catálogos pelo backend foram
concluídas no banco sintético, conforme o fechamento informado pelo responsável
no commit `552d09b`. Isso não atesta o estado atual de qualquer servidor nem
substitui testes de comportamento das funções SQL e concorrência pelo harness
NestJS, que permanecem etapas separadas. Os testes de integração do primeiro
incremento do banco têm registro próprio; não confundir as duas frentes.

Permanecem pendentes os contratos de inferência, funcionalidades de negócio,
frontend e validação de uso operacional. Conexões e escritas de teste exigem
escopo e autorização próprios; não são consequência automática da CI.

## Fechamento acadêmico Invoice — 18/10/2026

Invoice mantém 19 features, modelo e resultados históricos de VALIDATION.
O fluxo é dados → preparação → EDA → features → treinamento → validação →
avaliação final → resultados. O avaliador recebe dados/modelo explicitamente,
valida inputs e grava um JSON novo sem sobrescrever resultados. A verificação
histórica é independente da avaliação normal. Consulte o
[protocolo acadêmico](invoice_academic_evaluation_protocol.md) e a
[documentação técnica](invoice_academic_evaluation_protocol.md#71-responsabilidades-dos-módulos).

A avaliação final em TEST foi concluída em execução única, com 60.000 faturas
e as mesmas 19 features, sem fit, tuning ou alteração do modelo. O resultado
oficial está em [invoice_test_final_v1.json](../ml/experiments/invoice_test_final_v1.json),
separado dos resultados históricos de VALIDATION. Não repetir a avaliação nem
usar TEST para exploração, desenvolvimento, tuning ou seleção.
`source_reconciled=false` e as limitações de procedência do fit legado,
labels, temporalidade e utilidade humana permanecem; a comparação retrospectiva
não comprova eficácia empresarial.

Na simplificação acadêmica de 13/10/2026, a avaliação final ainda estava pendente,
TEST/raw permaneceram fechados e nenhum resultado científico foi recalculado
pela refatoração. Esse era o estado anterior à execução final.

Supplier concluiu sua avaliação final acadêmica; não repetir. A auditoria Purchase
concluiu pela decisão C: não implementar o modelo ainda, por insuficiência
metodológica para demonstrar uso pré-aprovação. Purchase permanece na fase 7,
sem iniciar feature engineering ou treinamento. Backend/frontend seguem fora desta etapa.
As atualizações datadas e planos abaixo são históricos; não são tarefas a
repetir nem exigem reconstruir a antiga infraestrutura de execução Invoice.
As decisões independentes de Supplier/Purchase continuam válidas.

## Atualização de execução — 28/09/2026

A [comparação IF versus valor](invoice_validation_results.md#3-comparação-if--valor--28092026) está
**concluída em VALIDATION**: ganho líquido de positivos −40/+7/+192 nos orçamentos
fixos 1%/5%/10%. Não há vencedor uniforme, orçamento escolhido ou utilidade
empresarial comprovada. Não repetir essa comparação como pendência.

O teste técnico da revisão cega foi encerrado pelo responsável. Avaliadores
artificiais não são pessoas nem evidência; respostas simuladas, concordância e
julgamentos ficam excluídos de resultados, JSONs e decisões acadêmicas. ZIPs
simulados devem permanecer fora do repositório. A [preparação original](invoice_academic_evaluation_protocol.md#9-preparação-da-revisão-cega--histórico-de-coordenação)
foi preservada; não houve revisão humana válida e uma eventual etapa real segue
separada, sem ser substituída pela simulação.

**Nota histórica:** a etapa seguinte então previa uma estrutura técnica de
execução, com avaliação final então pendente. A arquitetura e o estado atual
da avaliação estão descritos acima. Custos, capacidade e avaliação humana reais continuam
necessários para alegar utilidade operacional.

As atualizações datadas abaixo preservam o histórico, não redefinem o próximo
passo vigente. Supplier/Purchase e suas decisões permanecem fora desta etapa.

## Atualização de execução — 27/09/2026

Invoice foi formalizado como **triagem de anomalias para auditoria humana**,
não classificação automática de fraude. A avaliação anterior e a
[auditoria metodológica](invoice_methodological_audit.md) estão concluídas e
preservadas; as pendências de auditoria abaixo são registros históricos.

O [protocolo de triagem](invoice_triage_protocol.md) e seus
[resultados](invoice_validation_results.md#2-triagem-e-diagnóstico-temporal--27092026) registram diagnóstico top-1%/5%/10%
somente em VALIDATION, com o modelo e as 19 features existentes, zero fit/tuning
ou ajuste de threshold. Precision@K da referência: 85,00%/43,00%/32,67%;
sinal concentrado em INFLATED, sem comprovação de utilidade humana.
Distribuições TRAIN/VALIDATION e períodos parciais foram descritos, não usados
para alterar features ou atribuir causalidade.

**Próximo gate Invoice:** definir utilidade/capacidade de auditoria e comparação
prévia com uma regra simples de priorização por valor. Revisão humana depende
de evidência de negócio disponível; não se presume que a label seja verdade
empresarial. Não escolher orçamento de produção com estes resultados.
TEST permanece fechado. Esta atualização não modifica Supplier, Purchase ou
a arquitetura e não libera produção.

## Atualização de execução — 24/09/2026

As seções seguintes conservam o planejamento e os gates originais; estados
históricos de Supplier ainda planejado não representam o estado atual.

- Supplier: avaliação final acadêmica e encerramento documental concluídos,
  conforme [relatório final](supplier_risk_final_evaluation.md). Não repetir
  EDA, treino, seleção, validação ou TEST. Não há modelo de produção nem
  comprovação de risco empresarial; procedência/validade externa seguem limitadas.
- Fases 1/2: helpers e publicação de evidência final implementados no escopo
  Supplier; isso não implica refatoração de todos os produtores históricos.
- Próxima prioridade: **fase 6, Invoice**, pois já há modelo e features.
  Escopo mínimo: inferência somente em VALIDATION com artefato e offset originais,
  métricas consolidadas/por fraude, sem treino, tuning ou TEST. Ver
  [protocolo](invoice_validation.md) e [estado/resultados](invoice_validation_results.md).
- Fase 7, Purchase: somente auditoria e documentação; pastas de código ainda
  vazias. Objetivo, target/horizonte quando aplicáveis, disponibilidade anterior
  à aprovação e política monetária impedem iniciar modelagem responsável.
- Backend/frontend permanecem placeholders, sem código funcional. Não entram
  no incremento Invoice nem justificam fabricar um score combinado.

Esta atualização não libera automaticamente TEST Invoice. O menor próximo gate
de avaliação da baseline existente em VALIDATION foi executado: AP 0,31607,
ROC-AUC 0,57976 e 8.935 falsos positivos, sem fit/tuning. O próximo incremento
é auditar is_fraud versus fraud_type e a procedência do artefato, somente em
TRAIN/VALIDATION, sem corrigir labels por suposição. Uma avaliação final exigirá
decisão explícita e prévia sobre configuração, regra e uso pretendido. A fase 6
como um todo ainda não está concluída.

## 1. Escopo e regras permanentes

Este roadmap ordena o trabalho restante por dependência e risco. Ele não seleciona um modelo Supplier, uma lista final de features, um threshold, um score combinado nem o objetivo de negócio Purchase.

Regras que atravessam todas as fases:

- os três domínios permanecem independentes e com saídas auditáveis;
- Procurement KPI é auxiliar e não treina Invoice, Supplier ou Purchase;
- TRAIN serve para exploração, ajuste e treino; VALIDATION para comparação/seleção; TEST somente para avaliação final explicitamente solicitada, após definição prévia da metodologia; as decisões Supplier concluídas permanecem preservadas;
- o protocolo Supplier atual não permite refit em `TRAIN + VALIDATION`;
- métricas Supplier medem reprodução de `Risk_Level`, não risco empresarial real;
- datasets de origem permanecem imutáveis;
- decisões de negócio, custos de erro e escopo da avaliação final precisam ser registrados, não inferidos de métricas.

## 2. Estado de partida histórico — anterior à avaliação final Supplier

### IMPLEMENTADO

- Invoice: pipeline de 19 features e Isolation Forest existente; comando de treino com fronteira segura de importação, sem mudança de metodologia.
- Supplier: base por fornecedor, auditoria do target, split determinístico, ML-Ready com imputação train-only, EDA restrita a TRAIN, baselines A/B/C/D em TRAIN/VALIDATION e validação científica exploratória com CV A/D dentro de TRAIN.
- Supplier: contrato JSON de evidência para experimentos futuros, sem registros reais retroativos.
- Purchase: auditoria/documentação da fonte, unidade disponível como linha de pedido e fronteira pré-aprovação.
- Qualidade: suíte sintética e Ruff existentes; 113 testes é a linha de base histórica anterior a este fechamento, não uma contagem futura a ser codificada.

### LIMITAÇÕES

- nenhuma configuração Supplier foi congelada como final; não há threshold, calibrador, modelo serializado ou avaliação TEST;
- predições individuais históricas não foram persistidas e não podem ser reconstruídas com certeza a partir dos agregados;
- `Risk_Level` e `geopolitical_risk_index` têm procedência incompleta; `supplier_record_count`, compliance acima de 100 e lead time zero conservam dúvidas de semântica/domínio;
- não há validação externa ou temporal de Supplier;
- scripts de preparação publicam arquivos sequencialmente; uma falha pode deixar saídas antigas e novas misturadas até conferência de metadata/hashes;
- lógica experimental ainda vive em notebooks e não constitui uma biblioteca testável reutilizável;
- backend, frontend, banco operacional, contratos de inferência e monitoramento ainda não existem.

## 3. Fase 1 — biblioteca experimental antes de novo experimento

**Impacto:** máximo; reduz risco de repetir lógica divergente e de acessar splits indevidos.

**Responsáveis:** engenharia de ML e revisão metodológica.

**PLANEJADO:**

1. extrair helpers de cenários, métricas, alinhamento e validações dos notebooks;
2. criar carregador com allowlist explícita por finalidade, mantendo TEST recusado no fluxo de desenvolvimento;
3. cobrir os módulos com testes sintéticos de schema, IDs, leakage e determinismo;
4. transformar notebooks futuros em consumidores finos da biblioteca;
5. preservar notebooks históricos como evidência, sem reescrevê-los retroativamente.

**Gate de saída:** API revisada; testes negativos demonstram recusa de split não autorizado; transformações são ajustadas apenas no subtreino de cada fold; notebook fino reproduz um caso sintético; nenhum dado real ou TEST é necessário para a suíte.

Nenhum novo experimento real deve anteceder este gate.

## 4. Fase 2 — publicação transacional e evidência reproduzível

**Impacto:** alto; evita aceitar conjuntos parciais ou mistos como uma execução válida.

**Responsáveis:** engenharia de dados/ML e mantenedor de artefatos.

**PLANEJADO:**

- adotar diretório temporário exclusivo por execução;
- validar todos os arquivos, schemas, hashes e manifest antes da promoção;
- promover o conjunto completo de forma atômica para destino versionado;
- impedir sobrescrita silenciosa e registrar falha/limpeza segura;
- integrar os registros JSON Supplier futuros ao manifest da execução;
- definir retenção, permissões e, se necessário, assinatura/autenticidade separada do checksum.

**Gate de saída:** teste de falha injetada prova que consumidores veem o conjunto anterior completo ou o novo completo, nunca uma mistura; manifest referencia todos os artefatos; verificação independente revalida hashes e IDs.

## 5. Fase 3 — procedência e validade do problema Supplier

**Impacto:** máximo; limita o significado científico de qualquer métrica.

**Responsáveis:** responsável pelos dados, especialista de domínio e governança.

**PLANEJADO:** obter evidência verificável sobre origem/regra de `Risk_Level`, construção e referência temporal do índice geopolítico, semântica de `supplier_record_count`, escala de compliance e significado de lead time zero. Definir também custos e consequências dos erros caso exista uso decisório.

**Gate de saída:** ficha de procedência versionada, decisão explícita de uso/exclusão de cada variável questionada, definição do uso pretendido e limites de comunicação aprovados. Se a evidência não existir, registrar a limitação como bloqueante ou restringir o produto a demonstração acadêmica.

Validação externa/temporal requer outra fonte ou período adequado. Sem isso, nenhum resultado deverá ser apresentado como generalização fora do dataset atual.

## 6. Fase 4 — congelamento do candidato Supplier

**Estado atual: concluído.** LR cenário C foi congelada antes de TEST; itens
abaixo preservam o planejamento original, não constituem seleção pendente.

**Impacto:** alto; é a última fase de seleção antes de TEST.

**Responsáveis:** ciência de dados, revisão metodológica e proprietário do uso de negócio.

**PLANEJADO:**

- registrar antecipadamente o orçamento de qualquer análise adicional em TRAIN/VALIDATION;
- decidir explicitamente cenário, família, transformações, hiperparâmetros, seed(s), métricas, regra de threshold e eventual calibração;
- justificar a decisão considerando procedência e não somente o maior valor pontual;
- limitar reutilização de VALIDATION e documentar todas as consultas;
- gerar registros de evidência verificáveis para novas execuções.

**Gate de saída:** documento de congelamento assinado/revisado com lista ordenada de features, código e inputs identificados por hash, parâmetros, threshold, política de calibração, baseline, métricas e plano de falha. Esse gate pode concluir que nenhum candidato é defensável. A documentação atual não escolhe A, D ou qualquer vencedor.

## 7. Fase 5 — avaliação final única do Supplier

**Estado atual: concluído**, conforme [relatório final](supplier_risk_final_evaluation.md).
O planejamento abaixo não autoriza nova execução nem refit.

**Impacto:** alto e irreversível do ponto de vista metodológico.

**Responsáveis:** executor autorizado e revisor independente.

**PLANEJADO:** somente após o gate anterior, ajustar a configuração congelada em TRAIN, sem incorporar VALIDATION, e avaliar uma vez em TEST. Não haverá EDA, tuning, calibração, troca de feature, mudança de threshold ou refit em `TRAIN + VALIDATION`.

**Gate de saída:** relatório completo da execução única, incluindo desvios do protocolo, métricas predefinidas, incerteza aplicável, limitações, hashes e decisão de aceitar ou rejeitar o candidato para o uso declarado. Resultado insatisfatório é reportado como tal; TEST não realimenta uma nova seleção.

Mesmo um resultado favorável não supre validação externa/temporal nem prova risco empresarial real.

## 8. Fase 6 — fechamento metodológico do Invoice

**Impacto:** alto; o modelo existe, mas sua avaliação operacional não está fechada.

**Responsáveis:** ciência de dados Invoice e revisão de risco.

**CONCLUÍDO:** avaliação consolidada/por `fraud_type`, auditoria metodológica, diagnóstico de triagem e comparação IF versus valor em VALIDATION nos orçamentos 1%/5%/10%, preservando 19 features e a configuração (`IsolationForest`, 200 árvores, `contamination=0.22`, `random_state=42`, `n_jobs=-1`). Sem retreino, tuning ou seleção de threshold. O objetivo vigente é priorização de faturas incomuns para auditoria humana. Teste técnico da revisão cega encerrado e excluído da evidência acadêmica; nenhuma revisão humana válida realizada.

**IMPLEMENTADO — técnico:** avaliador acadêmico e validações de inputs/modelo
com fixtures sintéticas; JSON normal com proteção contra sobrescrita e
verificação histórica independente. **CONCLUÍDO — avaliação final acadêmica:**
execução única em TEST conforme o [protocolo](invoice_academic_evaluation_protocol.md),
registrada em [invoice_test_final_v1.json](../ml/experiments/invoice_test_final_v1.json).
As duas estratégias foram comparadas nos orçamentos previstos, sem retreino,
tuning ou ajuste condicionado a TEST. O registro mantém partição, configuração,
features, métricas, resultados, limitações, timestamp e `source_reconciled=false`.

**Utilidade operacional separada:** exige evidência humana real, contexto
disponível, capacidade/custos e eventual regra operacional pré-definida.
Se um threshold vier a ser necessário, selecioná-lo em validação sob protocolo
próprio. Não inventar um threshold para o ranking retrospectivo.
Score não é probabilidade de fraude; benchmark favorável não libera produção.

## 9. Fase 7 — decisão formal do Purchase

**Impacto:** bloqueante para qualquer modelagem Purchase.

**Responsáveis:** proprietário do processo de compras, especialista de domínio, dados e ML.

**Estado vigente:** decisão C, não implementar o modelo ainda. A auditoria confirmou 5.200 linhas de pedido e 57 colunas, mas não encontrou timestamp explícito de aprovação nem histórico de alterações/snapshots dos campos. Não há target ou conjunto de features pré-aprovação aprovado. Detecção de anomalias e supervisão continuam possibilidades, não decisões adotadas.

**Próximo passo:** esclarecer a relação entre `PO Date` e aprovação, a existência de timestamp/snapshot pré-aprovação e a disponibilidade temporal das variáveis; validar semântica dos status e contratos e procedência das classificações. Se a supervisão vier a ser escolhida, definir população, horizonte de observação e target. Manter a política para as cinco moedas sem conversão pendente. As evidências, candidatos e limitações estão no [contrato Purchase](purchase_risk_model.md); agregação por pedido completo não será inventada.

**Gate de saída:** contrato de problema aprovado com unidade, objetivo, população, instante de scoring, variáveis permitidas/proibidas, split, métricas, custo dos erros e semântica da saída. Sem esse gate não há autorização para feature engineering ou treino.

## 10. Fase 8 — contratos de inferência e registro de modelos

**Impacto:** alto; separa experimentação de consumo seguro.

**Responsáveis:** ML engineering, backend e governança.

**PLANEJADO:** para cada domínio aprovado, definir schema de entrada/saída, tratamento de ausentes/categorias, ordem de features, versão de transformadores/modelo, semântica e faixa do score, códigos de erro, latência, idempotência e rastreabilidade. Persistir o pipeline ajustado, não reajustar transformadores em produção.

**Gate de saída:** testes de contrato e compatibilidade passam com fixtures sintéticas; uma versão identifica de forma imutável código, dados, transformadores, modelo e documentação; rollback foi ensaiado; score mantém a semântica específica do domínio.

## 11. Fase 9 — backend, frontend e integração

**Impacto:** depende dos contratos anteriores.

**Responsáveis:** backend, frontend, produto e segurança.

**PLANEJADO:** expor endpoints versionados, autenticação/autorização, trilha de auditoria, validação de entrada e telas que mostrem separadamente os sinais Invoice, Supplier e Purchase. Exibir limitações e contexto humano de decisão.

Uma camada combinada só poderá ser estudada se houver contexto comum verificável entre as entidades, objetivo e pesos definidos por responsáveis de negócio e avaliação própria. IDs parecidos entre fontes não provam identidade. Este roadmap não define score combinado.

**Gate de saída:** testes de contrato e integração ponta a ponta, ameaças revisadas, explicações/limites visíveis, contribuição de cada sinal preservada e nenhuma junção artificial entre populações.

## 12. Fase 10 — segurança, monitoramento e reprodutibilidade operacional

**Impacto:** obrigatório antes de produção.

**Responsáveis:** segurança, plataforma, governança de dados, ML e operação.

**PLANEJADO:**

- controle de acesso mínimo, gestão de segredos, logs sem dados sensíveis e política de retenção;
- validação de supply chain, dependências e artefatos; assinatura quando a ameaça justificar;
- monitoramento de schema, qualidade, drift, distribuição de scores, latência, falhas e grupos relevantes;
- processo de incidentes, rollback, suspensão do modelo e revisão humana;
- ambientes reproduzíveis e CI remota comprovada, com contagens de testes obtidas da execução corrente;
- validação externa/temporal e reavaliações periódicas quando houver dados adequados.

**Gate de saída:** critérios de alerta e responsáveis definidos, runbooks ensaiados, reprodução independente documentada, auditoria de acesso aprovada e política de revalidação aceita. Sem validação externa/temporal, a limitação permanece explícita mesmo que o sistema técnico esteja operacional.

## 13. Ordem crítica e condição de produto

```text
biblioteca experimental testável
  → publicação transacional/evidência
  → procedência e uso declarado
  → congelamento Supplier
  → TEST único autorizado
  → contrato de inferência
  → aplicação e operação segura
```

Invoice e a decisão Purchase podem avançar em paralelo depois de seus próprios gates, mas nenhum deles autoriza uma composição de scores. O produto somente poderá ser chamado de pronto para produção quando os contratos de problema, avaliação, inferência, segurança, monitoramento e responsabilidade humana estiverem aprovados para o uso declarado.


## Registros técnicos consolidados

Esta seção conserva as decisões e verificações úteis dos planos de engenharia
encerrados. As contagens são históricas, não resultados da suíte atual. Os
checklists de implementação e instruções para agentes foram retirados; protocolos,
resultados científicos e contratos executáveis continuam em seus arquivos próprios.
O histórico integral dos planos está no commit `552d09b`, anterior à limpeza.

### Engenharia e avaliação Invoice — setembro de 2026

- **17–18/09:** foi escolhido um fechamento pequeno de engenharia, em vez de
  somente documentação ou implementação prematura de novos modelos/aplicação.
  A importação do treino Invoice tornou-se inerte, com validação das 19 features;
  o Supplier recebeu registro/verificação de evidências experimentais. Não houve
  reconstrução de predições históricas ausentes. O contrato atual está em
  [registros Supplier](supplier_risk_experiment_records.md) e a cobertura em
  `tests/invoice/test_train_model.py` e `tests/supplier_risk/test_experiment_artifact.py`.
  O diagnóstico inicial registrava 113 testes; no encerramento, o responsável
  informou 196 testes e Ruff aprovados. Esses comandos não foram repetidos na
  integração. Foram integrados 12 arquivos, preservados 72 hashes e conferidos
  atributos de três arquivos TEST sem abrir seu conteúdo. A comparação com o
  worktree aprovado desconsiderou apenas CRLF/LF; os notebooks ficaram fora.
- **24/09, HEAD b624204:** Invoice foi priorizado por já ter um artefato; Purchase
  dependia de problema, target quando aplicável e moedas. O offset original foi
  mantido, sem seleção pelos resultados. O plano registrou 17 casos RED com
  avaliador ausente, depois 38 testes Invoice aprovados em 8,30 s, Ruff e pip check
  aprovados, em ambiente temporário com os mesmos pins. A execução real em
  30.000 registros VALIDATION teve zero fits e preservou 51 hashes. AP 0,31607,
  contra referência 0,22577, e os demais resultados permanecem no
  [relatório original](invoice_validation_results.md). O protocolo foi mantido
  imutável; observações e hash da saída foram registrados separadamente.
- **29/09, HEAD b624204:** o executor então era exclusivamente sintético. A matriz
  usava seleção global top-K, não classificação pelo threshold legado. A revisão
  retirou uma restrição indevida de montantes positivos, mantendo valores assinados,
  e corrigiu o bypass por cópia do freeze com vínculo ao destino. Houve 69 testes
  direcionados aprovados e um skip antes do último ajuste; a regressão final
  registrou **392 aprovados, 1 skip, 41,79 s**, Ruff aprovado e
  `REAL_PROJECT_DATA_ACCESS_ATTEMPTS=0`. O skip dependia de symlink no Windows;
  disputa simultânea entre processos não foi exercitada naquele fechamento.
  O snapshot inicial tinha 91 hashes e 42 registros de tamanho/data, mas os
  valores dos hashes não sobreviveram à retomada. A conferência posterior usou
  metadados e o marcador `2026-09-29T04:11:14.561165Z`, sem alegar equivalência
  criptográfica completa. Fixtures joblib confiáveis e filesystem cooperativo
  eram limites explícitos; não houve execução científica nessa entrega.

### Executor Invoice anterior à simplificação — outubro de 2026

A arquitetura abaixo foi substituída em **13/10/2026**. Seus freezes, recibos e
contratos de autorização não devem ser reconstruídos nem usados para executar o
fluxo atual. A referência vigente é o [protocolo acadêmico](invoice_academic_evaluation_protocol.md)
e o [guia técnico](invoice_academic_evaluation_protocol.md#71-responsabilidades-dos-módulos). TEST foi avaliado posteriormente,
em 18/10/2026; os registros abaixo são verificações técnicas anteriores.

| Registro | Verificação histórica | Resultado |
|---|---|---|
| 05/10 | Invoice | 591 aprovados, 8 skips, 135,22 s |
| 05/10 | Regressão completa | 816 aprovados, 8 skips, 137,32 s |
| 06/10 | Seleção direcionada | 244 aprovados, 1 skip, 88,93 s |
| 06/10 | Invoice | 595 aprovados, 8 skips, 140,13 s |
| 06/10 | Regressão completa | 820 aprovados, 8 skips, 139,63 s |
| 06/10, auditoria de formalização | Invoice | 595 aprovados, 8 skips, 146,80 s |

Essas execuções registraram zero tentativas de acesso aos dados reais pelas
instrumentações, Ruff aprovado nos nove arquivos envolvidos e verificações de
whitespace aprovadas. Instrumentação não equivale a sandbox do sistema
operacional. Os oito skips eram cinco casos de symlink do adaptador, um do
executor sintético, um da evidência histórica e um da fronteira legada; não
foram contabilizados como passes. Não houve atualização de dependências entre
as revisões de outubro. O runtime registrado era Python 3.14.3, pandas 2.3.3,
NumPy 2.5.2, PyArrow 25.0.1, scikit-learn 1.9.0, joblib 1.6.0, pytest 9.1.1 e
Ruff 0.16.5, em ambiente descartável separado, com os pins existentes.

As revisões corrigiram mutação de inputs durante publicação, hashes em maiúsculas,
dependência da ordem de chaves, overflow JSON/redirecionamento de caminhos,
recibos incompletos e aceitação indevida de bundles ainda não publicados. Cinco
casos da revisão de 06/10 foram reproduzidos antes da correção. As verificações
semânticas históricas passaram a atualizar referências descendentes para atingir
a rejeição pretendida, e não apenas um digest antigo. A validação de métricas do
bundle cobria invariantes limitadas; não certificava autenticidade ou correção
semântica exaustiva. Escritas hostis no filesystem continuavam fora do escopo.

Os três JSONs de VALIDATION foram conferidos em bytes e referências internas,
sem reabrir datasets/modelos para recalcular hashes ou métricas. O fechamento
conservou `source_reconciled=false`: integridade não comprova treinamento legado.
O registro de 05/10 preservou estes hashes dos notebooks locais, sem afirmar que
correspondem aos bytes congelados da avaliação Supplier:

- notebook 01: `f750a05c83637f09faa9c9fce357c8f0448bc98f47f1d3e0bfc150e6f2f83e3f`;
- notebook 02: `8c31090637683cc0391075e5211b78ee3772cbf98a6b8a0ba479c0b1283dcc46`.

A formalização foi bloqueada apesar de **29 hashes permitidos coincidentes**:
o contrato 1.2 exigia caminhos absolutos e destino vinculado, incompatíveis com
um freeze portátil. Não houve emissão forçada ou autorização humana. O inventário
então era um rascunho (`invoice-freeze-preparation/1.0`), candidato
`invoice-prefreeze-4dbb67f7-1206-43a2-82b4-0cbb4fb946de`, SHA-256
`036021fd68d98e9c93ceb0a6fcf31910dc14ae436b48067c103007f6e0ae7563`.
A literal `max_features=1.0` foi corrigida na serialização do rascunho, não no
modelo. Os 22 pins coincidiam com o ambiente QA, mas o gate conferia somente
seis versões de runtime. A alternativa proposta era separar freeze portátil e
contexto vinculado; essa infraestrutura foi posteriormente removida. Esses
identificadores antigos não representam artefatos vigentes ou permissão de acesso.

### Banco e CI offline — outubro de 2026

- **20/10, HEAD f220740:** o primeiro incremento foi limitado às 11 tabelas,
  histórico seletivo e snapshots contemporâneos, sem dados acadêmicos ou tabelas
  ML. Identidades externas e observações foram separadas; versões usam FKs
  tipadas e projeção/head transacionais. A decisão foi complementar Prisma com
  SQL customizado, sem substituir FKs, triggers, locks ou imutabilidade pelo ORM.
  Os tipos monetários, assinaturas, privilégios e procedimentos necessários
  estão no [guia do banco](../prisma/README.md) e na migration preservada.
  Naquele ponto havia PostgreSQL 18.6 instalado, Node 24.13.1 e npm 11.14.0,
  mas detectar serviço/porta não identificava banco ou papéis autorizados.
  A primeira entrega aprovou testes estáticos, validate/generate e dependências;
  não aplicou migration nem executou testes SQL. A revisão independente foi
  parcial por limite de uso. Bootstrap/search_path e lacunas de rollback,
  permissões/concorrência foram corrigidos; a validação conectada ocorreu depois,
  conforme o estado atual do guia. Não tratar os checkboxes antigos como pendências.
- **23/10, HEAD a92e5ab:** a CI backend foi separada da CI Python. Windows foi
  escolhido por corresponder ao ambiente validado e permitir exercitar junctions;
  não se alegou suporte a uma matriz de sistemas ainda não testada. As ações e
  Node/npm foram fixados, os dois lockfiles instalados com hooks desabilitados
  e dependências nativas opcionais mantidas. O build precede os testes do client.
  “Offline” significa sem banco/dados de negócio, não sem downloads de ferramentas.
  A reprodução limpa copiou 34 arquivos permitidos para um temporário: ambos
  `npm ci` e `npm ls --all` passaram; os 34 arquivos permaneceram iguais.
  Foram **5 testes de contrato, 33 unitários, 1 E2E e 12 Prisma aprovados**
  (51 no total, zero falhas/skips), além de schema, build, lint e TypeScript.
  Actionlint 1.7.12 e a análise dos blocos PowerShell passaram. Dos 35 arquivos
  monitorados no checkout, somente a seção CI do guia backend mudou.
  Não se reproduziram localmente checkout/setup/cache hospedados, instalação
  global npm ou a guarda Git de checkout limpo. A revisão não encontrou bloqueador;
  esses resultados locais não comprovavam uma execução no GitHub Actions.

Os históricos completos que originaram esta consolidação podem ser consultados
na [árvore do commit 552d09b](https://github.com/MatheusCarriero/detector-anomalias-compras/tree/552d09b63b47604b5a8abd98d05ec2a5f3130911/docs/superpowers): planos de
17/09, 24/09, 29/09, 02/10, 20/10 e 23/10, e desenho de 17/09. Nenhum protocolo,
resultado experimental ou contrato executável foi substituído por esta síntese.

## Critérios históricos de prontidão dos domínios

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

Esses critérios descrevem o planejamento inicial. Diretórios vazios não são requisito atual de clonagem; o provisionamento está no [guia de provisionamento](../README.md#fontes-e-reconstrução). A avaliação Supplier já terminou; Purchase permanece na decisão C e nenhum score combinado foi escolhido.
