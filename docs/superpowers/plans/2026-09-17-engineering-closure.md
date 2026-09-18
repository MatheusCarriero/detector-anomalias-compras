# Fechamento de engenharia — plano de implementação

> For agentic workers: REQUIRED SUB-SKILL: use superpowers:subagent-driven-development.
> Execute com agentes especializados, TDD, revisão independente e sem commit.

**Goal:** eliminar efeitos colaterais de importação Invoice, criar contrato
verificável de evidências experimentais Supplier e consolidar o roadmap.

**Architecture:** preservar os três domínios. Novo utilitário Supplier somente
stdlib; Invoice mantém método, parâmetros, caminhos e metadata. Nenhum notebook
ou artefato real é executado/modificado.

**Tech Stack:** Python do ambiente isolado existente, pytest e Ruff já instalados.
Sem dependências novas.

**Spec:** ../specs/2026-09-17-engineering-closure-design.md.

## Autorização de encerramento — 2026-09-18

A implementação e a revisão de engenharia foram concluídas. O usuário confirmou
validação manual com 196 testes aprovados e Ruff sem avisos. Não repetir pytest,
Ruff, treinamento ou notebooks nesta etapa; conferir apenas documentos, escopo,
integridade dos arquivos e diff da integração.

Está autorizada a integração dos 12 arquivos deste plano ao checkout principal
e sua seleção explícita no índice Git (staging). Não criar commit ou fazer push:
o commit depende de autorização explícita posterior. Essa autorização substitui
somente a proibição anterior de staging, preservando as restrições metodológicas.
Arquivos temporários de execução, datasets, modelos e notebooks históricos não
fazem parte da integração.

Na retomada, o usuário autorizou preservar a alteração existente em
`ml/supplier_risk/notebooks/01_supplier_risk_eda.ipynb` no checkout principal,
integralmente fora do staging e do commit de engenharia. O README já transferido
será preservado; os outros 11 arquivos aprovados serão integrados seletivamente.
Qualquer outra alteração fora do escopo interrompe a integração.

### Situação das tarefas de implementação

As tarefas 1, 2 e 3 abaixo foram implementadas e revisadas. Seus comandos e
checklists descrevem o trabalho já realizado, não uma autorização para repetir
experimentos ou validações neste encerramento. A revisão documental final
preserva as regras de bootstrap, distingue scaling experimental de ML-ready e
explicita os limites de hashes e Unicode do contrato de evidências.

## Global Constraints

Não ler TEST, executar notebooks/modelos reais, alterar datasets/Parquets/splits/
targets/modelos/scores, modificar dependências, criar commit ou fazer push.
Staging é permitido somente no encerramento, para os 12 arquivos aprovados.
Preservar mudanças anteriores do usuário. Dados dos testes são sintéticos.
Arquivos fora da propriedade da tarefa não devem ser editados.
Agentes não criam outros agentes; o coordenador faz as revisões.
Cada implementador entrega relatório com arquivos, evidência RED/GREEN, comandos,
limitações e auto-revisão. Não declarar tarefa concluída antes da revisão.

## Task 1 — fronteira segura do treinamento Invoice

**Files:**
- Modify: ml/scripts/treinar_modelo.py
- Create: tests/invoice/test_train_model.py

**Interfaces:** validate_training_features(frame), main() e, se útil, factory
sem fit. Importação é inerte. main guard executa o comportamento CLI existente.

- [x] Escrever testes primeiro: importação com pd.read_parquet, fit e joblib.dump
  substituídos por sentinelas que falham se chamadas; importar deve passar sem I/O.
- [x] Adicionar testes para vazio, colunas ausentes/extra/reordenadas, valores
  não numéricos/complexos, nulos/infinitos; nenhuma mutação do frame.
- [x] Executar teste direcionado e registrar falha RED pelo efeito ao importar
  ou ausência da API, não por erro de sintaxe/ambiente.
- [x] Refatorar minimamente: validação explícita, main guard, preservar FEATURES
  ordenadas, parâmetros 200/0.22/42/-1, caminhos e chaves de metadata.
- [x] Testar execução com leitura sintética e estimador/dump dublês: apenas TRAIN,
  columns=FEATURES, fit uma vez, metadata consistente; não carregar labels.
- [x] Rodar testes direcionados, Ruff nos arquivos e revisão de diff.
- [x] Registrar relatório; entregar ao revisor sem commit.

Exemplo de comportamento contratual a cobrir:

```python
frame = pd.DataFrame(1.0, index=range(3), columns=module.FEATURES)
module.validate_training_features(frame)
with pytest.raises(ValueError):
    module.validate_training_features(frame.assign(is_fraud=0))
```

Comando direcionado (usar o Python isolado, -I -B, sem cache):
`python -I -B -m pytest -q -p no:cacheprovider tests/invoice/test_train_model.py`.

## Task 2 — evidência experimental Supplier sem fit

**Files:**
- Create: ml/supplier_risk/scripts/experiment_artifact.py
- Create: tests/supplier_risk/test_experiment_artifact.py

