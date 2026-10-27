import { expect, test } from 'vitest';
import { connectedTestOptions } from '../config.js';
import { inspectRuntimeCatalog } from '../harness.js';

// Explicitly gated, excluded from *.spec.ts and E2E/CI. No fixtures or writes.
connectedTestOptions(process.env);
test('inspects effective runtime permissions and structural contracts through catalogs', async () => {
  const result = await inspectRuntimeCatalog();
  expect(result.runtimeRole).toBe('detector_runtime');
});
