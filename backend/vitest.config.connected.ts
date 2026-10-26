import { defineConfig } from 'vitest/config';
import { connectedTestOptions } from './test/connected/config.js';
import { diagnosticCode, diagnosticError, reportDiagnostic } from './test/connected/diagnostics.mjs';

// Evaluated before collection: a direct/misconfigured invocation fails closed.
export default defineConfig(() => {
  reportDiagnostic('stage', 'CHILD_CONFIGURATION');
  try {
    return {
      resolve: { tsconfigPaths: true },
      test: connectedTestOptions(process.env),
    };
  } catch (error) {
    const code = diagnosticCode(error, 'CHILD_CONFIGURATION');
    reportDiagnostic('failure', code);
    throw diagnosticError(code);
  }
});
