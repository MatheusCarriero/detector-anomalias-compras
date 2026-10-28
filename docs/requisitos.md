# Requisitos funcionais e não funcionais

Este documento reúne os requisitos do projeto acadêmico e suas extensões planejadas. Os RF implementados descrevem funcionalidades existentes; os planejados representam evolução futura, não entregas concluídas. Nos RNF, “Atual” indica uma restrição ou prática vigente, não uma certificação de qualidade operacional.

Invoice prioriza faturas incomuns para auditoria humana. Supplier classifica a referência `Risk_Level` do dataset e já concluiu sua avaliação acadêmica. Purchase mantém decisões metodológicas pendentes. Os domínios têm fontes e resultados independentes, conforme a [estratégia dos modelos](model_strategy.md) e a [estratégia de dados](data_strategy.md).

Os critérios abaixo permitem conferir o comportamento esperado, preferencialmente com fixtures sintéticas. Sua inclusão não significa que testes foram executados nesta consolidação nem permite repetir avaliações ou usar TEST no desenvolvimento. O [roadmap](implementation_roadmap.md) registra o estado vigente e distingue etapas concluídas de planos históricos.

## Requisitos funcionais implementados

### RF01 — Validar a estrutura das entradas Invoice

- Descrição: conferir schema, tipos, ausência de nulos e infinitos nas features, labels binárias e lista ordenada das 19 features; labels e identificadores ficam fora da matriz do modelo.
- Ator/Responsável: adaptador de dados Invoice.
- Estado: Implementado.
- Critério de aceitação: uma entrada incompatível interrompe o fluxo antes do scoring; colunas inesperadas, valores inválidos ou ordem incorreta não são corrigidos silenciosamente.

### RF02 — Conferir IDs, partições e fontes Invoice

- Descrição: validar unicidade, cobertura e separação de IDs, correspondência das labels e consistência dos valores monetários e da moeda. O alinhamento usa IDs, não a posição das linhas.
- Ator/Responsável: adaptador e validador de inputs Invoice.
- Estado: Implementado.
- Critério de aceitação: IDs duplicados ou sobrepostos entre partições, fontes incompatíveis ou ausência de uma moeda única não nula impedem scoring e gravação.

### RF03 — Conferir a compatibilidade do modelo Invoice

- Descrição: verificar o modelo recebido contra metadata, configuração e contrato das features existentes.
- Ator/Responsável: adaptador Invoice.
- Estado: Implementado.
- Critério de aceitação: incompatibilidade com a configuração ou com as features é recusada antes do cálculo; a avaliação não ajusta o modelo nem altera seus parâmetros.

### RF04 — Gerar rankings e comparar estratégias Invoice

- Descrição: ordenar o score de anomalia do Isolation Forest e, separadamente, o valor da fatura, usando a mesma coorte e os orçamentos predefinidos de investigação.
- Ator/Responsável: avaliador Invoice.
- Estado: Implementado.
- Critério de aceitação: rankings seguem `-score_samples` e `invoice_amount` decrescentes, com desempate por `invoice_id` crescente; reportam todos os orçamentos de 1%, 5% e 10%, sem escolher um percentual pelos resultados.

### RF05 — Calcular as métricas previstas para a triagem

- Descrição: comparar recuperação da referência, composição por tipo e sobreposição das filas, sem interpretar anomalia como fraude confirmada.
- Ator/Responsável: avaliador Invoice.
- Estado: Implementado.
- Critério de aceitação: resultados incluem Precision@K, captura, lift, composição por `fraud_type`, casos comuns/exclusivos, Jaccard e ganhos previstos no protocolo. Denominadores inexistentes produzem `null`, sem ocultar grupos sem seleção.

### RF06 — Registrar resultados Invoice sem sobrescrita

- Descrição: gravar um JSON com identificação, partição, configuração, features, métricas, resultados, limitações e timestamp.
- Ator/Responsável: entrada pública de avaliação Invoice.
- Estado: Implementado.
- Critério de aceitação: destino existente é recusado antes da validação dos dados; falha de validação impede cálculo e gravação. A saída válida é criada em arquivo novo.

RF01–RF06 consolidam o [guia técnico Invoice](invoice_final_executor.md) e o [protocolo acadêmico](invoice_academic_evaluation_protocol.md). A avaliação final única em TEST foi concluída e está registrada em [invoice_test_final_v1.json](../ml/experiments/invoice_test_final_v1.json). Proteção contra sobrescrita não concede permissão para repetir TEST em outro destino.

### RF07 — Preparar e classificar fornecedores no estudo Supplier

- Descrição: consolidar a base por fornecedor, preservar nulos na base, separar partições antes da imputação e classificar `Risk_Level` conforme o protocolo do domínio.
- Ator/Responsável: scripts de preparação e executor acadêmico Supplier.
- Estado: Implementado.
- Critério de aceitação: IDs e partições seguem os contratos existentes, transformações aprendem somente no treino e o target não entra nas features. A configuração final e os resultados correspondem ao [registro final](supplier_risk_final_evaluation.md), sem reexecução para conferir este requisito.

Os detalhes de preparação e alinhamento permanecem no [contrato Supplier](supplier_risk_model.md). A classificação não é previsão de falha futura nem um serviço operacional implantado.

## Requisitos funcionais planejados

### RF08 — Disponibilizar resultados por interfaces de aplicação

