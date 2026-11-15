import { catalog, failure, packet, preparationRequest, prepared, runPacket, runResult, inferenceProtocol } from '../../test/fixtures/procurement-demo.js';
import { parseResponse, validateRequest } from './procurement-demo-contract.js';
import { CONTRACT, FEATURES, OPERATIONS, PROTOCOL, SOURCE_SHA256, MODEL, INFERENCE_PROTOCOL, INFERENCE_CONTRACT } from './procurement-demo-contract.js';
import { readFileSync } from 'node:fs';

describe('Procurement transport contract', () => {
  it('matches the Python pins and ordered contracts without executing Python', () => {
    const read = (name: string) => readFileSync(new URL(`../../../ml/procurement_v2/${name}.py`, import.meta.url), 'utf8');
    const demo = read('demo');
    expect(demo).toContain(`CONTRACT_VERSION = "${CONTRACT}"`);
    expect(demo).toContain(`SOURCE_SHA256 = "${SOURCE_SHA256}"`);
    expect(read('demo_runner')).toContain(`PROTOCOL_VERSION = "${PROTOCOL}"`);
    expect(read('demo_runner')).toContain(`INFERENCE_PROTOCOL_VERSION = "${INFERENCE_PROTOCOL}"`);
    expect(read('demo_inference')).toContain(`CONTRACT_VERSION = "${INFERENCE_CONTRACT}"`);
    for (const [key, value] of Object.entries({ ARTIFACT_ID: MODEL.artifact_id,
      TRUSTED_MODEL_SHA256: MODEL.model_sha256, TRUSTED_METADATA_SHA256: MODEL.metadata_sha256 })) {
      expect(read('artifact')).toContain(`${key} = "${value}"`);
    }
    const allowed = demo.split('_ALLOWED_OPERATIONS = (')[1].split('\n)')[0];
    expect([...allowed.matchAll(/\("(PO-[^"]+)", "([0-9-]+)", 1\)/g)].map(match => [match[1], match[2]])).toEqual(OPERATIONS);
    const matrix = read('batch').split('MATRIX_FEATURES = (')[1].split('\n)')[0];
    expect([...matrix.matchAll(/"([a-z0-9_]+)"/g)].map(match => match[1])).toEqual(FEATURES);
    const inference = read('demo_inference');
    for (const key of ['score_convention', 'score_semantics', 'score_direction'] as const) {
      expect(inference).toContain(`"${key}": "${runResult()[key]}"`);
    }
    expect(demo).toContain(`"status": "${prepared(true).status}" if unavailable else "${prepared().status}"`);
    expect(inference).toContain(`"status": "${runResult(true).status}"`);
    expect(inference).toContain(`result.update(status="${runResult().status}"`);
  });
  it('copies a strictly authorized request', () => {
    const input = preparationRequest();
    expect(validateRequest(input)).toEqual(input);
    expect(validateRequest(input).operation).not.toBe(input.operation);
  });
  it.each([null, [], {}, { ...preparationRequest(), path: 'secret' },
    { ...preparationRequest(), source_sha256: 'other' },
    { ...preparationRequest(), operation: { ...preparationRequest().operation, occurrence: true } },
    { ...preparationRequest(), operation: { ...preparationRequest().operation, order_date: '2025-02-30' } },
    { ...preparationRequest(), operation: { ...preparationRequest().operation, po_id: 'unknown' } },
  ])('rejects untrusted request %j', input => {
    expect(() => validateRequest(input)).toThrow('PROCUREMENT_INVALID_REQUEST');
  });
  it('preserves the entire catalog', () => {
    expect(parseResponse(packet(catalog()), 0, 'catalog')).toEqual(catalog());
  });
  it.each([false, true])('preserves diagnostics, unavailable=%s', unavailable => {
    expect(parseResponse(packet(prepared(unavailable)), 0, 'prepare', preparationRequest(unavailable).operation)).toEqual(prepared(unavailable));
  });
  const mutations: Array<[string, (value: ReturnType<typeof prepared>) => void]> = [
    ['contract', value => { value.contract = 'other'; }],
    ['source', value => { value.source.origin = 'real'; }],
    ['identity', value => { value.operation.occurrence = 2; }],
    ['feature order', value => { value.feature_names.reverse(); }],
    ['vector size', value => { value.values?.pop(); }],
    ['vector association', value => { value.values![0] = 999; }],
    ['null eligible vector', value => { value.values = null; }],
    ['window', value => { value.window.end_exclusive = false; }],
    ['support', value => { value.support.item = -1; }],
    ['missing reason', value => { value.diagnostics.unavailability.price_iqr_distance_90d = null; }],
    ['unknown reason', value => { value.diagnostics.unavailability.price_iqr_distance_90d = 'secret'; }],
    ['negative reference', value => { value.diagnostics.references.item.unit_price!.mad = -1; }],
    ['count', value => { value.diagnostics.features.supplier_lines_90d = 1.5; }],
  ];
  it.each(mutations)('rejects inconsistent %s', (_name, mutate) => {
    const result = prepared(); mutate(result);
    expect(() => parseResponse(packet(result), 0, 'prepare', preparationRequest().operation)).toThrow('PROCUREMENT_INVALID_RESPONSE');
  });
  it('rejects unexpected score and mismatched identity', () => {
    expect(() => parseResponse(packet({ ...prepared(), score: 0.8 }), 0, 'prepare', preparationRequest().operation)).toThrow();
    expect(() => parseResponse(packet(prepared()), 0, 'prepare', preparationRequest(true).operation)).toThrow();
  });
  it.each(['{private', '{}\n{}', packet(prepared()).replace('"quantity":2', '"quantity":1e999')])('rejects malformed JSON or numbers', output => {
    expect(() => parseResponse(output, 0, 'prepare', preparationRequest().operation)).toThrow('PROCUREMENT_INVALID_RESPONSE');
  });
  it('rejects incomplete or duplicated catalog', () => {
    const result = catalog(); result.operations.pop();
    expect(() => parseResponse(packet(result), 0, 'catalog')).toThrow();
    result.operations.push(result.operations[0]);
    expect(() => parseResponse(packet(result), 0, 'catalog')).toThrow();
  });
  it.each([
    ['invalid_request', 'CLI_REQUEST', 2, 'PROCUREMENT_INVALID_REQUEST'],
    ['technical_error', 'CLI_SOURCE_UNAVAILABLE', 1, 'PROCUREMENT_SOURCE_UNAVAILABLE'],
    ['technical_error', 'CLI_SOURCE_HASH', 1, 'PROCUREMENT_SOURCE_HASH'],
    ['technical_error', 'private secret', 1, 'PROCUREMENT_INVALID_RESPONSE'],
    ['invalid_request', 'CLI_REQUEST', 1, 'PROCUREMENT_INVALID_RESPONSE'],
  ] as const)('classifies %s/%s with exit %s', (status, code, exit, expected) => {
    expect(() => parseResponse(failure(status, code), exit, 'catalog')).toThrow(expected);
  });
  it('rejects success with failure exit', () => {
    expect(() => parseResponse(packet(catalog()), 2, 'catalog')).toThrow('PROCUREMENT_INVALID_RESPONSE');
  });
  it.each([false, true])('validates scored or unavailable results, unavailable=%s', unavailable => {
    expect(parseResponse(runPacket(runResult(unavailable)), 0, 'run', preparationRequest(unavailable).operation)).toEqual(runResult(unavailable));
  });
  const runMutations: Array<[string, (value: ReturnType<typeof runResult>) => void]> = [
    ['contract', value => { value.contract = 'other'; }],
    ['score', value => { value.anomaly_score = null; }],
    ['model', value => { value.model = null; }],
    ['hash', value => { value.model!.model_sha256 = '0'.repeat(64); }],
    ['metadata', value => { value.model!.metadata_sha256 = '0'.repeat(64); }],
    ['domain', value => { value.model!.domain = 'invoice'; }],
    ['semantics', value => { value.score_semantics = 'fraud_probability'; }],
    ['features', value => { value.preparation.feature_names.reverse(); }],
  ];
  it.each(runMutations)('rejects invalid inference %s', (_name, mutate) => {
    const value = runResult(); mutate(value);
    expect(() => parseResponse(runPacket(value), 0, 'run', preparationRequest().operation)).toThrow('PROCUREMENT_INVALID_RESPONSE');
  });
  it('refuses score on unavailable operation, unexpected keys and wrong protocol', () => {
    const value = runResult(true); value.anomaly_score = .25;
    expect(() => parseResponse(runPacket(value), 0, 'run', preparationRequest(true).operation)).toThrow();
    expect(() => parseResponse(runPacket({ ...runResult(), risk: 'high' }), 0, 'run', preparationRequest().operation)).toThrow();
    expect(() => parseResponse(packet(runResult()), 0, 'run', preparationRequest().operation)).toThrow();
    expect(() => parseResponse(runPacket(runResult()).replace('"anomaly_score":0.25', '"anomaly_score":1e999'), 0, 'run', preparationRequest().operation)).toThrow();
  });
  it.each(['MODEL_UNAVAILABLE', 'MODEL_INTEGRITY', 'MODEL_INCOMPATIBLE', 'INVALID_SCORE'])('sanitizes inference error %s', error => {
    const output = JSON.stringify({ protocol: inferenceProtocol, status: 'technical_error', error: `CLI_${error}` });
    expect(() => parseResponse(output, 1, 'run', preparationRequest().operation)).toThrow(`PROCUREMENT_${error}`);
  });
});