**Interfaces:** write_experiment_record(path, predictions, metadata) retorna
Path; verify_experiment_record(path) retorna envelope validado. CLI verify retorna
zero apenas em sucesso. Contrato completo no desenho; não criar runner de ML.

- [x] Escrever testes de API inexistente (RED) com listas/dicts sintéticos.
- [x] Cobrir round-trip, digest independente da ordem das linhas, fingerprint
  dos IDs e mismatch dos esperados, adulteração, JSON duplicado/não finito,
  versão/keys inesperadas, recusa de sobrescrita, CLI sucesso/falha.
- [x] Cobrir TEST/unknown, IDs vazios/repetidos/espaçados, bool/classes inválidas,
  NaN/Inf/probabilidade fora do intervalo, features erradas/cenários A/B/C/D.
- [x] Confirmar invalid input falha antes de mkdir; destino existente intacto.
- [x] Implementar apenas stdlib, JSON canônico e SHA-256, exceções explícitas.
- [x] Acrescentar UTC timestamp fora do digest; exigir contrato de metadata e
  fingerprint dos IDs; não ler fontes para validar procedência.
- [x] Rodar testes direcionados e Ruff; testar CLI com tmp_path via subprocess.
- [x] Registrar relatório RED/GREEN e limites; entregar ao revisor sem commit.

Exemplo de payload sintético (com metadata completa da fixture):

```python
rows = [dict(supplier_id="s1", split="validation", y_true=0,
             y_pred=1, probability_class_1=0.6)]
path = write_experiment_record(tmp_path / "record.json", rows, metadata)
assert verify_experiment_record(path)["payload"]["record_count"] == 1
with pytest.raises(FileExistsError):
    write_experiment_record(path, rows, metadata)
```

Comando: `python -I -B -m pytest -q -p no:cacheprovider
tests/supplier_risk/test_experiment_artifact.py`.

## Task 3 — estado atual e roteiro até a implementação final

**Files:**
- Modify: README.md
- Modify: docs/model_strategy.md
- Modify: docs/data_strategy.md
- Modify: docs/supplier_risk_model.md
- Create: docs/supplier_risk_experiment_records.md
- Create: docs/implementation_roadmap.md

- [x] Reconciliar afirmações atuais sobre EDA/baselines/validação Supplier;
  manter contexto histórico e distinguir experimental de final.
- [x] Documentar utilitário sem alegar existência de predições históricas
  persistidas ou certificado de ausência de TEST; incluir API/CLI verificáveis.
- [x] Roteiro por impacto com critérios de saída: módulos experimentais testáveis
  antes de novo experimento; artefatos transacionais; congelamento de candidato e
  protocolo; avaliação TEST única autorizada, sem refit TRAIN+VALIDATION;
  avaliação Invoice; decisão formal Purchase; contratos de inferência;
  backend/front e integração; segurança, monitoramento e reprodutibilidade.
- [x] Não escolher modelo, features finais, threshold, score combinado nem
  objetivo de negócio Purchase. KPI continua auxiliar.
- [x] Descrever limitações de procedência, ausência de validação externa/temporal
  e validade limitada do problema atual.
- [x] Checar links relativos/comandos contra interfaces reais, diff e coerência.
- [x] Registrar relatório e revisão independente; sem commit.

## Integração e gates

- [x] Revisão independente das três tarefas contra spec e qualidade.
- [x] Revisão final do conjunto e correção de achados relevantes.
- [x] Ruff completo; pytest sintético completo; git diff --check.
- [x] Transferir somente mudanças desta tarefa para o checkout original após
  verificação de precondições; preservar arquivos pré-existentes do usuário.
- [x] Conferir diff e integridade no checkout final, sem repetir a suíte ou Ruff,
  conforme autorização de encerramento e validação manual já aprovada.
- [x] Registrar arquivos alterados/criados, comandos e limitações na entrega.

## Execução autônoma e rastreamento

Worktree detached temporário, sem dados reais; ledger e relatórios de agentes em
.superpowers/sdd/2026-09-17-engineering-closure/. Usuário dispensou perguntas e
autorizou paralelização independente. Commits exigidos por templates das skills
foram omitidos para respeitar a decisão do projeto de não criar commit.
Na retomada de encerramento, o usuário autorizou staging seletivo sem commit.
Plano completo de produto no roadmap; somente as três tarefas acima são
implementadas agora, para não inventar decisões metodológicas pendentes.

## Registro do encerramento

As tarefas de implementação e a revisão documental estão concluídas. Os 12
arquivos aprovados foram integrados seletivamente ao checkout principal; o
conteúdo foi comparado com o worktree aprovado, desconsiderando somente CRLF/LF.
A conferência preservou 72 hashes de arquivos protegidos e os atributos de três
arquivos TEST, sem ler o conteúdo destes. O notebook EDA mantém o hash capturado
na retomada e permanece fora do staging de engenharia.

A validação de 196 testes e Ruff limpo é a validação manual anterior informada
pelo usuário; não foi repetida neste encerramento. A revisão local usa somente
diff, comparação de conteúdo, hashes e estado Git. Nenhum treinamento, notebook,
novo experimento ou commit foi executado. O staging seletivo está autorizado;
a criação do commit é o próximo passo e depende de autorização explícita.
