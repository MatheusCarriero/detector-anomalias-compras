import type { PurchaseComparabilityService } from './purchase-comparability.service.js';
import { PurchaseHttpError } from './purchase-http.js';
import { COMPARABILITY_FIELDS } from './statistics/manual-comparability.js';
import { PRICE_REVIEW_CONTRACT, PRICE_SIMULATION_CONTRACT, validCandidatePrice, readPriceReview } from './purchase-price-review.contract.js';
import type { PersistedPriceReview, SimulatedPriceReview } from './purchase-price-review.contract.js';

export class PurchasePriceReviewService {
  constructor(private readonly comparability: Pick<PurchaseComparabilityService, 'status'>) {}

  async review(id: string): Promise<PersistedPriceReview> {
    // Reuse receipt verification and the versioned, read-only metadata repository.
    // Unknown history is deliberately not reported as zero/insufficient support.
    const state = await this.comparability.status(id);
    const receipt = state.receipt_eligibility;
    const metadata = state.current?.validation;
    if (metadata && (metadata.content.purchase.id !== receipt.evidence.id ||
      metadata.content.purchase.version_id !== receipt.evidence.version_id ||
      metadata.content.purchase.content_sha256 !== receipt.evidence.content_sha256)) throw new PurchaseHttpError('P4_INTERNAL_ERROR');
    const result = {
      contract: PRICE_REVIEW_CONTRACT, mode: 'persisted' as const, status: 'unavailable' as const,
      purchase: { id: receipt.evidence.id, version_id: receipt.evidence.version_id,
        content_sha256: receipt.evidence.content_sha256, unit_price: receipt.recorded.unit_price, currency: receipt.recorded.currency },
      metadata_status: state.metadata_status,
      metadata_revision: metadata ? { id: metadata.content.id, revision: metadata.content.revision, content_sha256: metadata.content_sha256 } : null,
      missing_fields: metadata ? metadata.diagnostics.filter(d => d.category === 'missing').map(d => d.field) : [...COMPARABILITY_FIELDS],
      unverified_fields: metadata ? metadata.diagnostics.filter(d => d.category === 'unverified').map(d => d.field) : [],
      history: 'not_assessed' as const, reason: 'manual_contract_and_historical_evidence_required' as const,
    };
    const checked = readPriceReview(result, id);
    if (!checked || checked.mode !== 'persisted') throw new PurchaseHttpError('P4_INTERNAL_ERROR');
    return checked;
  }

  async hypothetical(price: unknown) {
    if (!validCandidatePrice(price)) throw new PurchaseHttpError('P4_INVALID_REQUEST');
    return { contract: PRICE_SIMULATION_CONTRACT, result: await this.calculateSimulation(price) };
  }

  async simulation(): Promise<SimulatedPriceReview> { return this.calculateSimulation(); }

  private async calculateSimulation(price?: string): Promise<SimulatedPriceReview> {
    // Fixed experiment with an optional validated hypothetical price. No receipt,
    // DB read or persisted metadata enters this branch. Imports remain lazy.
    const { createExperimentalScenarios } = await import('./statistics/experimental-fixtures.js');
    const { analyzePrice } = await import('./statistics/price-analysis.js');
    const scenario = createExperimentalScenarios()[0];
    // Only the hypothetical candidate price changes; all commercial assumptions
    // remain those of the fixed experiment, never those of a persisted purchase.
    if (price !== undefined) scenario.operation = { ...scenario.operation, unitPrice: price };
    const result = analyzePrice(scenario);
    if (result.status !== 'available') throw new PurchaseHttpError('P4_INTERNAL_ERROR');
    const response = { contract: PRICE_REVIEW_CONTRACT, mode: 'simulation', status: 'available', origin: result.origin,
      scenario_id: result.context.operationId, unit_price: result.unitPrice, median_unit_price: result.medianUnitPrice,
      percent_difference: result.percentDifference.display,
      percent_fraction: { numerator: result.percentDifference.numerator, denominator: result.percentDifference.denominator },
      references: result.context.support.references, dates: result.context.support.dates, suppliers: result.context.support.suppliers,
      minimum_references: result.context.minimumReferences, window: result.context.window, reference_ids: result.context.referenceIds };
    const checked = readPriceReview(response, 'simulation');
    if (!checked || checked.mode !== 'simulation') throw new PurchaseHttpError('P4_INTERNAL_ERROR');
    return checked;
  }
}
