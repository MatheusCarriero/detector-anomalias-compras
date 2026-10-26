<p align="center">
  <a href="http://nestjs.com/" target="blank"><img src="https://nestjs.com/img/logo-small.svg" width="120" alt="Nest Logo" /></a>
</p>

[circleci-image]: https://img.shields.io/circleci/build/github/nestjs/nest/master?token=abc123def456
[circleci-url]: https://circleci.com/gh/nestjs/nest

  <p align="center">A progressive <a href="http://nodejs.org" target="_blank">Node.js</a> framework for building efficient and scalable server-side applications.</p>
    <p align="center">
<a href="https://www.npmjs.com/~nestjscore" target="_blank"><img src="https://img.shields.io/npm/v/@nestjs/core.svg" alt="NPM Version" /></a>
<a href="https://www.npmjs.com/~nestjscore" target="_blank"><img src="https://img.shields.io/npm/l/@nestjs/core.svg" alt="Package License" /></a>
<a href="https://www.npmjs.com/~nestjscore" target="_blank"><img src="https://img.shields.io/npm/dm/@nestjs/common.svg" alt="NPM Downloads" /></a>
<a href="https://circleci.com/gh/nestjs/nest" target="_blank"><img src="https://img.shields.io/circleci/build/github/nestjs/nest/master" alt="CircleCI" /></a>
<a href="https://discord.gg/G7Qnnhy" target="_blank"><img src="https://img.shields.io/badge/discord-online-brightgreen.svg" alt="Discord"/></a>
<a href="https://opencollective.com/nest#backer" target="_blank"><img src="https://opencollective.com/nest/backers/badge.svg" alt="Backers on Open Collective" /></a>
<a href="https://opencollective.com/nest#sponsor" target="_blank"><img src="https://opencollective.com/nest/sponsors/badge.svg" alt="Sponsors on Open Collective" /></a>
  <a href="https://paypal.me/kamilmysliwiec" target="_blank"><img src="https://img.shields.io/badge/Donate-PayPal-ff3f59.svg" alt="Donate us"/></a>
    <a href="https://opencollective.com/nest#sponsor"  target="_blank"><img src="https://img.shields.io/badge/Support%20us-Open%20Collective-41B883.svg" alt="Support us"></a>
  <a href="https://twitter.com/nestframework" target="_blank"><img src="https://img.shields.io/twitter/follow/nestframework.svg?style=social&label=Follow" alt="Follow us on Twitter"></a>
</p>
  <!--[![Backers on Open Collective](https://opencollective.com/nest/backers/badge.svg)](https://opencollective.com/nest#backer)
  [![Sponsors on Open Collective](https://opencollective.com/nest/sponsors/badge.svg)](https://opencollective.com/nest#sponsor)-->

## Description

[Nest](https://github.com/nestjs/nest) framework TypeScript starter repository.

## Project setup

```bash
$ npm install
```

## Compile and run the project

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
database identity. Those checks remain part of a later, explicitly controlled
connection to the synthetic database. TLS deployment configuration is outside
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
| `DB_TEST_OPERATION` | Exactly `identity-read-only` |

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
ownership or membership graph. Those checks remain part of the next stage,
before any fixture or write. No HTTP server or endpoint is started.

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

## Deployment

When you're ready to deploy your NestJS application to production, there are some key steps you can take to ensure it runs as efficiently as possible. Check out the [deployment documentation](https://docs.nestjs.com/deployment) for more information.

If you are looking for a cloud-based platform to deploy your NestJS application, check out [Mau](https://mau.nestjs.com), our official platform for deploying NestJS applications on AWS. Mau makes deployment straightforward and fast, requiring just a few simple steps:

```bash
$ npm install -g @nestjs/mau
$ mau deploy
```

With Mau, you can deploy your application in just a few clicks, allowing you to focus on building features rather than managing infrastructure.

## Observability

In production applications, observability is essential for understanding how your system behaves, detecting issues early, and maintaining reliable performance.

[NestJS Observe](https://observe.nestjs.com) automatically instruments your NestJS application, giving you deep visibility into your system with minimal setup:

- **Distributed tracing:** Follow requests across services and understand how they flow through your system.
- **Waterfall analysis:** Visualize request execution and identify slow operations, bottlenecks, and unexpected delays.
- **Performance analysis:** Analyze application performance in real time and quickly pinpoint areas that need optimization.
- **Metrics:** Track key application and infrastructure metrics to understand system health and performance trends.
- **Logging:** Centralize and correlate logs with traces and other telemetry to make debugging easier.
- **Error tracking:** Detect errors quickly and investigate their root causes with the surrounding context.
- **SLA monitoring:** Track service-level objectives and identify when your application is approaching or exceeding defined thresholds.
- **Alarms and alerts:** Set up alerts for critical errors, performance degradation, SLA violations, and other anomalies so your team can react quickly.

To add it to this project, run this and approve the code it prints at [observe.nestjs.com/link](https://observe.nestjs.com/link) - signing up for free if you have no account:

```bash
$ npx @nestjs/observe link
```

It installs `@nestjs/observe`, wires it into `AppModule` and `main.ts`, and writes the app key and secret into `.env`, which every `nest start` script (`start`, `start:dev`, `start:debug`) then loads. In production, set `OBSERVE_APP_KEY` and `OBSERVE_APP_SECRET` in the environment instead.

Or do it by hand:

```bash
$ npm install @nestjs/observe
```

Then follow the [setup guide](https://docs.nestjs.com/observability/sdk) - it takes a single import and an app key.

The free plan needs no payment details and covers 300,000 events a month. You can also browse the [live demo](https://www.observe-demo.nestjs.com/dashboard) first - the whole dashboard over a busy service's data, with nothing to install.

## Resources

Check out a few resources that may come in handy when working with NestJS:

- Visit the [NestJS Documentation](https://docs.nestjs.com) to learn more about the framework.
- For questions and support, please visit our [Discord channel](https://discord.gg/G7Qnnhy).
- To dive deeper and get more hands-on experience, check out our official video [courses](https://courses.nestjs.com/).
- Deploy your application to AWS with the help of [NestJS Mau](https://mau.nestjs.com) in just a few clicks.
- Auto-instrument your application with [NestJS Observe](https://observe.nestjs.com). Distributed tracing, metrics, and logging made easy. Error tracking and performance monitoring for your NestJS applications.
- Visualize your application graph and interact with the NestJS application in real-time using [NestJS Devtools](https://devtools.nestjs.com).
- Need help with your project (part-time to full-time)? Check out our official [enterprise support](https://enterprise.nestjs.com).
- To stay in the loop and get updates, follow us on [X](https://x.com/nestframework) and [LinkedIn](https://linkedin.com/company/nestjs).
- Looking for a job, or have a job to offer? Check out our official [Jobs board](https://jobs.nestjs.com).

## Support

Nest is an MIT-licensed open source project. It can grow thanks to the sponsors and support by the amazing backers. If you'd like to join them, please [read more here](https://docs.nestjs.com/support).

## Stay in touch

- Author - [Kamil Myśliwiec](https://twitter.com/kammysliwiec)
- Website - [https://nestjs.com](https://nestjs.com/)
- Twitter - [@nestframework](https://twitter.com/nestframework)

## License

Nest is [MIT licensed](https://github.com/nestjs/nest/blob/master/LICENSE).
