// Stage A: declarative test obligations only. No driver, SQL executor or connection.
// Defaults refer to SQL argument defaults, not permission to invent fixture IDs.
export type Rejection = { scenario: string; state: string; evidence: string };
export type TransactionContract = {
  name: string;
  parameters: string;
  result: string;
  effects: readonly string[];
  rejections: readonly Rejection[];
};

const actor: Rejection = { scenario: 'missing/inactive actor', state: '23503', evidence: 'Active actor required' };
const writerRejections: readonly Rejection[] = [
  actor,
  { scenario: 'invalid state, decimal/date/instant or unknown key', state: '22023', evidence: 'State must be an object' },
  { scenario: 'create with predecessor', state: '22023', evidence: 'Create cannot have a predecessor' },
  { scenario: 'absent entity on revision', state: '23503', evidence: 'Entity absent' },
  { scenario: 'missing/stale expected head on revision', state: '40001', evidence: 'Stale expected head; explicit retry requires rereading' },
  { scenario: 'resolved source refers to another owner', state: '23514', evidence: 'Source identity belongs to another/unresolved owner' },
  { scenario: 'invalid effective interval', state: '23514', evidence: 'effective_to>effective_from' },
];
const writerEffects = [
  'Create revision 1 or append one successor; replace full state, omitted optional fields become NULL.',
  'Advance projection and head atomically; preserve previous versions and typed owner.',
  'Exactly one create/revise audit event with actor, before/after version and database_session.',
  'Deferred head/projection/audit constraints must pass before outer rollback or commit.',
] as const;
const captureIsolation: Rejection = { scenario: 'isolation other than READ COMMITTED', state: '25001', evidence: 'Snapshot operations require READ COMMITTED' };

