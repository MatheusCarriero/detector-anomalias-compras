import { defineConfig } from 'vitest/config';
import { connectedTestOptions } from './test/connected/config.js';

// Evaluated before collection: a direct/misconfigured invocation fails closed.
export default defineConfig({
  resolve: { tsconfigPaths: true },
  test: connectedTestOptions(process.env),
});
