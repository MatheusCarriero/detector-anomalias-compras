import { NestFactory } from '@nestjs/core';
import type { NestExpressApplication } from '@nestjs/platform-express';
import { DemoModule } from './demo/demo.module.js';
import { configurePurchaseProxyErrors } from './demo/purchase-proxy.controller.js';

async function bootstrap() {
  let app: NestExpressApplication | undefined;
  try {
    app = await NestFactory.create<NestExpressApplication>(DemoModule, { logger: false });
    app.useBodyParser('json', { limit: '1kb', inflate: false });
    configurePurchaseProxyErrors(app);
    app.enableShutdownHooks();
    await app.listen(3001, '127.0.0.1');
  } catch {
    await app?.close().catch(() => undefined);
    throw new Error('DEMO_START_FAILED');
  }
}
await bootstrap();
