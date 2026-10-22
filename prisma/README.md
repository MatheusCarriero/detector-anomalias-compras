# Primeiro incremento do banco operacional

PostgreSQL 18, Prisma ORM 7.10.0, schema `app`. Este incremento não é um pipeline
Purchase nem uma implantação dos modelos acadêmicos. Não há importador, seed,
API, autenticação, scoring ou acesso aos datasets.

## Estado da entrega

- Schema Prisma e migration foram preparados offline.
- A migration foi aplicada e validada no banco sintético identificado para esta entrega.
  Nesse ambiente foram criados os papéis `detector_migrator` e `detector_runtime`.
- `prisma validate`/`generate` validam a representação Prisma, não as invariantes SQL.
- Os testes de integração exigem PostgreSQL 18 e dois papéis identificados.
  A execução no ambiente sintético validou concorrência, SQL customizado e permissões.
- O incremento foi validado no banco sintético; isso não constitui implantação em produção.

O estado das verificações desta entrega consta do relatório da tarefa. Não
reutilizar uma contagem antiga de testes como comprovação de uma nova execução.

## Escopo físico

| Grupo lógico | Tabelas no schema `app` |
|---|---|
| Core | `currencies`, `departments`, `users`, `suppliers` |
| Procurement | `purchase_order_lines` |
| Audit | `source_identities`, `source_references`, `record_versions`, `decision_snapshots`, `snapshot_members`, `audit_events` |

São 11 tabelas de domínio. Quando Prisma Migrate for usado com uma URL que
seleciona `schema=app`, sua tabela técnica `_prisma_migrations` deverá ficar nesse
schema e ser conferida separadamente. Não representa uma 12ª entidade de negócio.

O bootstrap da migration aceita `app` ausente, vazio ou contendo somente a
tabela técnica do Prisma e seus objetos associados, sob o mesmo proprietário
da migração. Objetos de domínio preexistentes ou outro proprietário causam erro;
não são reaproveitados silenciosamente. O DDL fixa `search_path=app,pg_catalog`
na transação. Essa compatibilidade com o bootstrap ainda precisa ser exercitada
com `migrate deploy` no banco sintético identificado.

Não existem cabeçalhos de pedido, contratos, aprovações, catálogo de itens,
entregas, faturas, pagamentos ou tabelas ML. Uma linha pode existir sem fornecedor
ou departamento comprovados. Identificadores externos não são PKs internas.

### Estado operacional e versões

| Proprietário | Atributos escalares versionados | FKs versionadas separadamente |
|---|---|---|
| Supplier | `name`, `country_code`, `status`, `tier` | Nenhuma |
| Department | `name`, `code` | Nenhuma |
| Purchase line | `description`, `po_date`, `quantity`, `unit_price`, `amount` | `supplier_id`, `department_id`, `currency_id` |

Esses campos não mapeiam automaticamente o Excel. `po_date` é uma data civil,
não aprovação. Status/tier não possuem interpretação de risco. Não há fórmula
imposta entre quantidade, preço e montante, nem política de sinal/tributação
inventada. Nome é obrigatório nos cadastros; os campos de linha podem permanecer
ausentes. Campos desconhecidos não são ignorados silenciosamente.

`record_versions.payload_schema=1` define um objeto com os campos escalares
acima, inclusive chaves nulas. Decimais são strings canônicas com a escala da
coluna; datas civis usam `YYYY-MM-DD`. FKs ficam em colunas reais, fora do payload.
`id`, `current_version_id`, `created_at` e `updated_at` são campos técnicos.
`revision_no` existe apenas na versão.

As rotinas recebem a **substituição completa** do estado, não um patch. Um campo
opcional omitido vira NULL; a atualização exige o head esperado. Não há merge
silencioso ou retry automático. Correções criam nova versão, inclusive para
vigência: uma versão existente nunca é fechada por UPDATE.

### Interfaces SQL de escrita

Todas as funções estão em `app`. Não usar o CRUD gerado pelo Prisma para gravar
entidades versionadas: ele não substitui as transações abaixo.

```text
write_supplier(entity uuid, expected uuid, state jsonb, actor uuid,
               source uuid = NULL, valid_from text = NULL, valid_to text = NULL)
write_department(entity uuid, expected uuid, state jsonb, actor uuid,
                 source uuid = NULL, valid_from text = NULL, valid_to text = NULL)
write_purchase_order_line(entity uuid, expected uuid, state jsonb,
                          supplier uuid, department uuid, currency uuid, actor uuid,
                          source uuid = NULL, valid_from text = NULL, valid_to text = NULL)
→ TABLE(entity_id uuid, version_id uuid, revision_no integer)

register_source_identity(namespace text, kind text, external_id text, actor uuid) → uuid
resolve_source_identity(identity_id uuid, supplier uuid, department uuid, line uuid, actor uuid) → void
observe_source(namespace text, kind text, actor uuid, identity_id uuid = NULL,
               source_version text = NULL, record_key text = NULL, locator text = NULL,
               content_hash text = NULL, original_content jsonb = NULL, available_at text = NULL) → uuid

capture_line(line_id uuid, actor uuid) → uuid
seal_snapshot(snapshot uuid, actor uuid) → text (SHA-256)
```

