import { expect, it } from 'vitest';
import { connectedTestOptions } from '../config.js';
import { inspectComparabilityCatalog } from '../harness.js';

connectedTestOptions(process.env);
it('checks the pinned 13-table catalog with runtime privileges, read only', async () => {
  expect(await inspectComparabilityCatalog()).toMatchObject({ database: 'synthetic_p4_comparability_test', runtimeRole: 'detector_runtime' });
}, 30000);
