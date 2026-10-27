import { writeSync } from 'node:fs';
import { Socket } from 'node:net';
import { diagnosticCode, diagnosticError, parseDiagnostic, reportDiagnostic } from './diagnostics.mjs';
import * as diagnostics from './diagnostics.mjs';

vi.mock('node:fs', async (original) => ({
  ...await original<typeof import('node:fs')>(), writeSync: vi.fn(),
}));

describe('connected diagnostic boundary (offline)', () => {
  let attempts = 0;
  beforeEach(() => {
    attempts = 0;
    vi.mocked(writeSync).mockReset();
    vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => {
      attempts += 1;
      throw new Error('Offline network guard');
    });
  });
  afterEach(() => {
    expect(attempts).toBe(0);
    vi.restoreAllMocks();
  });

  it('recognizes only locally created errors, without examining arbitrary driver fields', () => {
    const own = diagnosticError('CONFIG_URL');
    expect(diagnosticCode(own, 'UNKNOWN')).toBe('CONFIG_URL');
    expect(diagnosticCode(Object.assign(new Error('private-sentinel'), {
      diagnosticCode: 'CONFIG_URL', code: 'CONFIG_URL',
    }), 'IDENTITY_QUERY')).toBe('IDENTITY_QUERY');
    expect(diagnosticCode({ get diagnosticCode() { throw new Error('private-sentinel'); } },
      'IDENTITY_QUERY')).toBe('IDENTITY_QUERY');
    expect(own).not.toHaveProperty('cause');
  });
  it('keeps the branded category independent of mutated error messages', () => {
    const own = diagnosticError('MODULE_INIT');
    own.message = 'private-sentinel';
    expect(diagnosticCode(own, 'UNKNOWN')).toBe('MODULE_INIT');
  });
  it('identifies local validation errors by identity, never by untrusted fields or getters', () => {
    for (const code of ['CATALOG_DEFAULT_ACL_FUNCTIONS', 'UNKNOWN']) {
      const own = diagnosticError(code);
      expect(diagnostics.isDiagnosticError(own)).toBe(true);
      expect(diagnostics.isDiagnosticError(Object.fromEntries(Object.entries(own)))).toBe(false);
    }
    const trap = () => { throw new Error('PRIVATE_SENTINEL'); };
    for (const value of [null, undefined, 'PRIVATE_SENTINEL',
      { diagnosticCode: 'CATALOG_DEFAULT_ACL_FUNCTIONS' },
      Object.defineProperty({}, 'diagnosticCode', { get: trap }),
      new Proxy({}, { get: trap, getOwnPropertyDescriptor: trap }),
    ]) expect(diagnostics.isDiagnosticError(value)).toBe(false);
  });
  it.each([
    ['P1000', 'TX_ERROR_AUTHENTICATION'], ['P1001', 'TX_ERROR_UNREACHABLE'],
    ['P1003', 'TX_ERROR_DATABASE_MISSING'], ['P1008', 'TX_ERROR_SOCKET_TIMEOUT'],
    ['P1010', 'TX_ERROR_ACCESS_DENIED'], ['P1011', 'TX_ERROR_TLS'],
    ['P1017', 'TX_ERROR_CONNECTION_CLOSED'], ['P2024', 'TX_ERROR_POOL_TIMEOUT'],
    ['P2028', 'TX_ERROR_API'], ['P2037', 'TX_ERROR_CONNECTION_LIMIT'],
    ['P2010', 'TX_ERROR_RAW_QUERY'], ['P2039', 'TX_ERROR_DATABASE'],
  ])('maps only the structured Prisma code %s, without interpreting messages', (code, expected) => {
    const error = { code, get message() { throw new Error('PRIVATE_MESSAGE'); },
      get stack() { throw new Error('PRIVATE_STACK'); } };
    expect(diagnostics.transactionErrorCategory(error)).toBe(expected);
    reportDiagnostic('failure', diagnostics.transactionErrorCategory(error));
    const frame = String(vi.mocked(writeSync).mock.calls[0]![1]).trim();
    expect(parseDiagnostic(frame)).toEqual({ kind: 'failure', code: expected });
  });
  it.each([
    ['57014', 'TX_ERROR_CANCELLED'], ['55P03', 'TX_ERROR_LOCK_UNAVAILABLE'],
    ['25006', 'TX_ERROR_READ_ONLY'], ['42601', 'TX_ERROR_SQL_SYNTAX'],
  ])('distinguishes an allowlisted PostgreSQL code from a generic query error (%s)', (code, expected) => {
    const cause = { kind: 'postgres', originalCode: code,
      get originalMessage() { throw new Error('PRIVATE_MESSAGE'); } };
    for (const error of [
      { code: 'P2010', meta: { driverAdapterError: { cause } } },
      { code: 'P2039', meta: { driverAdapterError: { cause } } },
      { name: 'DriverAdapterError', cause },
    ]) expect(diagnostics.transactionErrorCategory(error)).toBe(expected);
  });
  it.each([
    ['DatabaseNotReachable', 'TX_ERROR_UNREACHABLE'],
    ['ConnectionClosed', 'TX_ERROR_CONNECTION_CLOSED'],
    ['SocketTimeout', 'TX_ERROR_SOCKET_TIMEOUT'],
    ['AuthenticationFailed', 'TX_ERROR_AUTHENTICATION'],
    ['DatabaseAccessDenied', 'TX_ERROR_ACCESS_DENIED'],
    ['DatabaseDoesNotExist', 'TX_ERROR_DATABASE_MISSING'],
    ['TlsConnectionError', 'TX_ERROR_TLS'],
    ['TooManyConnections', 'TX_ERROR_CONNECTION_LIMIT'],
  ])('classifies unwrapped adapter failures such as commit errors (%s)', (kind, expected) => {
    expect(diagnostics.transactionErrorCategory({ name: 'DriverAdapterError', cause: { kind } })).toBe(expected);
  });
  it('does not label the ambiguous P2028 code as a proven startup timeout', () => {
    for (const message of ['Unable to start a transaction in the given time.', 'Transaction already closed.', 'PRIVATE_SENTINEL']) {
      expect(diagnostics.transactionErrorCategory({ code: 'P2028', message })).toBe('TX_ERROR_API');
    }
  });
  it('never invokes getters or string conversion or copies unknown driver data', () => {
    const trap = () => { throw new Error('PRIVATE_SENTINEL'); };
    const hostile = Object.defineProperties({}, Object.fromEntries(
      ['code', 'meta', 'cause', 'name', 'message', 'stack'].map((key) => [key, { get: trap }]),
    ));
    for (const error of [undefined, null, 'PRIVATE_SENTINEL', hostile,
      { code: { toString: trap } }, { code: 'PRIVATE_SENTINEL' },
      { cause: { kind: 'DatabaseNotReachable' } },
      Object.create({ code: 'P1000' }),
      new Proxy({}, { getOwnPropertyDescriptor: trap }),
      { name: 'DriverAdapterError', cause: { kind: 'postgres', originalCode: 'PRIVATE_SENTINEL' } },
    ]) {
      expect(diagnostics.transactionErrorCategory(error)).toBe('TX_ERROR_UNKNOWN');
    }
  });
  it('normalizes untrusted category and fallback strings without echoing them', () => {
    const own = diagnosticError('postgresql://private-sentinel');
    expect(String(own)).toBe('Error: DB_TEST: UNKNOWN');
    expect(diagnosticCode(own, 'CONFIG_URL')).toBe('UNKNOWN');
    expect(diagnosticCode(new Error('private-sentinel'), 'private-sentinel')).toBe('UNKNOWN');
  });
  it.each([
    ['DB_TEST_DIAGNOSTIC_V1 stage MODULE_IMPORT', { kind: 'stage', code: 'MODULE_IMPORT' }],
    ['DB_TEST_DIAGNOSTIC_V1 failure IDENTITY_QUERY', { kind: 'failure', code: 'IDENTITY_QUERY' }],
  ])('accepts exactly a known frame: %s', (line, expected) => {
    expect(parseDiagnostic(line)).toEqual(expected);
  });
  it.each(['IDENTITY_ADDRESS_TYPE', 'IDENTITY_ADDRESS_VALUE', 'IDENTITY_PORT_TYPE', 'IDENTITY_PORT_VALUE',
    'CATALOG_DEFAULT_ACL_FUNCTIONS', 'CATALOG_DEFAULT_ACL_TABLES', 'CATALOG_DEFAULT_ACL_BOTH'])(
    'preserves the specific failure %s across the sanitized protocol', (code) => {
      const error = diagnosticError(code);
      reportDiagnostic('failure', diagnosticCode(error, 'UNKNOWN'));
      const frame = String(vi.mocked(writeSync).mock.calls[0]![1]).trim();
      expect(parseDiagnostic(frame)).toEqual({ kind: 'failure', code });
    },
  );
  it.each([
    '', 'private-sentinel', 'DB_TEST_DIAGNOSTIC_V1 failure PRIVATE_SENTINEL',
    'DB_TEST_DIAGNOSTIC_V1 failure IDENTITY_QUERY private-sentinel',
    'private-sentinel DB_TEST_DIAGNOSTIC_V1 failure IDENTITY_QUERY',
    'DB_TEST_DIAGNOSTIC_V1 failure IDENTITY_QUERY\n',
    'DB_TEST_DIAGNOSTIC_V1 failure IDENTITY_QUERY\r',
    'DB_TEST_DIAGNOSTIC_V1 failure IDENTITY_QUERY\u0000',
    '\u001b[31mDB_TEST_DIAGNOSTIC_V1 failure IDENTITY_QUERY',
    'DB_TEST_DIAGNOSTIC_V1 arbitrary IDENTITY_QUERY',
    'DB_TEST_DIAGNOSTIC_V1  failure IDENTITY_QUERY',
    'DB_TEST_DIAGNOSTIC_V1 failure identity_query',
    'DB_TEST_DIAGNOSTIC_V1 failure IDENTITY_QUERY\nDB_TEST_DIAGNOSTIC_V1 stage HARNESS_OK',
  ])('rejects malformed or untrusted frames (case %#)', (line) => {
    expect(parseDiagnostic(line)).toBeUndefined();
  });
  it('emits only a fixed ASCII frame on stderr, with no arbitrary diagnostic text', () => {
    reportDiagnostic('failure', 'IDENTITY_QUERY');
    reportDiagnostic('stage', 'MODULE_IMPORT');
    reportDiagnostic('failure', 'postgresql://private-sentinel');
    expect(vi.mocked(writeSync).mock.calls).toEqual([
      [2, '\nDB_TEST_DIAGNOSTIC_V1 failure IDENTITY_QUERY\n'],
      [2, '\nDB_TEST_DIAGNOSTIC_V1 stage MODULE_IMPORT\n'],
      [2, '\nDB_TEST_DIAGNOSTIC_V1 failure UNKNOWN\n'],
    ]);
  });
  it('does not let a diagnostic channel failure replace the original operation outcome', () => {
    vi.mocked(writeSync).mockImplementation(() => { throw new Error('private-sentinel'); });
    expect(() => reportDiagnostic('failure', 'IDENTITY_QUERY')).not.toThrow();
  });
});
