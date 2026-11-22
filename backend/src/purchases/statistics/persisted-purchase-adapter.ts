import { PURCHASE_CATALOG } from '../purchase-catalog.js';
import { PURCHASE_CONTRACT } from '../purchase-contract.js';
import type { PurchaseRecord } from '../purchase-repository.js';
import type { PriceAnalysisInput } from './price-analysis.js';

const DIAGNOSTICS = [
  { category: 'contract_incompatibility', code: 'manual_origin_not_supported', field: 'origin' },
  { category: 'missing_requirement', code: 'technical_specification_missing', field: 'specificationId' },
  { category: 'missing_requirement', code: 'packaging_not_explicit', field: 'packaging' },
  { category: 'missing_requirement', code: 'price_composition_unknown', field: 'priceBasis' },
  { category: 'missing_requirement', code: 'delivery_conditions_missing', field: 'deliveryZone' },
  { category: 'missing_requirement', code: 'quantity_pricing_unknown', field: 'quantityPricing' },
  { category: 'insufficient_historical_evidence', code: 'availability_not_established', field: 'availableAt' },
  { category: 'insufficient_historical_evidence', code: 'historical_coverage_not_established', field: 'history.coverage' },
] as const;

export type PersistedPurchaseDiagnostic = (typeof DIAGNOSTICS)[number];

/** Internal boundary for receipts already verified by PurchaseRepository, NOT
 * an HTTP/raw-JSON validator. Its decoder verifies the original purchase/catalog
 * contracts and manual origin before producing PurchaseRecord.
 *
 * All receipts under that current contract lack the required comparability and
 * availability evidence. This is eligibility diagnosis only: no experimental
 * input is manufactured, no history is fetched and no statistics are executed.
 * recorded_at is retained as evidence, never relabeled as availableAt.
 */
export function adaptPersistedPurchase(record: PurchaseRecord) {
  const p = record.purchase;
  return {
    contract: 'p4-persisted-price-eligibility/1.0' as const,
    target_contract: 'p4-price-analysis/1.0' satisfies PriceAnalysisInput['contract'],
    status: 'unavailable' as const,
    evidence: {
      id: record.id, version_id: record.version_id, revision_no: record.revision_no,
      recorded_at: record.recorded_at, source_reference_id: record.source_reference_id,
      source: { source_namespace: record.source.source_namespace,
        source_entity_kind: record.source.source_entity_kind, source_id: record.source.source_id },
      content_sha256: record.content_sha256,
      purchase_contract: PURCHASE_CONTRACT, origin: 'manual' as const,
      catalog_version: PURCHASE_CATALOG.version, catalog_origin: PURCHASE_CATALOG.origin,
    },
    // Keep the stored unit label, including any package text. Do not parse names
    // into experimental specification IDs, standardized units or packaging.
    recorded: {
      supplier: { id: p.supplier.id, name: p.supplier.name },
      product: { id: p.product.id, name: p.product.name, unit: p.product.unit },
      department: { id: p.department.id, name: p.department.name },
      quantity: p.quantity, unit_price: p.unit_price, total: p.total, currency: p.currency,
      purchase_date: p.purchase_date, payment_days: p.payment_days,
    },
    // Unknown coverage is not zero support or a measured shortage of references.
    history: { status: 'not_assessed' as const },
    diagnostics: DIAGNOSTICS.map(diagnostic => ({ ...diagnostic })),
  };
}

export type PersistedPurchaseEligibility = ReturnType<typeof adaptPersistedPurchase>;
