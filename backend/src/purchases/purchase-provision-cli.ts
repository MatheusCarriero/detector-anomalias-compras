import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import type { ProvisionClient, ProvisionProfile } from './purchase-provisioning.js';

function fail(code: string): never { throw new Error(`P4_PROVISION_${code}`); }

export function provisionConfig(args: string[], env: NodeJS.ProcessEnv) {
  if (args.length !== 1 || args[0] !== '--execute-synthetic-p4') fail('OPT_IN_REQUIRED');
  const allowed = ['P4_PROVISION_CONFIRM', 'P4_PROVISION_URL', 'P4_PROVISION_TLS', 'P4_PROVISION_PROFILE'];
  for (const [key, value] of Object.entries(env)) {
    if (value && ((key.toUpperCase().startsWith('P4_PROVISION_') && !allowed.includes(key))
      || /^(PG.*|DB_TEST_.*|DATABASE_URL|DIRECT_URL|SHADOW_DATABASE_URL|NODE_OPTIONS|NODE_DEBUG.*|DEBUG|CI|NODE_TLS_REJECT_UNAUTHORIZED)$/i.test(key))) fail('CONFIG_CONFLICT');
  }
  const profile = env.P4_PROVISION_PROFILE ?? 'p4-v1';
  if (!['p4-v1', 'comparability-v1', 'p4-api-comparability-v1'].includes(profile)) fail('CONFIG_REQUIRED');
  const database = profile === 'comparability-v1' ? 'synthetic_p4_comparability_test' : 'synthetic_detector_anomalias_compras_test';
  const confirmation = profile === 'p4-api-comparability-v1' ? 'synthetic-p4-api-comparability-catalog/1.0'
    : profile === 'comparability-v1' ? 'synthetic-p4-comparability-catalog/1.0' : 'synthetic-p4-catalog/1.0';
  if (env.P4_PROVISION_CONFIRM !== confirmation || env.P4_PROVISION_TLS !== 'local-plaintext'
    || typeof env.P4_PROVISION_URL !== 'string') fail('CONFIG_REQUIRED');
  let url: URL; let password: string;
  try { url = new URL(env.P4_PROVISION_URL); password = decodeURIComponent(url.password); }
  catch { fail('CONFIG_URL'); }
  if (!['postgresql:', 'postgres:'].includes(url.protocol) || url.hostname !== '127.0.0.1' || url.port !== '5432'
    || url.pathname !== `/${database}` || url.username !== 'detector_migrator'
    || url.search || url.hash || !password || Array.from(env.P4_PROVISION_URL + password)
      .some(character => character.charCodeAt(0) <= 32 || character.charCodeAt(0) === 127)) fail('CONFIG_URL');
  // Explicit options: pg cannot fall back to PG*, a Unix socket, or another DB.
  return { host: '127.0.0.1', port: 5432, database,
    user: 'detector_migrator', password, ssl: false, application_name: 'p4-synthetic-provision-v1',
    connectionTimeoutMillis: 3000, statement_timeout: 5000, query_timeout: 8000,
    idle_in_transaction_session_timeout: 8000, options: '-c search_path=pg_catalog' };
}

interface AdminClient extends ProvisionClient {
  connect(): Promise<unknown>;
  end(): Promise<void>;
  on(event: 'error', listener: (error: Error) => void): unknown;
}
interface Dependencies {
  loadCore?: () => Promise<{ provisionP4: (client: ProvisionClient, profile?: ProvisionProfile) => Promise<unknown>;
    P4_MIGRATIONS: readonly { name: string; hash: string }[];
    P4_COMPARABILITY_MIGRATIONS?: readonly { name: string; hash: string }[] }>;
  createClient?: (config: ReturnType<typeof provisionConfig>) => Promise<AdminClient>;
  readMigration?: (name: string) => Promise<Buffer>;
  nodeVersion?: string;
}
type Result = { ok: true; value: unknown } | { ok: false; code: string; transaction?: 'committed' | 'unconfirmed' };
const defaultCore = () => import('./purchase-provisioning.js');
const defaultClient = async (config: ReturnType<typeof provisionConfig>): Promise<AdminClient> => {
  const { Client } = await import('pg'); return new Client(config);
};
const defaultMigration = (name: string) => readFile(new URL(`../../../prisma/migrations/${name}/migration.sql`, import.meta.url));
const codes = new Set(['OPT_IN_REQUIRED', 'CONFIG_CONFLICT', 'CONFIG_REQUIRED', 'CONFIG_URL', 'NODE_VERSION',
  'LOCAL_ARTIFACT', 'CONNECT', 'TARGET', 'MIGRATIONS', 'PERMISSION', 'CONFLICT', 'INTEGRITY', 'DATABASE',
  'ROLLBACK_UNCONFIRMED', 'COMMIT_UNKNOWN', 'DISCONNECT']);