- Descrição: expor endpoints versionados, com validação de entrada e contratos de saída específicos por domínio aprovado.
- Ator/Responsável: backend e ML engineering, conforme o roadmap.
- Estado: Planejado.
- Critério de aceitação: contratos de entrada/saída e testes de integração demonstram versão, semântica do resultado e tratamento de entradas inválidas; transformadores não são reajustados no consumo.

### RF09 — Apresentar os sinais dos domínios separadamente

- Descrição: disponibilizar telas que mostrem resultados, contexto e limitações de cada domínio, sem criar um score combinado implícito.
- Ator/Responsável: frontend e produto, conforme o roadmap.
- Estado: Planejado.
- Critério de aceitação: cada resultado é identificado pelo domínio e por seu significado; a interface não apresenta anomalia como fraude confirmada nem `Risk_Level` como risco empresarial comprovado.

RF08–RF09 correspondem às fases de contratos de inferência e aplicação do [roadmap](implementation_roadmap.md). Purchase não recebe requisitos de modelagem adicionais: objetivo, target quando aplicável, disponibilidade pré-aprovação e avaliação ainda dependem das decisões do [contrato Purchase](purchase_risk_model.md).

## Requisitos não funcionais atuais

### RNF01 — Confiabilidade diante de entradas inválidas

- Descrição: falhar explicitamente quando os contratos de entrada não forem atendidos, sem reparar dados ou descartar casos silenciosamente.
- Critério verificável: fixtures inválidas provocam erro antes do scoring e da escrita de resultados, conforme RF01–RF03 e o [guia Invoice](invoice_final_executor.md).
- Estado: Atual.

### RNF02 — Integridade e preservação de evidências

- Descrição: preservar fontes, modelos e resultados históricos; novas saídas de avaliação não sobrescrevem evidências existentes.
- Critério verificável: tentativas sintéticas de gravar em destino existente são recusadas; o diff da entrega não contém alterações científicas fora do escopo. Os registros não fabricam predições históricas ausentes.
- Estado: Atual.

### RNF03 — Rastreabilidade da configuração e dos resultados

- Descrição: identificar domínio, configuração, features, partição, versões e origem dos artefatos segundo o contrato de cada registro.
- Critério verificável: os campos exigidos estão presentes e correspondem às referências do experimento; hashes são conferidos quando previstos pelo contrato. Integridade não é tratada como prova da procedência do treinamento legado; `source_reconciled=false` permanece no Invoice.
- Estado: Atual.

### RNF04 — Reprodutibilidade com limites documentados

- Descrição: registrar versões e procedimentos do ambiente, mantendo dependências fixadas e distinguindo verificações sintéticas de reprodução científica.
- Critério verificável: `.python-version`, `requirements.txt` e `requirements-dev.txt` identificam o ambiente previsto; o [README](../README.md) registra instalação, verificações e limitações. Não se presume equivalência de modelos entre ambientes nem isolamento da instalação local sem evidência.
- Estado: Atual.

### RNF05 — Manutenibilidade e verificação isolada

- Descrição: manter funções reutilizáveis e testes sintéticos, sem depender dos datasets reais para validar pequenas mudanças.
- Critério verificável: testes pertinentes usam fixtures e diretórios temporários; importar o comando de treino Invoice não inicia treinamento. Ruff e pytest integram a verificação técnica prevista no [README](../README.md), respeitando as restrições de cada tarefa.
- Estado: Atual.

### RNF06 — Isolamento dos domínios e das partições

- Descrição: manter fontes, features e resultados independentes por domínio; impedir uso de TEST para exploração, desenvolvimento, tuning ou seleção.
- Critério verificável: contratos e registros identificam domínio e partição; não há merge de fontes com base em IDs apenas semelhantes. Transformações seguem o conjunto permitido pelo protocolo. A revisão pré-TEST não usa raw compartilhado, pois filtros de linhas não garantem isolamento físico.
- Estado: Atual.

RNF02–RNF06 se apoiam nas [estratégias de dados](data_strategy.md) e [modelos](model_strategy.md), no [guia Invoice](invoice_final_executor.md) e nos [registros Supplier](supplier_risk_experiment_records.md). São controles técnicos e metodológicos, não evidência de prontidão para produção.

## Requisitos não funcionais futuros

### RNF07 — Segurança da aplicação

- Descrição: prever controle de acesso mínimo, gestão de segredos, logs sem dados sensíveis e política de retenção.
- Critério verificável: políticas e controles documentados, com testes de acesso permitido/negado e revisão dos logs e da retenção antes de produção. Requisito qualitativo, sem SLA numérico definido.
- Estado: Futuro.

### RNF08 — Observabilidade e recuperação operacional

- Descrição: monitorar schema, qualidade, drift, distribuição de scores, latência e falhas; definir resposta a incidentes, rollback e suspensão do modelo.
- Critério verificável: responsáveis e critérios de alerta definidos, procedimentos de resposta documentados e recuperação ensaiada. Requisito qualitativo; metas de latência, throughput, disponibilidade, capacidade e escalabilidade não foram estabelecidas.
- Estado: Futuro.

Esses objetivos pertencem à fase de segurança, monitoramento e reprodutibilidade operacional do [roadmap](implementation_roadmap.md). Não representam infraestrutura já entregue. As limitações de procedência, validade externa e utilidade humana permanecem mesmo quando um requisito técnico é atendido.
