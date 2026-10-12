---
name: invoice-pretest-guard
description: Use when a task involves Invoice Anomaly, final evaluation or scoring, TEST access or authorization, invoice_final_evaluation.py, invoice_real_inputs.py, Invoice data adapters, evaluation artifacts or evidence, model/features/threshold changes, or Invoice data preparation/reprocessing.
---

# Invoice pré-TEST guard

Esta skill protege o gate metodológico; não concede autorização nem substitui as guardas do código.

## Antes de implementar

1. Leia [README](../../../README.md), [roadmap](../../../docs/implementation_roadmap.md), [protocolo acadêmico](../../../docs/invoice_academic_evaluation_protocol.md) e [contrato técnico](../../../docs/invoice_final_executor.md). Informe qual gate **vigente** a tarefa atende; diferencie estado atual de histórico datado. Não invente permissões para resolver conflitos.
2. Confira o Git e preserve alterações preexistentes. Inspecione scripts afetados em `ml/scripts/` e testes em `tests/invoice/`: imports, leituras, escritas, splits e efeitos colaterais, antes de executar comandos. Esses caminhos são relativos à raiz do repositório.
3. Confira autorização, configuração, hashes, destino e bloqueios de repetição conforme o contrato vigente, sem abrir dados protegidos. Freeze, contexto e recibo não iniciam avaliação nem equivalem a aprovação humana independente.

## Guardas obrigatórias

- TEST Invoice fica fechado: não ler, hashear, pontuar ou avaliar sem autorização explícita já registrada, válida e vinculada ao freeze/contexto/destino conforme o protocolo, além de tarefa que autorize a execução. Não fabricar aprovador ou autorização; checksum comprova integridade, não identidade humana.
- Nunca usar TEST para debugging, exploração, tuning ou desenvolvimento. Não chamar a rota real nem validar inputs reais apenas para testar funcionamento: o acesso consome a tentativa mesmo sem scoring.
- Não acessar raw compartilhado no pré-TEST. Filtros TRAIN/VALIDATION não isolam fisicamente TEST; não copiar dados reais ou trocar caminhos para contornar guardas. Confira leituras efetivas: o adaptador pode carregar ambas as partições de desenvolvimento mesmo solicitando uma.
- Não retreinar o Isolation Forest nem alterar as 19 features ou sua ordem nesta etapa. Consulte `FEATURES` em `ml/scripts/treinar_modelo.py`; labels/IDs não são features. Contamination, threshold, regra de triagem e metodologia congelada exigem tarefa explicitamente destinada à revisão metodológica, nunca mudança silenciosa.
- Não repetir avaliações históricas concluídas, nem em outro destino. Não sobrescrever JSONs, métricas, relatórios ou evidências; preserve marcadores de início/falha e parciais. Não fabricar evidência ausente nem incorporar revisão cega simulada como evidência científica.
- Preserve datasets originais, processados e artefatos congelados. Não executar preparação legada sobre dados reais como teste. Não reprocessar Supplier, cuja avaliação acadêmica terminou; não iniciar Purchase, backend ou frontend como efeito colateral.
- Prefira fixtures artificiais isoladas e testes automatizados. Inspecione a seleção: testes podem executar células de notebooks ou importar preparação. Não execute testes incompatíveis com as restrições da tarefa.
- Mantenha `source_reconciled=false` nos registros reais. Consistência de linhas, hashes e compatibilidade não certificam procedência independente do treinamento legado. Resultados sintéticos não são resultados científicos.

## Classificação e interrupção

| Nível | Critério e ação |
|---|---|
| BLOCKER | TEST não autorizado ou usado no desenvolvimento; retreino/mudança metodológica não autorizada; alteração silenciosa das 19 features; sobrescrita histórica; pipeline capaz de reprocessar/contaminar dados protegidos; ultrapassar o gate. Interrompa antes da ação e explique a pendência. |
| HIGH | Lacuna de autorização, hashes, rastreabilidade ou replay. Suspenda o caminho afetado; se permitir violação acima, eleve a BLOCKER. |
| MEDIUM | Inconsistência documental ou cobertura insuficiente sem violação identificada. Registre impacto e correção no escopo. |
| LOW | Clareza/apresentação sem efeito metodológico ou de integridade. Registre sem ampliar o escopo. |

Informe gate atendido, achados com nível/evidência, ações bloqueadas, arquivos alterados e verificações realmente executadas. Autorização insuficiente ou conflito com o gate exige parada e explicação, nunca bypass ou aprovação presumida.
