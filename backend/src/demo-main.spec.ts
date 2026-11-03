const mocks = vi.hoisted(() => ({
  create: vi.fn(), listen: vi.fn(), close: vi.fn(), hooks: vi.fn(), parser: vi.fn(),
}));
vi.mock('@nestjs/core', () => ({ NestFactory: { create: mocks.create } }));
vi.mock('./demo/invoice-demo.module.js', () => ({ InvoiceDemoModule: class {} }));
vi.mock('./app.module.js', () => { throw new Error('Demo must not import AppModule'); });

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  mocks.listen.mockResolvedValue(undefined);
  mocks.close.mockResolvedValue(undefined);
  mocks.create.mockResolvedValue({
    listen: mocks.listen, close: mocks.close, enableShutdownHooks: mocks.hooks,
    useBodyParser: mocks.parser,
  });
});

it('binds only loopback and limits JSON parsing without starting a real server', async () => {
  await import('./demo-main.js');
  expect(mocks.create).toHaveBeenCalledWith(expect.any(Function), { logger: false });
  expect(mocks.parser).toHaveBeenCalledWith('json', { limit: '1kb', inflate: false });
  expect(mocks.hooks).toHaveBeenCalledOnce();
  expect(mocks.listen).toHaveBeenCalledWith(3001, '127.0.0.1');
});

it('closes initialized resources and sanitizes listener failures', async () => {
  mocks.listen.mockRejectedValue(new Error('private address'));
  mocks.close.mockRejectedValue(new Error('private cleanup'));
  await expect(import('./demo-main.js')).rejects.toThrowError(/^DEMO_START_FAILED$/);
  expect(mocks.close).toHaveBeenCalledOnce();
});

it('sanitizes module creation failures without logging their details', async () => {
  mocks.create.mockRejectedValue(new Error('private initialization'));
  await expect(import('./demo-main.js')).rejects.toThrowError(/^DEMO_START_FAILED$/);
  expect(mocks.listen).not.toHaveBeenCalled();
});
