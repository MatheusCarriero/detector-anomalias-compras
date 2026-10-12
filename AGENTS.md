# Instruções do repositório

## Escopo e fonte de verdade

- Invoice Anomaly, Supplier Risk e Purchase Risk são domínios independentes. Não misture features, labels, scores, datasets, conclusões ou metodologia sem decisão explícita documentada.
- Antes de mudanças metodológicas, arquiteturais ou de fluxo, consulte a documentação relevante em `docs/`, o [README](README.md) e a [estratégia dos modelos](docs/model_strategy.md).
- Use o [roadmap](docs/implementation_roadmap.md) para identificar o estado e o gate vigente. Atualizações históricas não são tarefas pendentes quando o estado vigente declara sua conclusão; não repita etapas nem deduza autorização delas.

## Invoice

- O objetivo atual é triagem de anomalias para auditoria humana. Anomaly score não significa fraude confirmada, probabilidade de fraude ou risco empresarial comprovado.
- TEST permanece protegido pelo [protocolo acadêmico](docs/invoice_academic_evaluation_protocol.md) e pelo [contrato técnico](docs/invoice_final_executor.md). Implementação, freeze e contexto não equivalem a autorização humana.
- Para tarefas Invoice envolvendo pré-TEST, avaliação final, TEST, autorização, scoring real, dados reais, adaptadores, contexto de execução, freeze ou evidências, use obrigatoriamente **$invoice-pretest-guard** antes de implementar ou executar verificações. Isso inclui `invoice_final_evaluation.py`, `invoice_real_evaluation.py` e `invoice_real_inputs.py`.
- Leia a skill em [.agents/skills/invoice-pretest-guard/SKILL.md](.agents/skills/invoice-pretest-guard/SKILL.md). Respeite seus bloqueios; não execute a rota real como ensaio. Preserve `source_reconciled=false`: integridade e compatibilidade não certificam a procedência do treinamento legado.

## Supplier e Purchase

- Supplier concluiu sua avaliação acadêmica final. Não repita EDA, treinamento, seleção, VALIDATION ou TEST como parte de outra tarefa. Reproduzir `Risk_Level` não comprova risco empresarial real nem previsão de falha futura.
- Purchase mantém decisões metodológicas pendentes. Não invente target, interpretação de risco, score final ou pipeline de modelagem para preencher lacunas; siga o gate documentado.

## Alterações de código

- Antes de modificar, inspecione `git status`, preserve alterações preexistentes, estude a implementação existente mais próxima e limite mudanças ao escopo solicitado.
- Não use automaticamente `git restore`, `git reset`, `git clean` ou comandos destrutivos. Não faça commit ou push sem autorização explícita.
- Não corrija problemas não relacionados apenas porque foram encontrados. Não apague, restaure ou sobrescreva trabalho preexistente do usuário.

## Verificação

- Para alterações em Python, testes, scripts, configuração, requirements, pipelines ou lógica executável, use obrigatoriamente **$code-change-verification** antes de considerar a tarefa concluída: [.agents/skills/code-change-verification/SKILL.md](.agents/skills/code-change-verification/SKILL.md).
- Se envolver Invoice pré-TEST, use também **$invoice-pretest-guard**; verificação técnica não autoriza ultrapassar gates metodológicos.
- Nunca declare que algo funciona apenas por inspeção, nem que um comando ou teste passou sem execução efetiva. Informe verificações executadas, omitidas e respectivos motivos; respeite restrições de execução da tarefa.

## Dados e ML

- Preserve datasets originais, artefatos congelados e evidências históricas. Não sobrescreva resultados nem fabrique evidência ausente.
- Não use TEST para debugging, tuning, desenvolvimento ou exploração. Não introduza target leakage, data leakage ou informação futura.
- Não execute pipelines de dados reais apenas para validar pequenas alterações. Prefira fixtures sintéticas e testes isolados quando permitidos; inspecione efeitos colaterais antes de executar.

## Estilo de implementação

- Priorize mudanças pequenas, reutilização dos padrões existentes, código simples e explicável e testes compatíveis com o comportamento alterado.
- Evite abstrações especulativas, dependências desnecessárias, refatorações paralelas não solicitadas e reescrita de notebooks históricos.
