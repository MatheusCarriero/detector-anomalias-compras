import { Socket } from 'node:net';
import { readFileSync } from 'node:fs';
import { catalogContract } from './catalog-contract.js';
import { selectConnectedSuite } from './config.js';

type Contracts = typeof import('./transaction-contracts.js');
let contracts: Contracts;
let networkAttempts = 0;

beforeEach(async () => {
  networkAttempts = 0;
  vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => {
    networkAttempts++;
    throw new Error('Offline network guard');
  });
  contracts = await import('./transaction-contracts.js');
});
afterEach(() => {
  try { expect(networkAttempts).toBe(0); }
  finally { vi.restoreAllMocks(); }
});

// Only read the reviewed migration, never execute it. The existing catalog
// contract pins its LF-normalized hash, so drift requires explicit review.
const sql = readFileSync(new URL('../../../prisma/migrations/20261020000100_first_increment/migration.sql', import.meta.url), 'utf8');
const normalize = (value: string) => value.replace(/\s+/g, ' ').replace(/\s*,\s*/g, ',').trim();

it('maps precisely the eight executable signatures and preserves parameter order/defaults', () => {
  const expected = catalogContract.functions.filter((fn) => fn.executable);
  expect(contracts.transactionContracts.map((c) => c.name).sort()).toEqual(expected.map((f) => f.name).sort());
  for (const contract of contracts.transactionContracts) {
    const signature = new RegExp(`CREATE FUNCTION app\\.${contract.name}\\(([\\s\\S]*?)\\)\\s+RETURNS ([\\s\\S]*?)\\s+LANGUAGE`).exec(sql);
    expect(signature, contract.name).not.toBeNull();
    expect(normalize(signature![1])).toBe(normalize(contract.parameters));
    expect(normalize(signature![2])).toBe(normalize(contract.result));
    expect(contract.effects.length).toBeGreaterThan(0);
    for (const rejection of contract.rejections) {
      expect(sql, `${contract.name}: ${rejection.scenario}`).toContain(rejection.evidence);
      expect(['22023', '25001', '23503', '23505', '23514', '40001', '55000']).toContain(rejection.state);
    }
  }
});

it('ties explicit errors to their SQLSTATE in the pinned migration, not an error message at runtime', () => {
  for (const contract of contracts.transactionContracts) {
    for (const rejection of contract.rejections) {
      const raise = sql.split(/\r?\n/).find((line) => line.includes('RAISE EXCEPTION') && line.includes(rejection.evidence));
      if (raise) expect(raise).toContain(`ERRCODE='${rejection.state}'`);
    }
  }
});

it.each(['sql-contracts', 'concurrency'])('keeps %s disabled despite the declarative obligations', (suite) => {
  expect(contracts.transactionBoundaries.enabled).toBe(false);
  expect(() => selectConnectedSuite(suite)).toThrow(/SUITE_REFUSED/);
});

it('exercises each mapped rejection with synthetic adapter errors and an isolated savepoint', async () => {
  const { rejectsSqlState } = await import('./sqlstate.js');
  for (const contract of contracts.transactionContracts) {
    for (const rejection of contract.rejections) {
      const statements: string[] = [];
      const tx = { $executeRaw: async (parts: TemplateStringsArray) => { statements.push(parts.join('')); } };
      await rejectsSqlState(tx, async () => {
        throw { code: 'P2010', meta: { driverAdapterError: { cause: {
          originalCode: rejection.state, originalMessage: 'SYNTHETIC sensitive fixture',
        } } } };
      }, rejection.state);
      expect(statements).toEqual(['SAVEPOINT db_test_negative', 'ROLLBACK TO SAVEPOINT db_test_negative', 'RELEASE SAVEPOINT db_test_negative']);
    }
  }
  // These mocks validate error handling only, never claim a SQL function ran.
});
