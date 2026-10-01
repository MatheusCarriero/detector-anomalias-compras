# Roadmap de implementação

## Atualização de execução — 28/09/2026

A [comparação IF versus valor](invoice_value_comparison_results.md) está
**concluída em VALIDATION**: ganho líquido de positivos −40/+7/+192 nos orçamentos
fixos 1%/5%/10%. Não há vencedor uniforme, orçamento escolhido ou utilidade
empresarial comprovada. Não repetir essa comparação como pendência.

O teste técnico da revisão cega foi encerrado pelo responsável. Avaliadores
artificiais não são pessoas nem evidência; respostas simuladas, concordância e
julgamentos ficam excluídos de resultados, JSONs e decisões acadêmicas. ZIPs
simulados devem permanecer fora do repositório. A [preparação original](invoice_blind_review_preparation.md)
foi preservada; não houve revisão humana válida e uma eventual etapa real segue
separada, sem ser substituída pela simulação.

**Próximo gate Invoice:** o [contrato acadêmico](invoice_academic_evaluation_protocol.md)
separa benchmark retrospectivo de adoção operacional. Implementar/revisar somente
o executor mínimo e seus testes sintéticos antes de qualquer avaliação final.
TEST permanece fechado até autorização registrada e congelamento pré-acesso;
nenhum retreino, mudança de algoritmo, features, labels ou percentuais. Custos,
capacidade e avaliação humana reais continuam necessários para alegar utilidade
operacional, não podem ser inferidos do benchmark ou da simulação.

As atualizações datadas abaixo preservam o histórico, não redefinem o próximo
passo vigente. Supplier/Purchase e suas decisões permanecem fora desta etapa.

## Atualização de execução — 27/09/2026

Invoice foi formalizado como **triagem de anomalias para auditoria humana**,
não classificação automática de fraude. A avaliação anterior e a
[auditoria metodológica](invoice_methodological_audit.md) estão concluídas e
preservadas; as pendências de auditoria abaixo são registros históricos.

O [protocolo de triagem](invoice_triage_protocol.md) e seus
[resultados](invoice_triage_results.md) registram diagnóstico top-1%/5%/10%
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
- TRAIN serve para exploração, ajuste e treino; VALIDATION para comparação/seleção; TEST somente para uma avaliação final autorizada após congelamento explícito;
- o protocolo Supplier atual não permite refit em `TRAIN + VALIDATION`;
- métricas Supplier medem reprodução de `Risk_Level`, não risco empresarial real;
- datasets de origem permanecem imutáveis;
- decisões de negócio, custos de erro e autorização de TEST precisam ser registradas, não inferidas de métricas.

## 2. Estado de partida

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

**Impacto:** alto e irreversível do ponto de vista metodológico.

**Responsáveis:** executor autorizado e revisor independente.

**PLANEJADO:** somente após o gate anterior, ajustar a configuração congelada em TRAIN, sem incorporar VALIDATION, e avaliar uma vez em TEST. Não haverá EDA, tuning, calibração, troca de feature, mudança de threshold ou refit em `TRAIN + VALIDATION`.

**Gate de saída:** relatório completo da execução única, incluindo desvios do protocolo, métricas predefinidas, incerteza aplicável, limitações, hashes e decisão de aceitar ou rejeitar o candidato para o uso declarado. Resultado insatisfatório é reportado como tal; TEST não realimenta uma nova seleção.

Mesmo um resultado favorável não supre validação externa/temporal nem prova risco empresarial real.

## 8. Fase 6 — fechamento metodológico do Invoice

**Impacto:** alto; o modelo existe, mas sua avaliação operacional não está fechada.

**Responsáveis:** ciência de dados Invoice e revisão de risco.

**CONCLUÍDO:** avaliação consolidada/por `fraud_type`, auditoria metodológica, diagnóstico de triagem e comparação IF versus valor em VALIDATION nos orçamentos 1%/5%/10%, preservando 19 features e a configuração (`IsolationForest`, 200 árvores, `contamination=0.22`, `random_state=42`, `n_jobs=-1`). Sem retreino, tuning ou seleção de threshold. O objetivo vigente é priorização de faturas incomuns para auditoria humana. Teste técnico da revisão cega encerrado e excluído da evidência acadêmica; nenhuma revisão humana válida realizada.

**PLANEJADO — acadêmico:** executor mínimo, validação sintética e registro pré-acesso segundo o [contrato](invoice_academic_evaluation_protocol.md). Eventual avaliação final única compara as duas estratégias em todos os orçamentos, sem retreino ou ajuste condicionado a TEST. A procedência parcial do fit e a validade não comprovada da referência permanecem explícitas.

**Gate acadêmico:** configuração, métricas e conclusões admissíveis registradas antes do acesso; revisão técnica, autorização explícita e evidência de execução única, sem alegar certificação retroativa do treinamento legado. Este gate não foi executado/liberado nesta etapa. O score não é probabilidade de fraude.

**Gate operacional separado:** evidência humana real, contexto disponível, capacidade/custos e eventual regra operacional pré-definida. Se um threshold vier a ser necessário, sua seleção/congelamento exige protocolo próprio em validação; não é necessário inventá-lo para o ranking retrospectivo. Sem evidência operacional, não liberar produção, mesmo com benchmark favorável. Mudanças metodológicas exigem nova versão, não alteração silenciosa do artefato existente.

## 9. Fase 7 — decisão formal do Purchase

**Impacto:** bloqueante para qualquer modelagem Purchase.

**Responsáveis:** proprietário do processo de compras, especialista de domínio, dados e ML.

**PLANEJADO:** escolher formalmente entre detecção de anomalias e previsão de um desfecho específico; confirmar unidade operacional, target/horizonte quando aplicável, instante pré-aprovação, disponibilidade das features e política para moedas. A fonte disponível representa linhas de pedido; agregação não será inventada.

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
