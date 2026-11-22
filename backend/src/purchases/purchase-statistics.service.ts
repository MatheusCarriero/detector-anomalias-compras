import type { PurchaseRepository, RepositoryResult } from './purchase-repository.js';
import { adaptPersistedPurchase } from './statistics/persisted-purchase-adapter.js';
import type { PersistedPurchaseEligibility } from './statistics/persisted-purchase-adapter.js';

/** Explicit repository injection; no client, environment access, HTTP route or
 * automatic module registration. Identifier validation and receipt integrity
 * remain the existing repository's responsibility. */
export class PurchaseStatisticsService {
  constructor(private readonly repository: Pick<PurchaseRepository, 'get'>) {}

  async getEligibility(id: unknown): Promise<RepositoryResult<PersistedPurchaseEligibility>> {
    try {
      const result = await this.repository.get(id);
      if (!result.ok) return { ok: false, error: { code: result.error.code } };
      return { ok: true, value: adaptPersistedPurchase(result.value) };
    } catch {
      // Unexpected exceptions remain technical failures, without driver details,
      // retries or an incorrect statistical-unavailability result.
      return { ok: false, error: { code: 'P4_STORAGE_FAILURE' } };
    }
  }
}
