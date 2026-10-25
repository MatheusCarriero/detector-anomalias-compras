import { expect, test } from 'vitest';
import { connectedTestOptions } from '../config.js';
import { inspectRuntimeIdentity } from '../harness.js';

// This file is NOT part of Stage 0 execution or offline CI.
connectedTestOptions(process.env);

test('confirms effective runtime identity before any fixture or write', async () => {
  const identity = await inspectRuntimeIdentity();
  expect(identity.runtimeRole).toBe('detector_runtime');
});