Para criar, `entity` e `expected` são NULL. Para revisar, ambos são obrigatórios.
Os três writers usam UUIDs internos gerados pelo PostgreSQL e devolvem a nova
identidade/head. Os parâmetros `source`, `valid_from` e `valid_to` são opcionais
e não certificam disponibilidade histórica.

Identidade canônica: UNIQUE(namespace, kind, external_id), com tipo controlado
(`supplier`, `department`, `purchase_order_line`). Zero proprietários significa
não resolvida; exatamente um proprietário tipado significa resolvida. Não há
merge nem remapeamento de uma identidade resolvida. `source_references` registra
observações imutáveis; não cria outra identidade canônica.

Autoria é atribuída ao `actor` ativo informado pelo chamador; `session_user`
também é registrado. **Isso não implementa autenticação humana nem comprova
que a pessoa controlava a sessão.** Associação com JWT/identidade autenticada
pertence à futura aplicação. Não guardar tokens/senhas em conteúdo ou contexto.
O cadastramento inicial de usuários/moedas exige administração separada; não há
seed de pessoas reais ou catálogo inventado.

### Dinheiro e tempo

- Montantes: NUMERIC(24,6); preço unitário: NUMERIC(24,8); quantidade: NUMERIC(20,6).
- As rotinas recebem decimais em texto. Recusam NaN/infinito, números JSON,
  excesso de escala ou faixa **antes** do cast. Não converter para Number/float.
- Preço ou montante exige moeda; não há câmbio nem soma entre moedas diferentes.
  `currencies.code` tem três letras, mas isso sozinho não certifica ISO/semântica.
- Instantes recebidos são texto ISO com offset explícito e até três casas;
  datas civis são DATE. Não converter primeiro para JavaScript Date e só depois
  tentar detectar precisão perdida.
- Instantes gerados pelo servidor usam milissegundos. UUID não ordena eventos.
- Não existe alegação de disponibilidade pré-aprovação. Hash prova integridade
  dos bytes representados, não procedência empresarial ou temporal.

### Captura e selagem

Somente `purpose=record_capture`, uma raiz de linha e captura contemporânea.
`capture_line` exige READ COMMITTED, bloqueia linha → fornecedor → departamento,
obtém os heads sob locks e registra raiz/contextos que existem. Não cria relações
ausentes. `captured_at` e `knowledge_cutoff_at` são gerados pelo servidor.

Membros usam FKs compostas (versão, proprietário), XOR e unicidade. O root aponta
para um membro do mesmo snapshot. Alterações de membros e selagem compartilham
o lock do snapshot. `seal_snapshot` confere composição e calcula o hash antes de
atualizar estado e auditoria na mesma transação.

`snapshot/1` é SHA-256 do JSONB textual produzido pelo PostgreSQL 18, convertido
para UTF-8, com timezone UTC/DateStyle ISO, lista de membros ordenada por
role/UUID e versões completas. Inclui identidade, ator, corte e instante da
captura. Duas capturas distintas não precisam ter o mesmo hash. Não é um formato
de canonicalização JSON universal; uma mudança de formato exige nova versão.
`content_hash`, `sealed_at` e o estado final não entram recursivamente no hash.

Após selagem não há alteração/reabertura nem exclusão de evidências. Um draft
não é evidência selada nem pode ser apresentado como aprovação/scoring.

## Prisma × SQL

| Representação | Garantias |
|---|---|
| Prisma | 11 modelos, tipos/precisões, UUID, nulidade, PK, UNIQUE, relações/FKs compostas, índices normais e ações referenciais |
| SQL customizado | XOR/CHECKs, índices parciais dos membros, FKs diferidas de head/root, cadeia linear, comparação da projeção, auditoria por versão, parsers sem arredondamento silencioso, locks, selagem/hash e imutabilidade |
| Permissões PostgreSQL | Sem execução pública de funções nem DML público; implantação do papel runtime sem ownership e com allowlist de funções |

Não usar `db push`, `migrate reset` ou migração regenerada somente do schema para
substituir o SQL revisado. Prisma não descreve todas as invariantes. A migration
única contém BEGIN/COMMIT e não pode ser editada depois de aplicada. Correções
posteriores precisam de uma nova migration e revisão.

## Operação offline

Node 24, dependências locais fixadas e lockfile. Nenhum lifecycle do projeto
aplica migrations ou faz seed. Os comandos abaixo não conectam ao banco:

```powershell
npm.cmd ci --ignore-scripts --no-fund --no-audit
npm.cmd test
npm.cmd run db:validate
npm.cmd run db:generate
npm.cmd ls --all
```