// The listed rejections are targeted scenarios, not an exhaustive list of errors
// possible for arbitrary PostgreSQL input (e.g. invalid UUID casts or NULLs).
export const transactionContracts: readonly TransactionContract[] = [
  {
    name: 'write_supplier',
    parameters: 'entity uuid,expected uuid,state jsonb,actor uuid,source uuid DEFAULT NULL,valid_from text DEFAULT NULL,valid_to text DEFAULT NULL',
    result: 'TABLE(entity_id uuid,version_id uuid,revision_no integer)',
    effects: [...writerEffects, 'Scalars: name, country_code, status, tier.'],
    rejections: writerRejections,
  },
  {
    name: 'write_department',
    parameters: 'entity uuid,expected uuid,state jsonb,actor uuid,source uuid DEFAULT NULL,valid_from text DEFAULT NULL,valid_to text DEFAULT NULL',
    result: 'TABLE(entity_id uuid,version_id uuid,revision_no integer)',
    effects: [...writerEffects, 'Scalars: name, code.'],
    rejections: writerRejections,
  },
  {
    name: 'write_purchase_order_line',
    parameters: 'entity uuid,expected uuid,state jsonb,supplier uuid,department uuid,currency uuid,actor uuid,source uuid DEFAULT NULL,valid_from text DEFAULT NULL,valid_to text DEFAULT NULL',
    result: 'TABLE(entity_id uuid,version_id uuid,revision_no integer)',
    effects: [...writerEffects, 'Scalars: description, po_date, quantity, unit_price, amount; supplier/department/currency are real FKs.',
      'Decimal text: quantity (20,6), unit_price (24,8), amount (24,6); no rounding or inferred arithmetic.'],
    rejections: [...writerRejections,
      { scenario: 'unknown supplier FK', state: '23503', evidence: 'purchase_order_lines_supplier_id_fkey' },
      { scenario: 'money without currency', state: '23514', evidence: 'currency_id IS NOT NULL' }],
  },
  {
    name: 'register_source_identity',
    parameters: 'namespace text,kind text,external_id text,actor uuid', result: 'uuid',
    effects: ['Create unresolved canonical identity and identity_register audit event; no automatic upsert.'],
    rejections: [actor,
      { scenario: 'unsupported identity kind', state: '23514', evidence: 'source_identities_owner_check' },
      { scenario: 'duplicate namespace/kind/external_id', state: '23505', evidence: 'source_identities_canonical_key' }],
  },
  {
    name: 'resolve_source_identity',
    parameters: 'identity_id uuid,supplier uuid,department uuid,line uuid,actor uuid', result: 'void',
    effects: ['Resolve once to exactly one matching typed owner, record resolved_at and identity_resolve audit.'],
    rejections: [actor,
      { scenario: 'identity absent', state: '23503', evidence: 'Identity absent' },
      { scenario: 'multiple or wrong typed owners', state: '23514', evidence: 'source_identities_owner_check' },
      { scenario: 'nonexistent supplier owner', state: '23503', evidence: 'source_identities_supplier_id_fkey' },
      { scenario: 'second resolution/remapping', state: '55000', evidence: 'Canonical identity cannot be rewritten/remapped' }],
  },
  {
    name: 'observe_source',
    parameters: 'namespace text,kind text,actor uuid,identity_id uuid DEFAULT NULL,source_version text DEFAULT NULL,record_key text DEFAULT NULL,locator text DEFAULT NULL,content_hash text DEFAULT NULL,original_content jsonb DEFAULT NULL,available_at text DEFAULT NULL',
    result: 'uuid',
    effects: ['Append immutable observation and source_observe audit; availability remains unverified.',
      'Hash identifies content integrity, not provenance or business validity.'],
    rejections: [actor,
      { scenario: 'invalid SHA-256 representation', state: '22023', evidence: 'Expected lowercase SHA-256 hex' },
      { scenario: 'instant without offset/excess precision', state: '22023', evidence: 'Use an explicit offset and at most milliseconds' },
      { scenario: 'identity namespace/kind mismatch', state: '23503', evidence: 'source_references_scope_fk' }],
  },
  {
    name: 'capture_line', parameters: 'line_id uuid,actor uuid', result: 'uuid',
    effects: ['Lock line then supplier then department; capture their current heads.',
      'Create draft record_capture with one line root and only existing contexts; audit capture.',
      'Server generates cutoff/capture time; no historical availability claim.'],
    rejections: [actor, captureIsolation, { scenario: 'line absent', state: '23503', evidence: 'Line absent' }],
  },
  {
    name: 'seal_snapshot', parameters: 'snapshot uuid,actor uuid', result: 'text',
    effects: ['Lock draft, validate composition, return/store snapshot/1 SHA-256; seal and audit atomically.',
      'Hash uses PostgreSQL JSONB text, UTF-8, ordered members, UTC/ISO; no universal JSON canonicalization.',
      'No reopening or automatic retry; immutable versions remain referenced.'],
    rejections: [actor, captureIsolation,
      { scenario: 'snapshot absent', state: '23503', evidence: 'Snapshot absent' },
      { scenario: 'already sealed', state: '55000', evidence: 'Snapshot already sealed' },
      { scenario: 'incomplete/conflicting composition (owner-only corruption fixture)', state: '23514', evidence: 'Incomplete, conflicting or temporally invalid capture' }],
  },
];

export const transactionBoundaries = {
  runtime: 'detector_runtime',
  enabled: false,
  fixtures: 'Preprovisioned synthetic active user and currency; never create them using runtime DML.',
  prohibited: 'Direct DML/DDL or internal helpers must fail with 42501; this proves ACL rejection, not trigger execution.',
  rollback: 'Validate baseline before savepoints; force deferred constraints; verify absence by case IDs after outer rollback.',
  privilegedTests: 'Audit-failure trigger injection and direct snapshot corruption remain separate owner-only SQL tests.',
  concurrency: 'Future separately authorized two-session checks; no retries; committed fixtures must be inventoried, never deleted to bypass immutability.',
} as const;
