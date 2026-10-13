# Invoice: contrato portátil e contexto vinculado

## Escopo aprovado

Separar o congelamento portátil do contexto concreto de execução; autorização futura
deve vincular hashes de ambos e o destino. Nenhum artefato real de congelamento ou
autorização será emitido. TEST, datasets, modelo e notebooks Supplier intocados.

## Desenho e compatibilidade

- `invoice-portable-freeze/1.0`: configuração, versões, nomes relativos, hashes
  permitidos e evidências históricas; sem caminhos absolutos e sem autorização.
- `invoice-execution-context/1.0`: caminho do freeze, project_root, run_dir,
  inputs, destino e hashes permitidos. Hashes de TEST/raw permanecem nulos.
- `invoice-real-authorization/1.3`: vincula freeze, contexto, configuração,
  destino, escopo, validade e reconhecimento de procedência incompleta.
- Novas execuções rejeitam contratos reais antigos; não existe migração implícita.
  Executor puramente sintético permanece compatível.
- Contexto pode ser materializado em outra máquina com os mesmos bytes portáteis,
  mas exige novo contexto e nova autorização independente; copiar documentos não
  concede outra tentativa.

## Plano de execução / ledger

1. Testes RED: separação, binding e mutações, sem acesso a inputs reais.
2. Contratos versionados e integração gate -> inputs -> execução -> publicação.
3. Migração das fixtures existentes, preservando os testes de fronteira.
4. Documentação técnica; revisão independente; correções com RED/GREEN.
5. Testes focados, Invoice, regressão completa, Ruff e diff-check.

Pre-flight: o gate produz recibo consumido pelo adaptador e executor; os quatro
documentos devem manter a mesma ordem de pins em todas as etapas e no manifesto.
Pre-flight: verificador de bundle deve usar somente os documentos do bundle,
sem reabrir datasets nem confundir integridade com aprovação humana.

Ruling: continuar no checkout atual autorizado, preservando mudanças preexistentes;
não criar commit, worktree adicional ou artefato definitivo. O custo é um diff que
precisa distinguir explicitamente as alterações anteriores das desta etapa.

## Revisão: foco

Bypass por cópia/alias, caminhos e destino, ausência de autorização, hashes não
vinculados, reexecução/sobrescrita, alteração entre estágios, acesso precoce a
inputs, compatibilidade e preservação de source_reconciled=false.

## Estado

Task 1: complete — RED: 24 falhas/1 aprovado, API de contexto ausente; GREEN: 25 aprovados.
Task 2: complete — RED: 2 integrações falharam por ausência de contexto; GREEN:
251 testes focados aprovados. Guardas: zero tentativas de acesso aos dados reais.
Task 3: complete — mais fronteiras e publicação: 111 testes aprovados.
Task 4: complete — revisão independente de código concluída; documentação atualizada.
Final: fixed P2 hashes dos inputs do bundle — quatro testes novos falharam por
DID NOT RAISE; correção exige oito nomes/digests e quatro identidades pré-acesso.
GREEN: 61 testes focados aprovados, zero acessos reais.
Task 5: complete — Invoice final: 667 aprovados, 8 skips (symlinks Windows), 160,35 s.
Regressão completa: 892 aprovados, mesmos 8 skips, 161,16 s.
Ambas: REAL_PROJECT_DATA_ACCESS_ATTEMPTS=0. Ruff: All checks passed.
Diff-check aprovado, incluindo novos arquivos. Nenhum commit/push ou emissão real.
Ruff inicial: um C410 na construção de lista, corrigido sem mudança semântica.

Ruling: contratos reais 1.2 não serão migrados automaticamente — evita
reaproveitar aprovações sem vínculo de contexto; custo: um futuro chamador antigo
deverá fornecer novo contexto e aprovação. API sintética legada preservada.
Ruling: TEST/raw têm hashes null no contexto — exigência de manter o conteúdo
fechado; custo: identidade pré-acesso desses conteúdos não é certificada.
O inventário anterior fica preservado como snapshot histórico, não como freeze
válido do código novo; nenhuma emissão real foi feita.

## Revisão independente e limites — 07/10/2026

Revisor independente encontrou somente o P2 acima; nenhum bypass concreto do gate
ou reexecução no modelo de filesystem cooperativo foi apontado. Correção verificada
por RED/GREEN; revisão foi estática, os testes foram executados pelo implementador.

Final: Ruling: somente freeze é portátil, não o bundle publicado — preservar
vínculo ao destino é parte do escopo mínimo; custo: auditoria dessa API requer
localização original do bundle. Esclarecido em docstring e documentação.
Final: Ruling: autenticação humana, custódia de pins e proteção contra operador
privilegiado permanecem externas — hashes são integridade, não assinatura;
custo: não há garantia contra fabricação de aprovação ou remoção deliberada de
estados por quem controla código/filesystem.
Final: Ruling: procedência científica e conteúdos reais não serão investigados
nesta tarefa — restrições do usuário; custo: source_reconciled=false e todas as
limitações históricas permanecem, sem novas evidências sobre independência.

Integridade: hashes dos dois notebooks Supplier, modelo, metadata, três JSONs
históricos e inventário de preparação conferidos e iguais ao baseline recebido.
Nenhum TEST/raw foi lido ou hasheado. Nada no staging; HEAD permanece 95fb8d1.
Arquivos fora do escopo e alterações locais preexistentes preservados.
