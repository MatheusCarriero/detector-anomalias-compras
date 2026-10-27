import { writeSync } from 'node:fs';

// A fixed vocabulary is the only information allowed across the diagnostic boundary.
const codes = new Set([
  'CONFIG_MISSING', 'CONFIG_CONFLICT', 'CONFIG_TARGET', 'CONFIG_URL',
  'RUNNER_REQUIRED', 'SUITE_REFUSED', 'CHILD_CONFIGURATION', 'CHILD_BOOTSTRAP',
  'CHILD_SPAWN', 'CHILD_EXIT', 'CHILD_TIMEOUT', 'CHILD_SIGNAL',
  'CHILD_TERMINATION_UNCONFIRMED', 'MODULE_IMPORT', 'MODULE_COMPILE', 'MODULE_INIT',
  'CLIENT_RESOLUTION', 'TRANSACTION_START', 'READ_ONLY_SETUP', 'SESSION_TIMEOUT_SETUP',
  'TRANSACTION_CALLBACK', 'TRANSACTION_RESOLVED',
  'TX_ERROR_AUTHENTICATION', 'TX_ERROR_UNREACHABLE', 'TX_ERROR_DATABASE_MISSING',
  'TX_ERROR_SOCKET_TIMEOUT', 'TX_ERROR_ACCESS_DENIED', 'TX_ERROR_TLS',
  'TX_ERROR_CONNECTION_CLOSED', 'TX_ERROR_POOL_TIMEOUT', 'TX_ERROR_API',
  'TX_ERROR_CONNECTION_LIMIT', 'TX_ERROR_RAW_QUERY', 'TX_ERROR_DATABASE',
  'TX_ERROR_CANCELLED', 'TX_ERROR_LOCK_UNAVAILABLE', 'TX_ERROR_READ_ONLY',
  'TX_ERROR_SQL_SYNTAX', 'TX_ERROR_UNKNOWN',
  'IDENTITY_QUERY', 'TRANSACTION_FINISH', 'IDENTITY_RESULT_SHAPE', 'IDENTITY_MISMATCH',
  'IDENTITY_VERSION', 'IDENTITY_SEARCH_PATH', 'IDENTITY_DATABASE', 'IDENTITY_USER',
  'IDENTITY_ENDPOINT', 'IDENTITY_SCHEMA', 'IDENTITY_PRIVILEGES', 'IDENTITY_TRANSPORT',
  'IDENTITY_ADDRESS_TYPE', 'IDENTITY_ADDRESS_VALUE', 'IDENTITY_PORT_TYPE', 'IDENTITY_PORT_VALUE',
  'RESOURCE_CLEANUP', 'RESOURCE_CLEANUP_TIMEOUT', 'RESOURCE_CLEANUP_HOOK',
  'HARNESS_BUSY', 'HARNESS_UNUSABLE', 'HARNESS_OK', 'UNKNOWN',
  'CATALOG_CONTRACT', 'CATALOG_DEFINITION', 'CATALOG_RESULT_SHAPE', 'CATALOG_ROLES',
  'CATALOG_RELATIONS', 'CATALOG_FUNCTIONS', 'CATALOG_COLUMNS', 'CATALOG_CONSTRAINTS',
  'CATALOG_INDEXES', 'CATALOG_TRIGGERS', 'CATALOG_DEFAULT_ACL', 'CATALOG_LOAD',
  'CATALOG_DEFAULT_ACL_FUNCTIONS', 'CATALOG_DEFAULT_ACL_TABLES', 'CATALOG_DEFAULT_ACL_BOTH',
]);
const ownedErrors = new WeakMap();
const safeCode = (code) => codes.has(code) ? code : 'UNKNOWN';

export function diagnosticError(code) {
  const category = safeCode(code);
  const error = new Error(`DB_TEST: ${category}`);
  Object.defineProperty(error, 'diagnosticCode', { value: category, enumerable: true });
  ownedErrors.set(error, category);
  return error;
}

export function diagnosticCode(error, fallback) {
  // Do not inspect driver objects, getters, messages, stack traces or arbitrary codes.
  return ownedErrors.get(error) ?? safeCode(fallback);
}

