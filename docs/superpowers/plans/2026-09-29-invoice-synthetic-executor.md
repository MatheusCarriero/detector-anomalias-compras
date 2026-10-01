# Invoice synthetic final executor — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkboxes; no commits or real-data execution in this task.

**Goal:** validar o contrato de execução única Invoice exclusivamente com fixtures sintéticas.
**Architecture:** módulo novo, sem CLI real/default de caminho; preparação congelada, avaliação pura e publicação separadas. Reusar apenas helpers puros dos rankings existentes, sem alterar scripts históricos ou Supplier.
**Tech Stack:** Python, pandas, numpy, scikit-learn, joblib, pyarrow, pytest, Ruff existentes; sem instalar dependências.
**Spec:** [protocolo acadêmico](../../invoice_academic_evaluation_protocol.md) e requisitos da solicitação de 29/09/2026.

## Global Constraints

- Não abrir TEST/dados/modelo reais, executar notebooks, ajustar threshold ou treinar modelo real.
- Mesmas 19 features ordenadas e nove parâmetros IF; orçamentos 1%, 5%, 10%.
- Nenhum resultado da revisão cega simulada; artefatos de testes somente temporários e identificados como não acadêmicos.
- Nenhuma alteração Supplier, pipelines históricos, datasets, resultados científicos, staging ou commit.

## Review Focus

- Ordem/colunas: rejeitar schema antes de selecionar FEATURES, sem reparação silenciosa.
- Integridade: confirmar bytes lidos, hashes maiúsculos/minúsculos, configuração e código.
- Concorrência/falha: claim exclusivo antes da leitura do holdout; falha preserva bloqueio.
- Cegamento científico: artefato sintético nunca parece avaliação TEST real.
- Diagnósticos: matriz por tipo usa a seleção global, não reordenação dentro de cada tipo.

## Decisões de implementação

- Continuação do escopo já documentado/autorizado; não reabrir planejamento metodológico ou pedir novas decisões. Implementação no checkout atual em arquivos novos, pois helpers/protocolos aprovados ainda não estão commitados; arquivos preexistentes preservados. A limitação do snapshot na retomada está registrada abaixo.
- Matriz solicitada significa referência 0/1 versus não selecionado/selecionado em cada top-K. Offset conferido, sem predict/decision_function. Uma matriz pelo threshold legado permanece fora do contrato acadêmico vigente.
- API nesta etapa aceita somente `synthetic_holdout`, diretórios explicitamente fornecidos fora do checkout e fixtures confiáveis. Não há modo real nem autorização TEST por flag. O modelo da fixture tem seu próprio offset congelado; não se falsifica sua identidade como modelo legado.
- Preparação registra hashes de modelo/metadata/IDs de desenvolvimento e código antes do acesso ao holdout. Os outros hashes são registrados após claim. Diretório existente bloqueia novo freeze; marcador de início persiste mesmo com falha.
- Artefatos sintéticos não são acrescentados a `ml/experiments/` ou aos relatórios científicos. Temp fixtures são geradas pelos testes; um marcador sintético não é prova de procedência de arquivo arbitrário.

## Task 1 — contrato, cálculo e ciclo de evidência

**Files:** criar `ml/scripts/invoice_final_evaluation.py` e `tests/invoice/test_invoice_final_evaluation.py`.
**Interfaces:** `configuration_contract(offset) -> dict`; `freeze_configuration(fixture_root, run_dir, configuration) -> Path`; `load_frozen_configuration(path, expected_sha256) -> dict`; `evaluate_frame(model, frame, configuration) -> dict`; `run_synthetic_evaluation(freeze_path, *, expected_freeze_sha256) -> Path`; `verify_bundle(results_dir, *, expected_manifest_sha256, expected_freeze_sha256) -> dict`.

- [x] Escrever primeiro fixtures/testes: IF novo ajustado só em números sintéticos, arquivos temporários, métricas com exemplos manuais, schema/labels/IDs/hash/modelo/split inválidos, repetição e falha após claim.
- [x] Executar teste inicial e observar falha pela ausência da implementação.
- [x] Implementar contrato estrito e configuração JSON exclusiva, com hash externo esperado.
- [x] Implementar leitura de bytes verificados e validação exata por IDs; score único sem fit e resumo comparativo reutilizado.
- [x] Implementar diagnósticos seleção@K, publicação exclusiva com manifesto e verificação dos hashes publicados.
- [x] Executar testes sintéticos novos e regressões; corrigir somente o novo escopo.

