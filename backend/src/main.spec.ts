const bootstrapEvents = vi.hoisted(() => [] as string[]);
const failures = vi.hoisted(() => ({
  listen: undefined as Error | undefined,
  close: undefined as Error | undefined,
  closeGate: undefined as Promise<void> | undefined,
  closing: undefined as (() => void) | undefined,
}));

vi.mock('@nestjs/core', () => ({
  NestFactory: {
    create: async () => ({
      enableShutdownHooks: () => {
        bootstrapEvents.push('shutdown-hooks');
      },
      listen: async (port: number) => {
        bootstrapEvents.push(`listen:${port}`);
        if (failures.listen) throw failures.listen;
      },
      close: async () => {
        bootstrapEvents.push('closing');
        failures.closing?.();
        await failures.closeGate;
        if (failures.close) throw failures.close;
        bootstrapEvents.push('closed');
      },
    }),
  },
}));
// The bootstrap test must not construct the application or its database provider.
vi.mock('./app.module.js', () => ({ AppModule: class {} }));

beforeEach(() => {
  vi.resetModules();
  bootstrapEvents.length = 0;
  failures.listen = undefined;
  failures.close = undefined;
  failures.closeGate = undefined;
  failures.closing = undefined;
  vi.stubEnv('PORT', undefined);
  vi.stubEnv('DATABASE_URL', undefined);
});

afterEach(() => vi.unstubAllEnvs());

it('enables lifecycle shutdown before listening without starting a real server', async () => {
  await import('./main.js');
  expect(bootstrapEvents).toEqual(['shutdown-hooks', 'listen:3000']);
});

it('awaits application cleanup when the HTTP listener fails', async () => {
  failures.listen = new Error('Synthetic listener failure');
  const closing = new Promise<void>((resolve) => { failures.closing = resolve; });
  let finishCleanup!: () => void;
  failures.closeGate = new Promise<void>((resolve) => { finishCleanup = resolve; });
  let settled = false;
  const startup = import('./main.js').then(
    () => { settled = true; },
    (error: unknown) => { settled = true; return error; },
  );
  try {
    await closing;
    // Allow import rejection to propagate if bootstrap stops awaiting cleanup.
    await new Promise<void>((resolve) => setImmediate(resolve));
    expect(settled).toBe(false);
    expect(bootstrapEvents).toEqual(['shutdown-hooks', 'listen:3000', 'closing']);
  } finally {
    finishCleanup();
  }
  expect(await startup).toBe(failures.listen);
  expect(bootstrapEvents).toEqual([
    'shutdown-hooks', 'listen:3000', 'closing', 'closed',
  ]);
});

it('preserves the startup failure if cleanup also fails', async () => {
  failures.listen = new Error('Synthetic listener failure');
  failures.close = new Error('Synthetic cleanup failure');
  await expect(import('./main.js')).rejects.toBe(failures.listen);
  expect(bootstrapEvents).toEqual([
    'shutdown-hooks', 'listen:3000', 'closing',
  ]);
});
