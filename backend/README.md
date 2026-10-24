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
