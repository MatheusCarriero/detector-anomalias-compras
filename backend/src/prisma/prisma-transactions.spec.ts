import { Prisma } from '../../generated/prisma/client.js';
import { PrismaService } from './prisma.service.js';

describe('PrismaService bounded transactions without a real adapter', () => {
  it.each(['read', 'write'] as const)('uses the injected client and READ COMMITTED for %s', async (access) => {
    const statements: string[] = [];
    const tx = { $queryRaw: vi.fn(), $executeRaw: vi.fn(async (sql: Prisma.Sql) => { statements.push(sql.sql); return 0; }) };
    const client = { $connect: vi.fn(), $disconnect: vi.fn(), $transaction: vi.fn(async (work) => work(tx)) };
    const service = new PrismaService(client);
    const result = await service.transaction(async (provided) => {
      expect(provided).toBe(tx); return 'done';
    }, access);
    expect(result).toBe('done');
    expect(client.$transaction).toHaveBeenCalledWith(expect.any(Function), { isolationLevel: 'ReadCommitted', maxWait: 2000, timeout: 10000 });
    expect(statements).toEqual([
      ...(access === 'read' ? ['SET TRANSACTION READ ONLY'] : []),
      "SET LOCAL statement_timeout = '5s'", "SET LOCAL lock_timeout = '2s'",
    ]);
    expect(client.$connect).not.toHaveBeenCalled(); expect(client.$disconnect).not.toHaveBeenCalled();
  });
  it('propagates callback and commit errors so the repository cannot report premature success', async () => {
    const tx = { $queryRaw: vi.fn(), $executeRaw: vi.fn(async () => 0) };
    const callbackError = { code: '23514' }; const commitError = { code: '23503' };
    const client = { $connect: vi.fn(), $disconnect: vi.fn(), $transaction: vi.fn(async (work) => { await work(tx); throw commitError; }) };
    const service = new PrismaService(client);
    await expect(service.transaction(async () => { throw callbackError; }, 'write')).rejects.toBe(callbackError);
    await expect(service.transaction(async () => 'not committed', 'write')).rejects.toBe(commitError);
  });
  it('refuses a lifecycle-only test client instead of constructing another connection', async () => {
    const service = new PrismaService({ $connect: vi.fn(), $disconnect: vi.fn() });
    await expect(service.transaction(async () => 1, 'read')).rejects.toThrow('Transaction client unavailable');
  });
});
