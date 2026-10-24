# Backend offline CI implementation plan

> **For agentic workers:** Use `superpowers:executing-plans` for the tasks below. Do not stage, commit or push.

**Goal:** Validate the current NestJS + Prisma integration automatically without PostgreSQL, credentials or academic datasets.

**Architecture:** Add one independent Windows workflow, preserving `quality.yml` byte for byte. Install both lockfiles, build the root-generated Prisma Client and Nest backend, then run isolated checks. No database service or application startup.

**Tech Stack:** GitHub Actions, Windows 2025, PowerShell, Node 24.20.0, npm 11.14.0, existing Prisma/NestJS/TypeScript/Vitest/Oxlint dependencies.

**Spec:** User request in this task: implement backend offline CI, preserve existing work and the Python workflow, validate locally, distinguish local evidence from GitHub execution.

## Decisions and constraints

- Separate workflow instead of changing the Python job: independent failures and no change to scientific verification.
- Windows only initially: matches the validated environment and exercises junction protections without adding an unverified OS matrix.
- Trigger on push, pull request and manual dispatch; no path filters that could omit a required check.
- Pin Actions by commit, Node/npm exactly, and dependencies through the existing lockfiles.
- Disable dependency lifecycle hooks; retain optional native dependencies.
- Network may download tools, npm packages and Prisma engines. Offline means no database or business-data dependency, not an air-gapped runner.
- Work in the existing checkout because the integration is still uncommitted. Validate fresh installation in a separate temporary directory, copying only an explicit allowlist of infrastructure/backend files.
- No modifications to schema, migration, runtime implementation, dependencies or notebooks.

## Review focus

- Build must precede checks that import ignored generated clients.
- Root and backend lockfiles must both be installed; optional native binaries must remain available.
- Native-command failure must fail its workflow step; no silent continuation.
- No secrets, PostgreSQL services, migrations, database tests or application start commands.
- Generated artifacts must stay ignored; existing user edits must remain intact.

## Task 1 — CI definition and usage

**Files:** Create `.github/workflows/backend-quality.yml`; update only the CI section of `backend/README.md`.

- [x] Record the initial working tree and hashes of protected/preexisting files.
- [x] Add the independent workflow with pinned tools, read-only permissions, cancellation and timeout.
- [x] Run `npm ci --ignore-scripts --no-fund --no-audit` in both packages.
- [x] Check dependency trees, root contracts and Prisma schema without a database.
- [x] Build before backend unit/E2E/client checks, lint and no-emit TypeScript checking.
- [x] Document workflow boundaries and prerequisite uncommitted integration files.

## Task 2 — Local reproduction and review

**Files:** No production changes planned; record outcomes here.

- [x] Check workflow syntax and step ordering; review safety independently.
- [x] Reproduce installations and verification commands in a fresh temporary copy without datasets, `.env`, models or initial generated outputs.
- [x] Check for failures without weakening database/ML protections; none occurred.
- [x] Run `git diff --check`; compare baseline hashes and final status.
- [x] Report local results separately from GitHub Actions, which cannot be claimed without a real run.

## Execution record

- Initial HEAD: `a92e5ab`; staging empty; integration changes and two Supplier notebooks are preexisting.
- Scope ruling: no new persistent test framework for YAML or changes to application behavior; validate the configuration and execute its actual commands in isolation.
- Clean reproduction: 34 explicitly selected infrastructure/backend files copied to a temporary directory. Both `npm ci` operations passed with lifecycle hooks disabled; root and backend `npm ls --all` passed. All 34 copied source files remained unchanged after validation.
- Root checks: 5 static contract tests passed; `prisma validate` passed without a database URL.
- Backend checks: generation, ESM compilation and Nest build passed; 33 unit tests, 1 isolated E2E test and 12 Prisma tests passed (51 tests overall, no failures or skips). Lint including `scripts/` and no-emit TypeScript checking passed.
- Workflow checks: actionlint 1.7.12 passed; both multiline PowerShell blocks parsed without errors. No additional project dependency was installed for these checks.
- Preservation: 34 of 35 baseline files are byte-identical, including the Python workflow, Supplier notebooks, schema, migration and lockfiles. The only baseline change is the CI section in `backend/README.md`; removing that section in memory reproduces the original file hash. Staging remains empty. `git diff --check` passed; existing line-ending warnings were not normalized.
- Independent review: static review of workflow order, offline tests, package scripts and preservation boundaries found no concrete defect. This does not validate the GitHub runner itself.
- Not reproduced locally: hosted Actions checkout/setup/cache, global npm installation (the local toolchain already matches), and the clean-checkout Git guard. Local source preservation was checked by hashes instead; the working tree intentionally remains dirty. No GitHub run, database integration test or scientific verification was performed.
