import { expect, test } from 'vitest';
import { connectedTestOptions } from '../config.js';
import { inspectP4Purchases } from '../harness.js';

// Not collected by unit/E2E/offline CI. Requires the bounded runner and the
// distinct P4 write acknowledgement. No connection until the test is invoked.
connectedTestOptions(process.env);

test('P4 authorized synthetic transactions, without cleanup or automatic retry', async () => {
  expect(await inspectP4Purchases()).toMatchObject({
    database: 'synthetic_detector_anomalias_compras_test', runtimeRole: 'detector_runtime',
  });
}, 30000);
