import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module.js';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.enableShutdownHooks();
  try {
    await app.listen(process.env.PORT ?? 3000);
  } catch (error) {
    // HTTP startup can fail after providers have initialized their resources.
    await app.close().catch(() => undefined);
    throw error;
  }
}
await bootstrap();
