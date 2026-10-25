export interface SqlStateTransaction {
  $executeRaw(strings: TemplateStringsArray): PromiseLike<unknown>;
}

const expectedStates = new Set(['42501', '23503', '23505', '23514', '40001', '55000']);

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null
    ? (value as Record<string, unknown>)
    : undefined;
}

/** Extract numeric SQLSTATE classes used by this contract, never error text. */
export function sqlState(error: unknown): string | undefined {
  const failure = record(error);
  let code = failure?.code;
  if (code === 'P2010') {
    const meta = record(failure?.meta);
    const adapter = record(meta?.driverAdapterError);
    code = record(adapter?.cause)?.originalCode;
  }
  return typeof code === 'string' && /^[0-9]{2}[0-9A-Z]{3}$/.test(code)
    ? code
    : undefined;
}

/**
 * Run one future negative case inside an existing transaction. Await cases
 * sequentially and reserve this savepoint name for the helper. The caller must
 * propagate any helper failure so the outer transaction is rolled back.
 */
export async function rejectsSqlState(
  tx: SqlStateTransaction,
  operation: (tx: SqlStateTransaction) => Promise<unknown>,
  expected: string,
): Promise<void> {
  if (!expectedStates.has(expected)) {
    throw new Error('DB_TEST: unsupported expected SQLSTATE');
  }
  try {
    await tx.$executeRaw`SAVEPOINT db_test_negative`;
  } catch {
    throw new Error('DB_TEST: savepoint setup failed');
  }

  let problem: string | undefined;
  let cleanupFailed = false;
  try {
    let rejected = false;
    let actual: string | undefined;
    try {
      await operation(tx);
      await tx.$executeRaw`SET CONSTRAINTS ALL IMMEDIATE`;
    } catch (error) {
      rejected = true;
      actual = sqlState(error);
    }
    if (!rejected) problem = 'operation unexpectedly succeeded';
    else if (actual !== expected) problem = 'unexpected SQLSTATE';
  } catch {
    problem = 'unable to verify SQLSTATE';
  } finally {
    try {
      await tx.$executeRaw`ROLLBACK TO SAVEPOINT db_test_negative`;
    } catch {
      cleanupFailed = true;
    }
    try {
      await tx.$executeRaw`RELEASE SAVEPOINT db_test_negative`;
    } catch {
      cleanupFailed = true;
    }
  }
  if (cleanupFailed) throw new Error('DB_TEST: savepoint cleanup failed');
  if (problem) throw new Error(`DB_TEST: ${problem}`);
}
