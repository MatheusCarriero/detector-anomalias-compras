# Backend — NestJS + Prisma

Infraestrutura TypeScript/ESM do Detector Inteligente de Anomalias em Compras.
O backend possui integração Prisma e testes offline/controle de acesso ao banco
sintético. Não há serviços de inferência dos modelos acadêmicos nem endpoints
de negócio implementados nesta etapa.

## Preparação local

Use Node 24 e npm 11; as versões da CI estão fixadas no
[workflow offline](../.github/workflows/backend-quality.yml). Em PowerShell,
partindo da raiz do repositório:

```powershell
npm.cmd ci --ignore-scripts --no-fund --no-audit
npm.cmd --prefix backend ci --ignore-scripts --no-fund --no-audit
```

Não é necessário configurar credenciais para gerar o client, compilar ou executar
os testes offline. Iniciar a aplicação e executar testes conectados são operações
separadas, sujeitas às restrições descritas abaixo.

## Build e integração Prisma

### Prisma Client preparation (no database connection)

The Prisma CLI, schema and migrations remain in the repository root. Install
the root and backend dependencies before preparing the client. From `backend/`:

```powershell
npm.cmd run prisma:prepare
npm.cmd run prisma:test
npm.cmd run build
```

`prisma:prepare` runs the root `db:generate` script with npm lifecycle hooks
disabled, then uses the backend's TypeScript compiler and `tsconfig.prisma.json`.
It compiles `../generated/prisma/` to ESM JavaScript and declarations in
`backend/generated/prisma/`, rewriting relative `.ts` imports to `.js`.
Only that compiled output is cleaned. Existing source and output directories
are checked before generation; symbolic links/junctions, linked source children
and unexpected generated assets cause preparation to fail. Neither generated directory is
versioned. No `DATABASE_URL`, migration, seed or database connection is needed.

Generation or source-validation failure leaves any previously compiled client
untouched, but returns a failure and stops the build. Do not treat that retained
client as the result of a successful new build. Compilation failure removes
partial compiled output. Run preparation exclusively, without concurrent writes
to either generated directory; these checks are not a filesystem sandbox.

`build` prepares the client before compiling Nest. The compiled client remains
outside `dist/`, so Nest's output cleanup does not remove it. A future deployment
must include `generated/prisma/` alongside `dist/`, the backend package manifest
and its runtime dependencies. Future services must import the compiled `.js`
entry, not the root's generated TypeScript.

`prisma:test` covers preparation with temporary synthetic fixtures, imports the
real compiled client and checks its constructor with the real PostgreSQL adapter
in separate Node processes. Socket connections are blocked; no `$connect` or
query is executed. Run preparation before this test command.

### Prisma runtime integration

`AppModule` imports a non-global `PrismaModule`, which exports `PrismaService`.
A replaceable `PRISMA_CLIENT` factory constructs the compiled client with
`PrismaPg` and the explicit SQL schema `app`. The service owns the connection
lifecycle; it does not expose domain CRUD or a public raw client. Future writes
must use the authorized SQL functions documented in [the database guide](../prisma/README.md),
not direct Prisma mutations of versioned entities.

At runtime, supply `DATABASE_URL` through the process environment. This module
does not load `.env` or import the root's `prisma.config.ts`. The URL must specify
a PostgreSQL host, port, database, nonempty password and the user
`detector_runtime`. Only the optional query parameter `schema=app` is accepted;
other parameters and duplicates are rejected. The factory passes explicit
connection fields to the adapter, with a fixed `search_path=app,pg_catalog`, so
URL parameters and `PGOPTIONS` cannot replace the intended role or search path.
Errors do not include the URL, password or original driver error.

This checks the intended configuration, not the role's actual grants or the
database identity. Those checks belong to explicitly controlled connections to the synthetic
database; startup alone cannot replace them. TLS deployment configuration is outside
this initial increment; URL-based TLS options are not currently accepted.
The provider does not set `ssl`, so `pg` inherits `PGSSLMODE` (or its default of
no TLS). This includes the insecure `no-verify` mode if supplied externally.
An explicit TLS/certificate policy is required before nonlocal deployment;
the current URL validation does not establish that transport guarantee.

`onModuleInit` awaits `$connect`; `onModuleDestroy` awaits `$disconnect`.
Failed startup attempts cleanup without retrying, and bootstrap enables Nest
shutdown hooks. If HTTP listening fails, bootstrap awaits application cleanup;
a cleanup failure does not replace the original startup error. In this adapter
version, `$connect` initializes a lazy pool;
successful startup alone does not prove PostgreSQL connectivity or permissions.
Starting the application enables its real database lifecycle, so do not use
`start` as an offline verification. No migration or seed is run during bootstrap.

