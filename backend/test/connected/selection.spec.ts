import { matchesGlob } from 'node:path';
import { connectedTestOptions, selectConnectedSuite } from './config.js';
import { syntheticEnvironment } from './fixtures.js';
import unitConfig from '../../vitest.config.js';
import e2eConfig from '../../vitest.config.e2e.js';

describe('connected suite isolation', () => {
  it('requires the bounded runner even with a valid target', () => {
    expect(() => connectedTestOptions(syntheticEnvironment)).toThrow(/DB_TEST/);
  });
  it('disables test retries, file parallelism and subprocess workers', () => {
    expect(connectedTestOptions({ ...syntheticEnvironment, CONNECTED_TEST_RUNNER: 'bounded-v1' }))
      .toMatchObject({ include: ['test/connected/identity-permissions/*.integration.test.ts'],
        pool: 'threads', maxWorkers: 1, fileParallelism: false, retry: 0,
        passWithNoTests: false, testTimeout: 15000, hookTimeout: 5000,
      });
  });
  it.each(['sql-contracts', 'concurrency', '../src', '*'])('does not enable unreviewed group %s', (group) => {
    expect(() => selectConnectedSuite(group)).toThrow(/DB_TEST/);
  });
  it.each(['identity-permissions', 'sql-contracts', 'concurrency'])(
    'keeps future %s cases out of unit and E2E collection', (group) => {
      const file = `test/connected/${group}/case.integration.test.ts`;
      for (const config of [unitConfig, e2eConfig]) {
        expect(config.test!.include!.some((pattern) => matchesGlob(file, pattern))).toBe(false);
      }
    },
  );
});
