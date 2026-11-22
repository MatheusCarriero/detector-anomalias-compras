import { expect, it } from 'vitest';
import { connectedTestOptions } from '../config.js';
import { inspectP4Comparability } from '../harness.js';

connectedTestOptions(process.env);
it('validates declared revisions in the separately authorized disposable database', async () => {
  expect(await inspectP4Comparability()).toMatchObject({ database: 'synthetic_p4_comparability_test', runtimeRole: 'detector_runtime' });
}, 30000);