Unit tests replace the adapter/client or the provider and block sockets; E2E
replaces the provider before initialization and blocks real adapter construction.
They need no real `DATABASE_URL`. Preparation, build and the validations for
this increment do not start the real application or connect to PostgreSQL.

```bash
# development
$ npm run start

# watch mode
$ npm run start:dev

# production mode
$ npm run start:prod
```

## Run tests

### Controlled PostgreSQL validation — Stage 0

Stage 0 prepares the connected test harness and verifies its protections offline.
It does not validate a live database. Ordinary `test`, `test:e2e`, `prisma:test`
and the offline CI do not collect `*.integration.test.ts`. The new guard tests
run as unit tests, with synthetic configuration, mocked drivers/processes and
blocked sockets. To run only those offline checks:

```powershell
npm.cmd run test:connected:offline
```

The separate `test:runtime:read` command is reserved for a later, explicitly
approved connection. Do not run it as an offline check. Its runner validates
configuration before launching Vitest; the connected configuration and harness
check it again before constructing the existing `AppModule`/`PrismaModule`.
There is no fallback to `DATABASE_URL`, `.env`, an owner role or a default target.
The internal runner marker prevents accidental direct invocation; it is not an
authorization token or a sandbox against deliberately modified test code.

Required environment settings for that later stage are:

| Setting | Requirement |
|---|---|
| `DB_TEST_CONFIRM` | `synthetic-only` |
| `DB_TEST_HOST` | Literal loopback: `127.0.0.1` or `[::1]`; no DNS/remote host |
| `DB_TEST_PORT` | Explicit port, 1–65535 |
| `DB_TEST_DATABASE` | Exclusive, administrator-confirmed synthetic database; `synthetic_` prefix, at most 63 characters |
| `DB_TEST_RUNTIME` | Exactly `detector_runtime` |
| `DB_TEST_RUNTIME_URL` | Matching PostgreSQL URL, nonempty password, no query parameters or fragment |
| `DB_TEST_TLS` | Explicit `local-plaintext` acknowledgement, for this loopback-only profile |
| `DB_TEST_OPERATION` | `identity-read-only` for identity; `catalog-read-only` for the separate Stage 2 inspection |

The prefix and flags validate intent, not the actual contents or ownership of a
database. Confirm the target and the local transport policy with its administrator
before Stage 1. Verified TLS/remote targets are not supported by this harness;
they require a separately reviewed configuration. Ambient `PG*`, database URLs,
owner credentials, debug/preload settings and CI execution are refused. The
runner forwards only the required target and a small OS environment allowlist.
Secrets are never command-line arguments. Do not print or commit them.

The prepared identity test uses the real Nest provider, without overriding it,
inside a read-only transaction. It checks `session_user`, `current_user`, database,
server address/port, PostgreSQL 18, `search_path`, schema USAGE/CREATE, role flags
and transport. It does not claim to validate the full table/column/function ACL,
ownership or membership graph. The separate Stage 2 inspection below covers
those contracts before any fixture or write. No HTTP server or endpoint is started.

Only one harness invocation/worker is allowed at a time, without retries.
The runtime provider's pool settings are unchanged (the installed `pg` default
allows ten clients); this read-only test requests one transaction and does not
exercise pool capacity. Prisma's acquisition `maxWait` is set to 3 seconds and
transaction timeout to 10 seconds; server statements are limited to 5 seconds
and locks to 2 seconds. Cleanup has a
3-second deadline. A separate 45-second process deadline also bounds lazy
connection/startup failures: Vitest uses a single thread worker, so terminating
its owned Node process terminates that worker. `SIGINT`/`SIGTERM` use the same
failure/termination path. Confirmation has a further 5-second
limit; if the OS does not confirm termination, the runner detaches only its own
child, fails and requests manual inspection. It cannot guarantee OS-level cleanup
in that case. A timeout/failed termination is failure, never proof of graceful
cleanup or rollback. A cleanup failure prevents
reuse of the harness in that process. Node/Nest errors are sanitized, and the
runner does not forward raw child output containing potential driver details.

`test:runtime:contracts` and `test:runtime:concurrency` are separate reserved
entry points that fail before spawning a process. They are not passing placeholder
tests. Future cases belong respectively in `test/connected/sql-contracts/` and
`test/connected/concurrency/`, with `*.integration.test.ts` names, after separate
review/authorization. Writes must use the SQL functions in the database guide;
no direct CRUD, seed, grants or fixture creation is introduced here.

