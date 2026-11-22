import { PurchaseComparabilityRepository } from './purchase-comparability.repository.js';
import { PurchaseStatisticsService } from './purchase-statistics.service.js';
import { PurchaseHttpError, purchaseValue } from './purchase-http.js';
import { MANUAL_COMPARABILITY_CONTRACT } from './statistics/manual-comparability.js';

function id(value: string) {
  if (value.length !== 36 || !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value)) throw new PurchaseHttpError('P4_INVALID_REQUEST');
}
type Failure = Extract<Awaited<ReturnType<PurchaseComparabilityRepository['save']>>, { ok: false }>;
function resultValue<T>(result: { ok: true; value: T } | Failure): T {
  if (result.ok) return result.value;
  const code = result.error.code;
  if (code === 'P4_COMPARABILITY_INVALID' || code === 'P4_COMPARABILITY_CONFLICT') {
    throw new PurchaseHttpError(code);
  }
  // Reuse the established storage-to-HTTP mapping; never forward raw errors.
  return purchaseValue({ ok: false, error: { code } });
}

export class PurchaseComparabilityService {
  constructor(private readonly repository: Pick<PurchaseComparabilityRepository, 'get' | 'save'>,
    private readonly statistics: Pick<PurchaseStatisticsService, 'getEligibility'>) {}

  async status(purchaseId: string) {
    id(purchaseId);
    const receipt = purchaseValue(await this.statistics.getEligibility(purchaseId));
    const current = resultValue(await this.repository.get(purchaseId));
    return { contract: MANUAL_COMPARABILITY_CONTRACT,
      // Receipt diagnostics describe the original immutable receipt only.
      receipt_eligibility: receipt, current,
      metadata_status: current?.validation.status ?? 'absent' };
  }

  async revision(purchaseId: string, requested: string) {
    id(purchaseId);
    if (requested !== 'current' && (/^[1-9][0-9]{0,9}$/.exec(requested)?.[0] !== requested || Number(requested) > 2147483647)) {
      throw new PurchaseHttpError('P4_INVALID_REQUEST');
    }
    const revision = resultValue(await this.repository.get(purchaseId, requested === 'current' ? null : Number(requested)));
    return { contract: MANUAL_COMPARABILITY_CONTRACT, purchase_id: purchaseId,
      outcome: revision ? 'found' : 'absent', revision };
  }

  async create(purchaseId: string, body: unknown) {
    id(purchaseId);
    if (!body || typeof body !== 'object' || Array.isArray(body) ||
      Object.keys(body).length !== 2 || !Object.hasOwn(body, 'metadata') || !Object.hasOwn(body, 'definitions')) {
      throw new PurchaseHttpError('P4_INVALID_REQUEST');
    }
    const { metadata, definitions } = body as { metadata?: { purchase?: { id?: unknown } }; definitions: unknown };
    if (metadata?.purchase?.id !== purchaseId) throw new PurchaseHttpError('P4_COMPARABILITY_INVALID');
    // The existing repository validates the full contract, receipt binding,
    // declarations, original definitions and hashes before its write transaction.
    return { contract: MANUAL_COMPARABILITY_CONTRACT, ...resultValue(await this.repository.save(metadata, definitions)) };
  }
}
