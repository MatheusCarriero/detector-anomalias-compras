# Runtime catalog inspection — Stage 2

Goal: prepare a separate runtime-only, read-only PostgreSQL 18 inspection. No
connection, SQL execution, grants, migrations or publication in this task.

Architecture: reuse the Nest/Prisma lifecycle and bounded transaction. Validate
identity in the same transaction before catalog reads. A distinct operation and
suite select only fixed catalog queries. Compare their results with the existing
migration, including SQL invariants absent from Prisma. Fail with fixed codes.

Implementation sequence:

- Add offline tests for suite/operation binding and refusal before construction.
- Add a pinned, read-only description of the initial migration and conservative
  comparison of CHECK expressions (preserving boolean grouping).
- Check effective runtime privileges, role reachability, ownership, function
  signatures/properties/bodies, table columns, constraints, indexes and triggers.
- Inspect future default ACLs separately from existing object ACLs.
- Add mocked catalog results and mutation tests, preserving existing diagnostics.
- Run unit tests, Prisma offline tests, lint, TypeScript and full build. Review
  diff and protected-file hashes. Never run connected commands in this task.

Review focus: missing/extra objects; overloads; inherited/SET ROLE and grant-option
escapes; disabled/not-valid constraints and triggers; wrong expression grouping;
unsafe default ACLs; identity failure before catalogs; SQL/query errors must not
be mistaken for an expected rejection or silently skipped.

Known issue to inspect, not repair: a per-schema default REVOKE does not remove
PostgreSQL's global default PUBLIC EXECUTE. Current functions have a separate
REVOKE; the owner's global/per-schema default ACLs require a separate check.

Runtime catalog inspection cannot certify DBA trust, secret configuration,
concurrency behavior or future objects created by other roles. Administrative
inspection and any permission correction remain separate authorized tasks.
