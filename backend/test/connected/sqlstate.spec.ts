import { Socket } from 'node:net';

type Helpers = typeof import('./sqlstate.js');
type Transaction = import('./sqlstate.js').SqlStateTransaction;

const expectedStates = ['42501', '23503', '23505', '23514', '40001', '55000'];
const savepoint = 'SAVEPOINT db_test_negative';
const rollback = 'ROLLBACK TO SAVEPOINT db_test_negative';
const release = 'RELEASE SAVEPOINT db_test_negative';
const constraints = 'SET CONSTRAINTS ALL IMMEDIATE';

function mockTransaction(failures: Record<string, unknown> = {}) {
  const statements: string[] = [];
  const tx: Transaction = {
    async $executeRaw(strings) {
      const statement = strings.join('?');
      statements.push(statement);
      if (Object.hasOwn(failures, statement)) throw failures[statement];
      return 0;
    },
  };
  return { tx, statements };
}

describe('SQLSTATE helpers with mocked transactions and blocked network', () => {
  let helpers: Helpers;
  let networkAttempts: number;

  beforeEach(async () => {
    networkAttempts = 0;
    vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => {
      networkAttempts += 1;
      throw new Error('Offline network guard');
    });
    // Import the helper only after the socket guard is active.
    helpers = await import('./sqlstate.js');
  });

  afterEach(() => {
    try {
      expect(networkAttempts).toBe(0);
    } finally {
      vi.restoreAllMocks();
    }
  });

  it.each([...expectedStates, '42601', '25P02'])(
    'extracts the exact pg code %s without interpreting a message',
    (code) => {
      expect(helpers.sqlState({ code, message: 'unrelated 23514' })).toBe(code);
    },
  );

  it('extracts the installed Prisma P2010 adapter originalCode', () => {
    expect(
      helpers.sqlState({
        code: 'P2010',
        clientVersion: '7.10.0',
        meta: {
          driverAdapterError: {
            cause: {
              originalCode: '23514',
              originalMessage: 'synthetic sensitive detail',
              kind: 'postgres',
              code: '23514',
            },
          },
        },
      }),
    ).toBe('23514');
  });

  it.each([
    null,
    undefined,
    '23514',
    { message: 'SQLSTATE 23514' },
    { code: 'P2010' },
    { code: 'P2002' },
    { code: 23514 },
    { code: '23514 ' },
    { code: '25p02' },
    { code: 'P2010', meta: { code: '23514', message: '23514' } },
    { code: 'P2010', meta: { driverAdapterError: { cause: { code: '23514' } } } },
    { code: 'P2010', meta: { driverAdapterError: { cause: { originalCode: 'P2010' } } } },
    { meta: { driverAdapterError: { cause: { originalCode: '23514' } } } },
  ])('does not infer a SQLSTATE from unsupported error shapes (case %#)', (error) => {
    expect(helpers.sqlState(error)).toBeUndefined();
  });

  it.each(expectedStates)('accepts the exact expected operation SQLSTATE %s', async (expected) => {
    const { tx, statements } = mockTransaction();
    const operation = async (operationTx: Transaction) => {
      expect(operationTx).toBe(tx);
      statements.push('operation');
      throw { code: expected };
    };

    await expect(helpers.rejectsSqlState(tx, operation, expected)).resolves.toBeUndefined();
    expect(statements).toEqual([savepoint, 'operation', rollback, release]);
  });

  it('forces deferred constraints before accepting the expected Prisma SQLSTATE', async () => {
    const { tx, statements } = mockTransaction({
      [constraints]: {
        code: 'P2010',
        meta: { driverAdapterError: { cause: { originalCode: '23503' } } },
      },
    });

    await expect(
      helpers.rejectsSqlState(tx, async () => { statements.push('operation'); }, '23503'),
    ).resolves.toBeUndefined();
    expect(statements).toEqual([savepoint, 'operation', constraints, rollback, release]);
  });

  it('rejects unexpected success after checking deferred constraints and rolling back', async () => {
    const { tx, statements } = mockTransaction();

    await expect(
      helpers.rejectsSqlState(tx, async () => { statements.push('operation'); }, '23514'),
    ).rejects.toThrow(/^DB_TEST: operation unexpectedly succeeded$/);
    expect(statements).toEqual([savepoint, 'operation', constraints, rollback, release]);
  });

  it.each(['23505', '42601', '25P02', 'P2010', undefined])(
    'rejects a mismatched or missing SQLSTATE %s and cleans up',
    async (code) => {
      const { tx, statements } = mockTransaction();
      await expect(
        helpers.rejectsSqlState(tx, async () => { throw { code, message: 'secret 23514' }; }, '23514'),
      ).rejects.toThrow(/^DB_TEST: unexpected SQLSTATE$/);
      expect(statements).toEqual([savepoint, rollback, release]);
    },
  );

  it.each(['42601', '25P02', '22023', 'P2010', '', '23514 ', 'unknown']) (
    'rejects unsupported expected code %s before running any SQL',
    async (expected) => {
      const { tx, statements } = mockTransaction();
      const operation = vi.fn();
      await expect(helpers.rejectsSqlState(tx, operation, expected)).rejects.toThrow(
        /^DB_TEST: unsupported expected SQLSTATE$/,
      );
      expect(operation).not.toHaveBeenCalled();
      expect(statements).toEqual([]);
    },
  );

  it('does not accept a matching failure from SAVEPOINT creation', async () => {
    const { tx, statements } = mockTransaction({ [savepoint]: { code: '42501', message: 'secret' } });
    const operation = vi.fn();
    await expect(helpers.rejectsSqlState(tx, operation, '42501')).rejects.toThrow(
      /^DB_TEST: savepoint setup failed$/,
    );
    expect(operation).not.toHaveBeenCalled();
    expect(statements).toEqual([savepoint]);
  });

  it.each([rollback, release])('does not hide failure of %s after the expected rejection', async (failed) => {
    const { tx, statements } = mockTransaction({ [failed]: new Error('synthetic secret') });
    const error = await helpers.rejectsSqlState(tx, async () => { throw { code: '23514' }; }, '23514')
      .catch((failure: unknown) => failure);
    expect(error).toBeInstanceOf(Error);
    expect(String(error)).toBe('Error: DB_TEST: savepoint cleanup failed');
    expect(error).not.toHaveProperty('cause');
    expect(statements).toEqual([savepoint, rollback, release]);
  });

  it('reports cleanup failure even when the operation also failed unexpectedly', async () => {
    const { tx, statements } = mockTransaction({
      [rollback]: new Error('secret rollback'),
      [release]: new Error('secret release'),
    });
    await expect(
      helpers.rejectsSqlState(tx, async () => { throw { code: '42601', message: 'secret operation' }; }, '23514'),
    ).rejects.toThrow(/^DB_TEST: savepoint cleanup failed$/);
    expect(statements).toEqual([savepoint, rollback, release]);
  });
});
