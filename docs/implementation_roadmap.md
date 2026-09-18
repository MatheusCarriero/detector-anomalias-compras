# Roadmap de implementação

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

**PLANEJADO:** preservar as 19 features e a configuração atual (`IsolationForest`, 200 árvores, `contamination=0.22`, `random_state=42`, `n_jobs=-1`) enquanto se define protocolo de avaliação, threshold somente em validação, análise consolidada e por `fraud_type`, e comportamento para fornecedores não observados. Revisar o limite das agregações de TRAIN, que não são ponto-a-ponto temporais.

**Gate de saída:** protocolo pré-registrado, threshold congelado sem uso de TEST, avaliação final documentada e contrato de score que não confunda anomalia com probabilidade de fraude. Mudanças de metodologia exigem nova versão, não alteração silenciosa do artefato existente.

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
