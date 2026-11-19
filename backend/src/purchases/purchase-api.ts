import { NestFactory } from '@nestjs/core';
import type { NestExpressApplication } from '@nestjs/platform-express';
import { PurchaseModule } from './purchase.module.js';
import { configurePurchaseHttp, P4_HTTP_HOST, P4_HTTP_PORT } from './purchase-http.js';

export function validatePurchaseApiEnvironment(env: NodeJS.ProcessEnv): void {
  try {
    if (env.P4_API_CONFIRM !== 'local-synthetic-p4/1.0' || env.P4_API_TLS !== 'local-plaintext' || !env.DATABASE_URL) throw new Error();
    for (const [key, value] of Object.entries(env)) {
      if (value && (/^(PG.*|DB_TEST_.*|P4_PROVISION_.*|DIRECT_URL|SHADOW_DATABASE_URL|NODE_OPTIONS|NODE_DEBUG.*|NODE_TLS_REJECT_UNAUTHORIZED|DEBUG|CI)$/i.test(key) ||
        (/^P4_API_/i.test(key) && !['P4_API_CONFIRM', 'P4_API_TLS'].includes(key)))) throw new Error();
    }
    const url = new URL(env.DATABASE_URL);
    const password = decodeURIComponent(url.password);
    if (!['postgres:', 'postgresql:'].includes(url.protocol) || url.hostname !== '127.0.0.1' || url.port !== '5432' ||
      decodeURIComponent(url.pathname) !== '/synthetic_detector_anomalias_compras_test' ||
      decodeURIComponent(url.username) !== 'detector_runtime' || !password || url.search || url.hash ||
      Array.from(env.DATABASE_URL + password).some(char => char.charCodeAt(0) <= 32 || char.charCodeAt(0) === 127)) throw new Error();
  } catch { throw new Error('P4_API_CONFIG'); }
}

export async function startPurchaseApi(): Promise<NestExpressApplication> {
  validatePurchaseApiEnvironment(process.env); // Before constructing any adapter/client.
  let app: NestExpressApplication | undefined;
  try {
    app = await NestFactory.create<NestExpressApplication>(PurchaseModule, { logger: false, abortOnError: false, bodyParser: false });
    configurePurchaseHttp(app);
    app.enableShutdownHooks();
    await app.listen(P4_HTTP_PORT, P4_HTTP_HOST);
    return app;
  } catch {
    await app?.close().catch(() => undefined);
    throw new Error('P4_API_START_FAILED');
  }
}