O client gerado fica em `generated/prisma/`, ignorado pelo Git.
Não é um backend e não instancia conexão automaticamente.

## Antes de qualquer conexão

Parar e identificar host, porta, banco exclusivo, usuário de migração, papel da
aplicação, schema `app` e operação. Exibir **AGORA É NO POSTGRESQL** e o comando
exato antes de executá-lo. Não registrar senha em comandos compartilhados ou Git.
Não criar banco/role por inferência. Não aplicar em produção.

Depois dessa identificação, o comando de aplicação será:

```powershell
npm.cmd exec -- prisma migrate deploy
```

Ele usa `DATABASE_URL` fornecida externamente, com o banco identificado e
`schema=app`. A configuração não carrega `.env` automaticamente nem possui
alvo padrão. Não executar o comando acima antes da identificação.

O papel runtime deve ser distinto do migrador e não possuir SUPERUSER,
CREATEDB, CREATEROLE, BYPASSRLS, ownership do schema/tabelas/funções nem membership
no papel proprietário. Não usar um papel preexistente com grants desconhecidos.
Na etapa de implantação, conferir grants herdados/default ACLs: `REVOKE ... FROM
PUBLIC` não remove privilégios individuais preexistentes.

Conceder apenas USAGE no schema, leituras necessárias e EXECUTE nas oito
interfaces públicas listadas acima. Não conceder EXECUTE em helpers,
`internal_write_record` ou funções de trigger; nem INSERT/UPDATE/DELETE/TRUNCATE,
CREATE/ALTER ou poder de desativar triggers. Não usar `GRANT ... ON ALL FUNCTIONS`.
As funções públicas de escrita e os validadores diferidos usam SECURITY DEFINER
com referências qualificadas e search_path fixo; o proprietário é confiável.
Um administrador/proprietário pode alterar o esquema: não há proteção contra
um DBA que deliberadamente remova controles.

No ambiente sintético identificado para esta validação, os grants do papel
runtime foram aplicados e validados. Em um novo ambiente, esses grants continuam
sendo uma etapa explícita de implantação e devem ser concedidos somente após a
identificação do banco, do migrador e do papel runtime.

## Testes sintéticos no PostgreSQL

Os testes de integração não criam ou removem bancos. Exigem configuração
separada e recusam fallback para `DATABASE_URL`:

```text
DB_TEST_CONFIRM=synthetic-only
DB_TEST_HOST=<localhost, 127.0.0.1 ou [::1]>
DB_TEST_PORT=<porta explícita>
DB_TEST_DATABASE=<nome exclusivo começando com synthetic_>
DB_TEST_MIGRATOR=<usuário proprietário do incremento no banco de teste>
DB_TEST_RUNTIME=<usuário runtime distinto, com grants mínimos>
DB_TEST_MIGRATION_URL=<URL do migrador que corresponde exatamente ao alvo>
DB_TEST_RUNTIME_URL=<URL runtime que corresponde exatamente ao alvo>
```

URLs de teste não admitem parâmetros/redirecionamentos nem fragmentos. As
queries qualificam `app` explicitamente. Os papéis e a finalidade descartável
do banco ainda precisam ser confirmados por quem administra a instância;
prefixo e variáveis não substituem essa decisão.

Depois da identificação/anúncio, `npm.cmd run db:test` executará somente
`tests/database/*.integration.test.mjs`. Nenhum teste lê arquivos científicos.
Asserções negativas verificam SQLSTATE; constraints diferidas chegam a
`SET CONSTRAINTS ALL IMMEDIATE` ou COMMIT. Testes concorrentes abrem duas
conexões e observam locks reais.

Os casos preparados incluem as duas ordens de concorrência entre selagem e
INSERT/UPDATE/DELETE de membros ou mudança da raiz, além de captura versus
nova versão de linha/fornecedor/departamento. A verificação do papel runtime
inspeciona ACLs efetivas de tabelas, colunas e funções e tenta captura/selagem
pelas interfaces permitidas. O caso de rollback injeta uma falha de auditoria
depois da escrita da versão e da projeção; a função/trigger de teste é revertida
na mesma transação. Esses cenários foram executados e validados no banco sintético.

Casos com COMMIT deixam fixtures claramente sintéticas no banco exclusivo.
Não contornar imutabilidade com DELETE/TRUNCATE para limpeza. Descarte desse
banco é uma operação futura explícita, nunca um teardown automático.

## Limites atuais

Purchase continua sem modelo/target aprovado. Invoice e Supplier acadêmicos não
foram importados nem executados. O incremento não escolhe regras de risco,
políticas de alerta, câmbio, metas de desempenho ou critérios de aprovação.

Testes SQL, concorrência e permissões foram executados no PostgreSQL 18 e
passaram integralmente no banco sintético. A infraestrutura deste incremento
foi validada nesse ambiente. A simples existência desta migration e um
`prisma validate` bem-sucedido não bastam para caracterizar uma implantação
em produção.