The offline-tested SQLSTATE helper supports exact PostgreSQL codes and the
installed Prisma adapter's structured error shape. It refuses syntax errors,
aborted-transaction errors and unexpected success as evidence of a legitimate
rejection. Each future negative case uses its own savepoint, forces deferred
constraints and rolls back/releases the savepoint before the next case. Propagate
cleanup failures to the outer transaction. Actual Prisma error mapping, privileges,
SQL invariants, concurrency and cleanup on a real server remain unverified by
Stage 0. The legacy root `db:test` suite connects and can persist synthetic
fixtures; it is not part of this offline workflow.

### Controlled PostgreSQL validation — Stage 2

`test:runtime:catalog` selects `catalog-permissions/*.integration.test.ts` with
`DB_TEST_OPERATION=catalog-read-only`. A mismatched operation/suite is refused
before spawning or constructing the adapter. Ordinary tests, E2E and offline CI
still exclude these connected files. No database access is needed to run the
new `*.spec.ts` tests: they use artificial catalog projections and block sockets.

The inspection reuses the Nest/Prisma lifecycle, identity checks and existing
timeouts. In one `READ COMMITTED`, `READ ONLY` transaction, identity is verified
before eight fixed catalog SELECTs. No business records or `app` functions are
executed. The eight authorized function signatures must be executable; helpers,
overloads, grant options, ownership and role membership/SET paths must not grant
extra runtime powers. Direct table/column writes, schema creation and the ability
to set `session_replication_role` are rejected. The session must use `origin`.
Table SELECT access is not required across all eleven tables: this catalog-only
inspection does not invent a blanket business-read grant. Database TEMP access
is not prohibited by the migration; it is not treated as permission to write
application tables or create fixtures here.

The reviewed migration is read as text and pinned by its SHA-256 after LF
normalization. It is never applied. The comparison covers eleven tables and their
columns/defaults, 26 functions (eight authorized entry points), 32 foreign keys,
13 CHECKs, 52 indexes including PKs, and 30 user triggers. It includes deferred
composite FKs, internal FK triggers, PG18 NOT NULL validation, partial uniqueness,
function arguments/results/defaults/bodies, SECURITY DEFINER and search_path.
Only known CHECK/default deparser equivalents are normalized; unsupported syntax
fails closed. A migration change requires reviewing this test contract explicitly.
The optional Prisma migration bookkeeping table is excluded from the domain
manifest, but its ownership and prohibited runtime privileges are still checked.

Diagnostics remain fixed codes: `CATALOG_ROLES`, `CATALOG_RELATIONS`,
`CATALOG_FUNCTIONS`, `CATALOG_COLUMNS`, `CATALOG_CONSTRAINTS`, `CATALOG_INDEXES`,
`CATALOG_TRIGGERS` and `CATALOG_DEFAULT_ACL`. They identify the inspection that
failed, not a disclosed object/value. Valid boolean default-ACL projections now
distinguish `CATALOG_DEFAULT_ACL_FUNCTIONS`, `CATALOG_DEFAULT_ACL_TABLES` and
`CATALOG_DEFAULT_ACL_BOTH`; malformed projections use `CATALOG_RESULT_SHAPE`.
`CATALOG_DEFAULT_ACL` remains the query-stage code. Query errors also use the existing
`TX_ERROR_*` categories; a syntax or access error is never accepted as a successful
permission rejection. No rows, SQL bodies, URLs, credentials or driver messages
are printed. Failure stops subsequent inspections and requests bounded cleanup.

**Known default-privilege caveat:** the migration revokes PUBLIC EXECUTE from
existing functions. Its per-schema default REVOKE alone cannot remove PostgreSQL's
global default PUBLIC EXECUTE for future functions. The final inspection combines
the owner's global defaults (or built-in fallback) with schema defaults, including
future table privileges. `CATALOG_DEFAULT_ACL` can therefore refuse a database
whose current eight entry points are otherwise correct. This is a separate
future-object risk, not evidence that existing routines are currently public.
Any owner-level default-ACL correction needs a separate administrative review
and explicit authorization; do not change the migration or weaken the check to
obtain a pass. See [PostgreSQL 18 ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/18/sql-alterdefaultprivileges.html).

