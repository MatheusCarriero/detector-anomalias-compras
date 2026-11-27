import { PurchasePriceReviewService } from './purchase-price-review.service.js';
import { PurchaseComparabilityService } from './purchase-comparability.service.js';
import { PurchaseStatisticsService } from './purchase-statistics.service.js';
import { PurchaseComparabilityRepository } from './purchase-comparability.repository.js';
import { PrismaService } from '../prisma/prisma.service.js';
import { comparabilityFixture } from '../../test/purchase-comparability.fixture.js';
import { readPriceReview } from './purchase-price-review.contract.js';
import * as core from './statistics/price-analysis.js';
import { createExperimentalScenarios } from './statistics/experimental-fixtures.js';
vi.mock('@prisma/adapter-pg', () => ({ PrismaPg: class { constructor() { throw new Error('Database forbidden'); } } }));
function setup() {
  const f = comparabilityFixture();
  const comparability = new PurchaseComparabilityService(new PurchaseComparabilityRepository(new PrismaService(f.client), f.purchases), new PurchaseStatisticsService(f.purchases));
  return { f, comparability, service: new PurchasePriceReviewService(comparability) };
}
afterEach(() => vi.restoreAllMocks());
it('diagnoses an immutable receipt, without claiming zero history or calling the calculator', async () => {
  const { f, service } = setup(); const spy = vi.spyOn(core, 'analyzePrice');
  const result = await service.review(f.id);
  expect(result).toMatchObject({ status: 'unavailable', mode: 'persisted', history: 'not_assessed', metadata_status: 'absent', purchase: { id: f.id, content_sha256: f.receipt.content_sha256 } });
  expect(result).not.toHaveProperty('median_unit_price'); expect(result).not.toHaveProperty('references');
  expect(spy).not.toHaveBeenCalled();
  expect(f.query.mock.calls.every(([sql]) => sql.sql.startsWith('SET ') || sql.sql.includes('p4_cmp_read'))).toBe(true);
  expect(readPriceReview(result, f.id)).toEqual(result);
});
it('keeps declarations distinct from verified historical evidence', async () => {
  const { f, service, comparability } = setup(); await comparability.create(f.id, f.body); f.query.mockClear();
  const result = await service.review(f.id);
  expect(result.metadata_status).toBe('incomplete');
  expect(result.missing_fields).toContain('specification');
  expect(result.unverified_fields).toContain('currency');
  expect(result.metadata_revision?.content_sha256).toHaveLength(64);
  expect(result.status).toBe('unavailable');
  expect(f.query.mock.calls.every(([sql]) => !sql.sql.includes('p4_cmp_write'))).toBe(true);
});
it.each(['P4_NOT_FOUND', 'P4_STORAGE_PERMISSION', 'P4_STORAGE_INTEGRITY'] as const)('keeps technical error %s out of statistical results', async code => {
  const { f, service } = setup(); f.purchases.get.mockResolvedValue({ ok: false, error: { code } });
  await expect(service.review(f.id)).rejects.toThrow();
});
it('runs only the fixed independent simulation using the original calculator', async () => {
  const { f, service } = setup(); const spy = vi.spyOn(core, 'analyzePrice');
  const result = await service.simulation();
  expect(result).toMatchObject({ mode: 'simulation', status: 'available', unit_price: '60.00', median_unit_price: '50.000', percent_difference: '20.000000', references: 30, minimum_references: 20 });
  expect(result).not.toHaveProperty('purchase');
  expect(spy).toHaveBeenCalledOnce(); expect(spy).toHaveBeenCalledWith(createExperimentalScenarios()[0]);
  expect(f.purchases.get).not.toHaveBeenCalled(); expect(f.query).not.toHaveBeenCalled();
  expect(readPriceReview(result, 'simulation')).toEqual(result);
  expect(readPriceReview(result, f.id)).toBeNull();
});
it('does not accept a forged available result for a persisted purchase', async () => {
  const { f, service } = setup(); const result = await service.review(f.id);
  expect(readPriceReview({ ...result, status: 'available' }, f.id)).toBeNull();
  expect(readPriceReview({ ...result, purchase: { ...result.purchase, id: 'bad' } }, f.id)).toBeNull();
  expect(readPriceReview({ ...result, median_unit_price: '0.30' }, f.id)).toBeNull();
});

it.each([['50.00','0.000000'],['60.00','20.000000'],['25.00','-50.000000'],['0.01','-99.980000'],['1000000.00','1999900.000000']])('calculates hypothetical price %s canonically', async (price, difference) => {
 const {f,service}=setup(); const original=createExperimentalScenarios()[0];
 const spy=vi.spyOn(core,'analyzePrice'); const r=await service.hypothetical(price);
 expect(r.contract).toBe('p4-hypothetical-price/1.0');
 expect(r.result).toMatchObject({unit_price:price,median_unit_price:'50.000',percent_difference:difference,references:30});
 expect(spy.mock.calls[0][0]).toEqual({...original,operation:{...original.operation,unitPrice:price}});
 expect(createExperimentalScenarios()[0]).toEqual(original);
 expect(f.query).not.toHaveBeenCalled(); expect(f.purchases.get).not.toHaveBeenCalled();
});
it.each([undefined,null,50,'','0.00','-1.00','1000000.01','1e2','50,00','50.001','50.00\n',{},['50.00']])('rejects invalid hypothetical input %j',async price=>{
 const {service,f}=setup();const spy=vi.spyOn(core,'analyzePrice');await expect(service.hypothetical(price)).rejects.toThrow();expect(f.query).not.toHaveBeenCalled();expect(spy).not.toHaveBeenCalled();
});
