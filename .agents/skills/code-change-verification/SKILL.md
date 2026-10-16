---
name: code-change-verification
description: Use when changes affect Python code, tests, scripts, configuration, requirements, pipelines, executable logic, or files related to Invoice, Supplier or Purchase workflows, before considering the task complete.
---

# Code change verification

Conclusão exige evidência atual, não aparência de correção. Verificação técnica não autoriza avaliação científica nem amplia o escopo da tarefa.

## Fontes e segurança

Consulte [README](../../../README.md), [CI](../../../.github/workflows/quality.yml), [pytest.ini](../../../pytest.ini), [requirements](../../../requirements.txt) e [requirements-dev](../../../requirements-dev.txt); preserve os comandos vigentes quando aplicáveis.

Para Invoice pré-TEST, **use obrigatoriamente $invoice-pretest-guard** em [SKILL.md](../invoice-pretest-guard/SKILL.md). Identifique a etapa vigente. Não acessar, hashear ou avaliar TEST Invoice para verificar código; não executar a rota real como ensaio. O fluxo acadêmico não exige reconstruir Freeze, Contexto, recibos ou autorização formal. A avaliação final precisa de uma tarefa explícita e separada, não de um ensaio de desenvolvimento.

## Sequência de verificação

1. Inspecione `git status --short --untracked-files=all`. Separe alterações da tarefa das preexistentes e registre o estado inicial.
2. Revise o diff relevante, inclusive staged (`git diff --cached`); inspecione arquivos novos separadamente, pois `git diff` não os inclui. Procure alterações fora do escopo.
3. Execute `git diff --check`; confira também `git diff --cached --check` quando houver staging. Verifique whitespace dos arquivos novos sem adicioná-los ao staging.
4. Mapeie mudanças aos testes em `tests/invoice/` e `tests/supplier_risk/`; não presuma cobertura Purchase existente. Antes de coletar/executar, leia testes, fixtures, conftest e imports relevantes: procure datasets reais, notebooks, artefatos históricos, caminhos protegidos e escritas. Até coleta pode importar código. Prefira fixtures sintéticas isoladas.
5. Execute primeiro os testes direcionados seguros, acrescentando seus caminhos/node IDs ao comando pytest abaixo. `pytest.ini` fornece `pythonpath = .` e configuração estrita; não altere isso para mascarar problemas.
6. Execute Ruff conforme abaixo, sem `--fix` automático. Preserve notebooks protegidos; se o escopo amplo conflitar com restrições, selecione somente arquivos permitidos e informe a limitação.
7. Execute a suíte completa somente se segura, permitida e proporcional ao impacto. Mudanças compartilhadas favorecem regressão ampla, não acesso protegido. `test_invoice_eda.py` executa células: quando notebooks forem proibidos, exclua-o antes da coleta e informe que a execução foi parcial.
8. Se dependências, especialmente os dois requirements, mudarem, execute `pip check`. Ele verifica compatibilidade instalada, não comprova instalação dos novos pins ou reprodução limpa. Registre divergências; não instale/atualize pacotes automaticamente.
9. Revise novamente `git status` e os diffs após verificações, distinguindo saídas geradas e alterações preexistentes. Não apague mudanças inesperadas; relate-as.
10. Relate comandos, ambiente efetivo, códigos de saída e resultados observados. Falha de ambiente/coleta não é aprovação nem prova de defeito no código. Skips não são passes; contagens históricas não são metas fixas.

## Comandos preferidos

Na raiz, usando a `.venv` existente:

```powershell
.\.venv\Scripts\python.exe -I -B -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -I -m ruff check . --no-cache
.\.venv\Scripts\python.exe -I -m pip check
```

Aplique as condições acima; não execute os três indiscriminadamente. Se a `.venv` estiver indisponível/incompatível, registre o bloqueio, sem substituição silenciosa.

No Windows, para problema de temporários, acrescente `--basetemp` com caminho novo, exclusivo e descartável, preferencialmente fora do checkout. Verifique o caminho absoluto: pytest pode apagar seu conteúdo. Nunca use `data/`, raiz do projeto, diretório de artefatos, local protegido ou pasta existente com arquivos importantes.

## Limites e falhas

Não execute pipelines/datasets reais para validar pequenas mudanças. Não reprocessar Supplier nem repetir sua avaliação. Não altere testes para aprovar implementação incorreta; não corrija problemas alheios à tarefa. Preserve alterações do usuário: nada de apagar/restaurar/sobrescrever, `git restore`, `git reset`, `git clean` ou comandos destrutivos sem autorização explícita. Não faça commit/push automaticamente.

| Nível | Consequência |
|---|---|
| BLOCKER | Falha relevante ou violação de segurança: alteração não pode ser considerada concluída. |
| HIGH | Risco significativo de regressão ou validação incompleta; explicite a pendência. |
| MEDIUM | Verificação parcial ou cobertura insuficiente; delimite o que foi comprovado. |
| LOW | Observação não bloqueante. |

Nunca declare sucesso de comando não executado, use resultado anterior como validação atual ou apresente suíte parcial como completa.

## Entrega obrigatória

Informe: arquivos modificados; testes direcionados executados; Ruff; pytest (aprovados/falhas/skips e motivos); `git diff --check`; outras verificações; verificações não executadas e motivos; riscos/limitações com gravidade. Se segurança ou autorização impedir validação, declare a pendência, não contorne a restrição.