Default privileges belong to the role actually creating the object, not to its
inherited roles. The migration requires its effective role to own `app`, but this
does not establish the identity of future creators or rule out later ownership
changes. A separate administrative review must confirm each creator, inspect
global and schema grants, and assess the impact on other schemas in the same
database before proposing a global REVOKE. Schema grants may need separate
revocation. Existing-function ACLs remain a separate concern. The all-true offline
fixture represents hardened defaults; it does not certify the migration alone.

Offline mocks and static review do not prove server permissions, SQL execution
or the server's exact deparser representation. The runtime catalog also cannot
certify the identity/trust of the administrative owner, future objects created
by other roles, privileges outside this application's scope, or concurrent DDL.
Plan the future inspection without concurrent grants/DDL. If catalog access is
denied, record the sanitized failure and request a separate administrator's
read-only inspection; never use administrative credentials in this harness.
Function behavior, rejection SQLSTATEs and concurrency still need their separate,
future write-test stages. Metadata inspection does not prove those behaviors.

Future procedure, **only after separate authorization**:

1. Confirm the exclusive synthetic database, PostgreSQL 18, literal loopback,
   runtime role and local-plaintext policy. Confirm no concurrent DDL/grants.
2. Supply the existing required `DB_TEST_*` settings through the secure process
   environment, including its matching runtime URL; do not print credentials,
   store them in files or pass them as command-line arguments. Remove conflicting
   settings according to the gate above. Do not set the internal runner marker.
3. In `backend/`, select and run only the catalog inspection:

   ```powershell
   $env:DB_TEST_OPERATION = 'catalog-read-only'
   npm.cmd run test:runtime:catalog
   ```

4. Require exit code zero and the runner's completion message. A failure or
   timeout is not partial approval; preserve only sanitized diagnostics for
   review. Do not retry automatically, grant privileges, alter objects or advance
   to contracts/concurrency tests. Clear the temporary credential environment.

#### Safe connected-test diagnostics

The runner reports fixed categories instead of forwarding Vitest/driver output.
Configuration failures distinguish `CONFIG_MISSING`, `CONFIG_CONFLICT`,
`CONFIG_TARGET` and `CONFIG_URL`. Child failures identify module import/compilation,
initialization, transaction boundaries/setup, identity query/validation and cleanup.
For example, `IDENTITY_SCHEMA` means a schema check failed; it does not print the
returned value. A primary failure and a cleanup failure are reported separately.

`TRANSACTION_START` is the last boundary before the interactive callback, not proof
of an acquisition failure. With Prisma 7.10 / adapter-pg, `$connect()` initializes
the adapter/pool without necessarily opening a physical connection. The first
`$transaction` then acquires a connection, sends `BEGIN` and sets the isolation
level before invoking the callback. The public API does not expose separate
hooks for these three operations; the harness does not patch driver internals.

| Diagnostic stage | What has been reached |
| --- | --- |
| `TRANSACTION_START` | `$transaction` requested; callback not yet entered. Acquisition, `BEGIN`, isolation setup or a client-side startup failure remain possible. |
| `TRANSACTION_CALLBACK` | Interactive callback entered. No harness SQL has run yet. |
| `READ_ONLY_SETUP` | Awaiting `SET TRANSACTION READ ONLY`. |
| `SESSION_TIMEOUT_SETUP` | Applying the three existing local SQL timeouts. |
| `IDENTITY_QUERY` | Awaiting the identity query and its decoding. |
| `TRANSACTION_FINISH` | Callback completed; awaiting transaction completion/release. |
| `TRANSACTION_RESOLVED` | `$transaction` resolved; identity validation and module cleanup still follow. |

A transaction rejection also reports an allowlisted `TX_ERROR_*` category from
structured Prisma/adapter fields. This is separate from the stage. For example,
`TX_ERROR_API` maps Prisma `P2028`, which covers multiple transaction API failures
and is **not proof of a startup timeout**. `TX_ERROR_UNREACHABLE`,
`TX_ERROR_AUTHENTICATION`, `TX_ERROR_CONNECTION_CLOSED` and `TX_ERROR_CONNECTION_LIMIT`
are emitted only when the structured code/kind supports them. PostgreSQL `57014`
maps to `TX_ERROR_CANCELLED` (not necessarily a timeout); `55P03` maps to
`TX_ERROR_LOCK_UNAVAILABLE` (also possible with NOWAIT), `25006` to
`TX_ERROR_READ_ONLY`, and `42601` to `TX_ERROR_SQL_SYNTAX`. Unknown errors remain
`TX_ERROR_UNKNOWN`; their messages are never used to guess a cause. The classifier
reads only own data properties, without invoking getters or copying error text.

