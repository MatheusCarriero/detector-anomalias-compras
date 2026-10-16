---
name: invoice-pretest-guard
description: Use when a task involves Invoice Anomaly, final evaluation or scoring, TEST access or authorization, invoice_final_evaluation.py, invoice_real_inputs.py, Invoice data adapters, evaluation artifacts or evidence, model/features/threshold changes, or Invoice data preparation/reprocessing.
---

# Invoice pré-TEST guard

Esta skill protege a separação entre desenvolvimento e avaliação acadêmica final. Não concede permissão para acessar dados fora do escopo da tarefa.

## Antes de implementar

1. Leia [README](../../../README.md), [roadmap](../../../docs/implementation_roadmap.md), [protocolo acadêmico](../../../docs/invoice_academic_evaluation_protocol.md) e [guia técnico](../../../docs/invoice_final_executor.md). Informe qual etapa **vigente** a tarefa atende; diferencie estado atual de histórico datado.
2. Confira o Git e preserve alterações preexistentes. Inspecione scripts afetados em `ml/scripts/` e testes em `tests/invoice/`: imports, leituras, escritas, splits e efeitos colaterais, antes de executar comandos. Esses caminhos são relativos à raiz do repositório.
3. Confira a configuração científica, os inputs e o destino exigidos pela tarefa, sem abrir dados protegidos. O fluxo acadêmico não exige Freeze, Contexto, recibos, manifestos ou documento formal de autorização; não reconstrua essa infraestrutura.

## Guardas obrigatórias

- TEST Invoice permanece reservado à avaliação final, em tarefa que a solicite explicitamente. Mudanças de código ou documentação não autorizam ler, hashear, pontuar ou avaliar TEST. Não fabricar autorização ou evidência.
- Nunca usar TEST para debugging, exploração, tuning, escolha de features/threshold ou desenvolvimento. Não chamar a rota real nem validar inputs reais apenas para testar funcionamento.
- Não acessar raw compartilhado no pré-TEST. Filtros TRAIN/VALIDATION não isolam fisicamente TEST; não copiar dados reais ou trocar caminhos para contornar guardas. Confira leituras efetivas: o adaptador pode carregar ambas as partições de desenvolvimento mesmo solicitando uma.
- Não retreinar o Isolation Forest nem alterar as 19 features ou sua ordem como efeito colateral. Consulte `FEATURES` em `ml/scripts/treinar_modelo.py`; labels/IDs não são features. Contamination, threshold, regra de triagem e metodologia exigem tarefa explicitamente destinada à revisão metodológica, nunca mudança silenciosa.
- Não repetir avaliações históricas concluídas, nem em outro destino. Não sobrescrever JSONs, métricas, relatórios ou evidências. Não fabricar evidência ausente nem incorporar revisão cega simulada como evidência científica.
- Preserve datasets originais, processados, modelos e registros históricos. Não executar preparação legada sobre dados reais como teste. Não reprocessar Supplier, cuja avaliação acadêmica terminou; não iniciar Purchase, backend ou frontend como efeito colateral.
- Prefira fixtures artificiais isoladas e testes automatizados. Inspecione a seleção: testes podem executar células de notebooks ou importar preparação. Não execute testes incompatíveis com as restrições da tarefa.
- Mantenha `source_reconciled=false` nos registros reais. Consistência de linhas, hashes e compatibilidade não certificam procedência independente do treinamento legado. Resultados sintéticos não são resultados científicos.

## Classificação e interrupção

| Nível | Critério e ação |
|---|---|
| BLOCKER | TEST fora da avaliação final solicitada ou usado no desenvolvimento; retreino/mudança metodológica não solicitada; alteração silenciosa das 19 features; sobrescrita histórica; pipeline capaz de reprocessar/contaminar dados protegidos. Interrompa antes da ação e explique a pendência. |
| HIGH | Lacuna de validação de schema, IDs, splits, configuração, rastreabilidade ou proteção contra sobrescrita. Suspenda o caminho afetado; se permitir violação acima, eleve a BLOCKER. |
| MEDIUM | Inconsistência documental ou cobertura insuficiente sem violação identificada. Registre impacto e correção no escopo. |
| LOW | Clareza/apresentação sem efeito metodológico ou de integridade. Registre sem ampliar o escopo. |

Informe etapa atendida, achados com nível/evidência, ações bloqueadas, arquivos alterados e verificações realmente executadas. Se a tarefa não permitir avaliação final, pare antes de acessar TEST e explique a restrição.
