# Invoice validation — Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans; steps tracked below.

**Goal:** Avaliar o modelo Invoice existente em VALIDATION sem retreinar.
**Architecture:** Um script junto dos comandos Invoice, um JSON agregado e um
relatório/protocolo; reutilizar contrato de features do treino. Sem backend,
frontend, serviço de modelos ou framework experimental novo.
**Tech Stack:** Bibliotecas já fixadas em requirements-dev.txt.
**Spec:** docs/invoice_validation.md.

## Global Constraints

Supplier encerrado: não ler TEST, executar notebooks, mudar resultados ou EDA.
Invoice TEST fechado. Sem treino real, tuning, novas features ou commit.
Preservar arquivos de dados, modelos e dependências existentes.
Autonomia autorizada: executar planejamento e implementação sem nova confirmação.

## Review Focus

- Leitura de TEST solicitada: recusar antes de I/O.
- IDs faltantes/duplicados/overlap: falhar antes de inferência.
- Labels desalinhadas: conferir join por ID, não posição.
- Score invertido/empate: maior é mais anômalo; decisão zero é normal.
- Grupos vazios, saída existente e modelo incompatível: diagnóstico sem sobrescrita.

## Task 1 — Avaliador e testes

Files: criar ml/scripts/avaliar_invoice.py e tests/invoice/test_evaluate_invoice.py.
Interfaces: load_validation(root, split='val') -> DataFrame validado;
summarize(y, prediction, score) -> dict; evaluate_frame(model, frame) -> dict;
run(root, output=None, split='val') -> dict. main() só encaminha CLI.

- [x] Escrever fixtures sintéticas reais de Parquet/modelo e testes de métricas
  calculadas à mão, por grupo, sem labels no score, allowlist e reexecução.
- [x] Demonstrar RED por módulo/funções ausentes.
- [x] Implementar script: validar fonte, modelo, score, gerar métricas e hashes.
- [x] Executar testes Invoice em isolamento e Ruff nos arquivos novos.
- [x] Revisão independente de código e protocolo antes de inferência real.

Casos numéricos: y=[0,0,1,1], alertas=[0,1,0,1], score=[0.1,0.8,0.4,0.9]:
matriz [[1,1],[1,1]], balanced_accuracy=0.5, F1_macro=0.5,
ROC_AUC=0.75, AP=5/6. Nunca-alertar: recall_1=0, accuracy=0.5.
Fraud_type com duas fraudes: um TP e um FN -> recall=0.5.
Fonte com ordem invertida deve reconciliar por invoice_id.

## Task 2 — Execução e documentação

Files: docs/invoice_validation.md, README.md, docs/implementation_roadmap.md,
ml/experiments/invoice_validation_v1.json (somente após gates aprovados).

- [x] Registrar hash dos arquivos protegidos sem abrir conteúdo Supplier TEST.
- [x] Integrar somente os novos arquivos revisados; preservar dados.
- [x] Executar inferência única em val, zero fits; se incompatibilidade, registrar
  bloqueio sem mudar modelo ou fazer retraining.
- [x] Documentar resultados observados e limites, atualizar status geral stale.
- [x] Conferir hashes pós-execução, JSON, diff e estado Git; não criar commit.

## Ledger

- Ruling: Invoice primeiro — já tem artefato e roadmap fase 6; Purchase depende
  de target/momento/moedas. Custo: adia a decisão Purchase sem bloquear Invoice.
- Ruling: manter offset original nesta baseline de validação — nenhuma seleção
  adicional agora; desempenho pode ser baixo e deve ser reportado sem ajuste.
- Ruling: execução inline em worktree isolado, revisão ao final; não repetir
  validações Supplier, apenas testes Invoice para respeitar fechamento.
- Ambiente temporário anterior incompleto; instalar os mesmos pins em nova venv
  separada, sem modificar requirements ou ambiente principal.
- Task 1: complete — RED (17 casos, avaliador ausente); GREEN final 38 testes
  Invoice em 8,30s; Ruff pontual aprovado; pip check sem conflitos. Revisão
  independente aprovada, sem Critical/Important. Nenhum commit.
- Final: minor (deferred to report): registrar SHA-256 do JSON de saída no
  relatório de resultados; não exige alteração do avaliador.
- Ruling: versão atual do checkout é b624204 e estava limpa, não bb9965a;
  preservar todos os artefatos dessa revisão, inclusive EDA. Custo: nenhum
  resultado antigo será reinterpretado ou refeito.
- Task 2: complete — inferência em 30.000 linhas val, zero fits reais; JSON
  exclusivo e relatório publicados. 51 hashes protegidos preservados, sem ler
  arquivos TEST. AP 0,31607 versus 0,22577 da referência; baixo poder de
  discriminação e volume alto de falsos positivos explicitados.
- Final: minor resolvido no relatório — hash externo do JSON registrado.
- Ruling: manter docs/invoice_validation.md imutável após execução; registrar
  observações em docs/invoice_validation_results.md para preservar o hash do
  protocolo. Custo: um documento adicional, sem framework novo.
- Próximo passo: auditar referência Invoice (446 fraudes tipo NONE; 140 normais
  com outros tipos) e procedência do modelo em TRAIN/VALIDATION, sem abrir TEST.
