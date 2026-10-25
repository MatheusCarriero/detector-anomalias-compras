// Artificial configuration only: never a real connection target or credential.
export const syntheticEnvironment = {
  DB_TEST_CONFIRM: 'synthetic-only',
  DB_TEST_HOST: '127.0.0.1',
  DB_TEST_PORT: '5432',
  DB_TEST_DATABASE: 'synthetic_stage0_fixture',
  DB_TEST_RUNTIME: 'detector_runtime',
  DB_TEST_RUNTIME_URL:
    'postgresql://detector_runtime:FAKE-password@127.0.0.1:5432/synthetic_stage0_fixture',
  DB_TEST_TLS: 'local-plaintext',
  DB_TEST_OPERATION: 'identity-read-only',
};