function safeCode(error: unknown, fallback: string) {
  const candidate = error instanceof Error ? error.message.replace(/^P4_PROVISION_/, '') : '';
  return error instanceof Error && codes.has(candidate) && error.message === `P4_PROVISION_${candidate}` ? candidate : fallback;
}

export async function runProvision(args: string[], env: NodeJS.ProcessEnv, {
  loadCore = defaultCore, createClient = defaultClient, readMigration = defaultMigration,
  nodeVersion = process.versions.node,
}: Dependencies = {}): Promise<Result> {
  let client: AdminClient | undefined; let result: Result; let phase = 'LOCAL_ARTIFACT'; let asynchronousError = false;
  try {
    const config = provisionConfig(args, env);
    if (nodeVersion.split('.')[0] !== '24') fail('NODE_VERSION');
    const { provisionP4, P4_MIGRATIONS, P4_COMPARABILITY_MIGRATIONS } = await loadCore();
    // provisionConfig has already checked the explicit profile and confirmation.
    const profile = (env.P4_PROVISION_PROFILE ?? 'p4-v1') as ProvisionProfile;
    const extended = profile !== 'p4-v1';
    const migrations = extended ? P4_COMPARABILITY_MIGRATIONS : P4_MIGRATIONS;
    if (!migrations || (extended && migrations.length !== 3)) fail('LOCAL_ARTIFACT');
    for (const migration of migrations) {
      const bytes = await readMigration(migration.name);
      const canonical = bytes.toString('utf8').replaceAll('\r\n', '\n');
      const lf = Buffer.from(canonical, 'utf8');
      const crlf = Buffer.from(canonical.replaceAll('\n', '\r\n'), 'utf8');
      // Authenticate the canonical content first, then admit exactly its two
      // uniform encodings. No mixed EOLs, lossy decoding or other normalization.
      if (createHash('sha256').update(lf).digest('hex') !== migration.hash
        || (!bytes.equals(lf) && !bytes.equals(crlf))) fail('LOCAL_ARTIFACT');
    }
    phase = 'CONNECT'; client = await createClient(config);
    client.on('error', () => { asynchronousError = true; }); // No raw driver output.
    await client.connect(); if (asynchronousError) fail('CONNECT'); phase = 'DATABASE';
    const value = extended ? await provisionP4(client, profile) : await provisionP4(client);
    result = asynchronousError ? { ok: false, code: 'COMMIT_UNKNOWN' } : { ok: true, value };
  } catch (error) { result = { ok: false, code: safeCode(error, phase) }; }
  finally {
    if (client) {
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        await Promise.race([client.end(), new Promise((_, reject) => {
          timer = setTimeout(() => reject(new Error('close deadline')), 3000);
        })]);
      } catch {
        // A confirmed commit is not rolled back by a later disconnect failure.
        result = { ok: false, code: 'DISCONNECT', transaction: result!.ok ? 'committed' : 'unconfirmed' };
      } finally { clearTimeout(timer); }
    }
  }
  return result;
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  // Bounds even a stalled driver. This terminates ONLY this owned CLI process.
  // Interruption/timeout cannot establish whether a COMMIT reached the server.
  const stop = () => { console.error('P4_PROVISION: INTERRUPTED_OUTCOME_UNKNOWN'); process.exit(1); };
  process.once('SIGINT', stop); process.once('SIGTERM', stop);
  const deadline = setTimeout(() => {
    console.error('P4_PROVISION: DEADLINE_OUTCOME_UNKNOWN'); process.exit(1);
  }, 60000);
  const result = await runProvision(process.argv.slice(2), process.env);
  clearTimeout(deadline); process.removeListener('SIGINT', stop); process.removeListener('SIGTERM', stop);
  console.log(JSON.stringify(result));
  // All resources normally close before this point; failures must not leave an
  // unbounded process. No success/rollback is claimed for an unknown outcome.
  process.exit(result.ok ? 0 : 1);
}