## Task 2 — revisão, documentação técnica e integridade

**Files:** criar `docs/invoice_final_executor.md`; atualizar somente este plano com execução real dos testes.

- [x] Revisor independente lê código/testes, sem dados reais.
- [x] Executar Ruff dos arquivos envolvidos e git diff --check (incluindo novos arquivos).
- [x] Conferir evidências disponíveis de integridade e suas limitações, guardas de acesso aos diretórios reais durante os testes, ausência de novos artefatos científicos e estado do Git.
- [x] Registrar limitações/uso técnico; nenhuma métrica sintética no relatório acadêmico.

## Registro de execução

29/09: protocolo/avaliador/rankings/executor Supplier lidos como código. Supplier usado apenas como referência de congelamento, claim e publicação; nenhuma decisão de classificação/treinamento copiada. Nenhum dado real carregado. Snapshot inicial: 91 hashes de arquivos de código/documentação/evidências e 42 registros de tamanho/data de dados protegidos; HEAD b624204.

### Implementação e revisão concluídas

- TDD: falha inicial por módulo ausente observada. Um teste detectou restrição
  indevida de valores monetários positivos; removida somente essa restrição nova,
  preservando o ranking pelo valor original assinado.
- Testes específicos antes do último ajuste: 69 aprovados, 1 ignorado. Revisão
  independente identificou a possibilidade de copiar o freeze e contornar o
  claim. `test_copied_freeze_cannot_bypass_consumed_attempt` foi RED e depois
  GREEN com `run_dir` incluído e validado no congelamento.
- Suíte final: `pytest.main(['-q', '-p', 'no:cacheprovider'])`, com guardas de
  leitura no processo Python e carregadores pandas/joblib: **392 passed,
  1 skipped in 41.79s; REAL_PROJECT_DATA_ACCESS_ATTEMPTS=0**. O teste ignorado
  depende da permissão Windows para symlinks.
- Ambiente já disponível:
  `C:/Users/mathe/AppData/Local/Temp/invoice-validation-88a846b12e0a4242884d458de4dc8297/venv/Scripts/python.exe`.
  Nenhuma instalação ou alteração da `.venv` principal nesta entrega.
- Ruff dos dois arquivos Python novos: **All checks passed!**
- Revisão focal da correção: nenhum achado bloqueante para o incremento
  exclusivamente sintético. Não representa autorização para TEST real.
- Final: minor (deferred): teste de disputa simultânea entre processos pelo
  claim; criação exclusiva revisada, fluxo sequencial e cópia do freeze cobertos.

### Limites da revisão e integridade

- Fixtures joblib são locais e confiáveis. Não há certificação da origem de
  arquivos arbitrários ou proteção contra alguém que possa apagar marcadores;
  este contrato não é um sandbox de segurança.
- Procedência do fit legado, adaptação aos dados reais e utilidade científica
  estão fora desta entrega. Matrizes usam seleção@K, conforme protocolo, não
  classificação de fraude pelo threshold legado.
- Os valores individuais do snapshot inicial em memória não estavam disponíveis
  na retomada. Não foi alegada comparação SHA-256 completa antes/depois nem
  aberto TEST para tentar reconstruí-la.
- Conferência por metadados: 42 arquivos protegidos e 91 arquivos preexistentes
  de código/documentação/evidências; nenhum com LastWriteTimeUtc posterior ao
  marcador de início `2026-09-29T04:11:14.561165Z`. Isso é evidência operacional,
  não substitui a comparação criptográfica perdida.
- HEAD preservado: `b624204baeaaa910719985eb10d14cecd440346d`; staging vazio.
  Somente os quatro arquivos deste plano foram criados; alterações antigas,
  incluindo os notebooks Supplier, permaneceram fora do escopo.

### Próxima etapa

Não repetir testes ou experimentos por causa de uma retomada documental.
Para eventual avaliação real, preparar separadamente o adaptador mínimo de
leitura seletiva, vínculo com o modelo legado e congelamento real; revisar esses
limites e registrar autorização antes de qualquer acesso a TEST. Não habilitar
o executor sintético por alteração de flag. Nenhum commit criado.