export function isDiagnosticError(error) {
  // Object identity only: an external diagnosticCode field is not trusted.
  return ownedErrors.has(error);
}

const prismaCategories = new Map([
  ['P1000', 'TX_ERROR_AUTHENTICATION'], ['P1001', 'TX_ERROR_UNREACHABLE'],
  ['P1003', 'TX_ERROR_DATABASE_MISSING'], ['P1008', 'TX_ERROR_SOCKET_TIMEOUT'],
  ['P1010', 'TX_ERROR_ACCESS_DENIED'], ['P1011', 'TX_ERROR_TLS'],
  ['P1017', 'TX_ERROR_CONNECTION_CLOSED'], ['P2024', 'TX_ERROR_POOL_TIMEOUT'],
  // P2028 also covers closed/expired/invalid transactions, not just maxWait.
  ['P2028', 'TX_ERROR_API'], ['P2037', 'TX_ERROR_CONNECTION_LIMIT'],
  ['P2010', 'TX_ERROR_RAW_QUERY'], ['P2039', 'TX_ERROR_DATABASE'],
]);
const adapterCategories = new Map([
  ['AuthenticationFailed', 'TX_ERROR_AUTHENTICATION'],
  ['DatabaseNotReachable', 'TX_ERROR_UNREACHABLE'],
  ['DatabaseDoesNotExist', 'TX_ERROR_DATABASE_MISSING'],
  ['SocketTimeout', 'TX_ERROR_SOCKET_TIMEOUT'],
  ['DatabaseAccessDenied', 'TX_ERROR_ACCESS_DENIED'],
  ['TlsConnectionError', 'TX_ERROR_TLS'],
  ['ConnectionClosed', 'TX_ERROR_CONNECTION_CLOSED'],
  ['TooManyConnections', 'TX_ERROR_CONNECTION_LIMIT'],
]);
const postgresCategories = new Map([
  // Cancellation does not establish a timeout; 55P03 can also mean NOWAIT.
  ['57014', 'TX_ERROR_CANCELLED'], ['55P03', 'TX_ERROR_LOCK_UNAVAILABLE'],
  ['25006', 'TX_ERROR_READ_ONLY'], ['42601', 'TX_ERROR_SQL_SYNTAX'],
]);

function ownData(object, key) {
  if (object === null || typeof object !== 'object') return;
  try {
    const descriptor = Object.getOwnPropertyDescriptor(object, key);
    return descriptor && Object.hasOwn(descriptor, 'value') ? descriptor.value : undefined;
  } catch { return undefined; }
}

export function transactionErrorCategory(error) {
  // This is diagnostic metadata only, never an identity/authentication decision.
  // Read only a bounded set of own data fields: no getters, recursive causes,
  // string conversion, driver messages, SQL, URLs, result values or stacks.
  const wrapped = ownData(ownData(error, 'meta'), 'driverAdapterError');
  const adapter = wrapped ?? (ownData(error, 'name') === 'DriverAdapterError' ? error : undefined);
  const cause = ownData(adapter, 'cause');
  const kind = ownData(cause, 'kind');
  const specific = kind === 'postgres'
    ? postgresCategories.get(ownData(cause, 'originalCode'))
    : adapterCategories.get(kind);
  return specific ?? prismaCategories.get(ownData(error, 'code')) ?? 'TX_ERROR_UNKNOWN';
}

export function reportDiagnostic(kind, code) {
  if (kind !== 'stage' && kind !== 'failure') return;
  // Start a fresh line even when unrelated stderr stopped mid-message.
  try { writeSync(2, `\nDB_TEST_DIAGNOSTIC_V1 ${kind} ${safeCode(code)}\n`); }
  catch { /* Diagnostics cannot replace the failure or interfere with cleanup. */ }
}

export function parseDiagnostic(line) {
  if (typeof line !== 'string' || line.length > 100) return;
  const match = /^DB_TEST_DIAGNOSTIC_V1 (stage|failure) ([A-Z_]+)$/.exec(line);
  // JS's $ can match before a final newline; require all bytes to match as well.
  if (!match || match[0].length !== line.length || !codes.has(match[2])) return;
  return { kind: match[1], code: match[2] };
}