A local validator refusal also rejects the transaction promise. The harness
recognizes its own diagnostic errors by object identity and does not classify
them a second time as `TX_ERROR_UNKNOWN`. External errors, including ones with a
forged diagnostic field, still receive the bounded transaction classification.
This distinction does not certify rollback or cleanup; cleanup failures continue
to be reported separately and prevent reuse of the harness.

Limits remain unchanged: `maxWait=3000ms` covers adapter transaction startup
(acquisition plus `BEGIN`/isolation), and `timeout=10000ms` covers the running
interactive transaction. SQL statement/lock/idle-in-transaction limits are
5s/2s/5s and take effect only after their `SET LOCAL` succeeds. They do not protect
acquisition or `BEGIN`. The provider leaves pg's pool defaults unchanged
(maximum 10 clients, 10s idle timeout, no explicit acquisition/connection timeout).
The module cleanup bound is 3s, the Vitest test budget is 15s and the runner bound
is 45s, followed by up to 5s to confirm forced termination. These are nested
limits: 3s startup + 10s transaction + 3s cleanup already exceeds the test budget,
before module initialization. They are not additive allowances or proof of the
cause of a particular failure, and were not increased to mask this incident.

An expired `maxWait` does not prove pg stopped acquiring a connection. Offline
fixtures cover late acquisition followed by Prisma's rollback/release, as well
as acquisition, `BEGIN`, isolation, read-only setup, query and commit failures.
They use the real client/adapter with simulated pg I/O and blocked sockets.
These tests do not establish what occurred in a real failed attempt or certify
its cleanup. The harness still refuses reuse after an observed cleanup failure.

Endpoint failures distinguish `IDENTITY_ADDRESS_TYPE` / `IDENTITY_PORT_TYPE`
(unexpected JavaScript type, including null) from `IDENTITY_ADDRESS_VALUE` /
`IDENTITY_PORT_VALUE` (a value that does not exactly match the approved target).
The query uses `pg_catalog.host(inet_server_addr())`: PostgreSQL's explicit
`inet::text` cast includes a netmask, whereas `host(inet)` returns the address
alone ([PostgreSQL 18 reference](https://www.postgresql.org/docs/18/functions-net.html)).
No returned value is printed or coerced; masked addresses, numeric strings,
different addresses and different ports remain rejected.

Only exact, allowlisted `DB_TEST_DIAGNOSTIC_V1` frames cross the stderr boundary;
raw text, URLs, passwords, stack traces and malformed/oversized lines are discarded.
`CHILD_BOOTSTRAP` means the process failed before emitting a recognized diagnostic,
not proof of a particular loader error. Timeouts/signals include the last known
safe stage when available. `CHILD_TERMINATION_UNCONFIRMED` still requires manual
inspection; it is not proof that resources closed.

These categories locate a failure but do not certify its underlying cause or
authorize another connection. After a failed controlled run, share only the fixed
codes, review the indicated stage and obtain authorization before retrying. Do not
enable raw driver/debug output, relax identity checks or use an owner credential.

### Offline CI

[Backend Quality (offline)](../.github/workflows/backend-quality.yml) runs on
pushes, pull requests and manual dispatches, independently of the existing
Python `Quality` workflow. It uses Windows 2025, Node 24.20.0 and npm 11.14.0.

Both root and backend dependencies are installed with `npm ci --ignore-scripts`
from their lockfiles. Lifecycle hooks stay disabled throughout the job; optional
native packages remain enabled. The cache contains npm downloads, not
`node_modules` or generated clients.

After dependency checks and the root's static database contracts/schema
validation, the job builds the client and NestJS before running unit tests,
isolated E2E tests, `prisma:test`, lint (including `scripts/`) and a no-emit
TypeScript check including tests. It also rejects changes to versioned files
or newly generated files that are not ignored.

No PostgreSQL service, database credentials, migration, seed, academic dataset
or ML evaluation is used. Downloads of Node/npm, packages and Prisma engine
binaries still require network access: offline here means independent of the
database and business data, not an air-gapped runner. E2E uses local HTTP with
the database provider replaced.

A clean checkout needs all integration sources/configuration and both updated
lockfiles committed together with this workflow; ignored generated clients
must not be committed. Local validation is not evidence of a successful
GitHub Actions run. After publication, inspect the real run before requiring
its check in branch protection.

```bash
# unit tests
$ npm run test

# e2e tests
$ npm run test:e2e

# test coverage
$ npm run test:cov
```
