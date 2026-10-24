import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync, copyFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const backend = fileURLToPath(new URL('../', import.meta.url));
const script = join(backend, 'scripts/prepare-prisma.mjs');
const config = join(backend, 'tsconfig.prisma.json');

function fixture(t, generation = '') {
  assert.ok(existsSync(script), 'The preparation script must exist');
  assert.ok(existsSync(config), 'The dedicated compiler config must exist');
  const root = mkdtempSync(join(tmpdir(), 'prisma preparation '));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const app = join(root, 'backend');
  mkdirSync(join(app, 'scripts'), { recursive: true });
  mkdirSync(join(app, 'node_modules/typescript/bin'), { recursive: true });
  copyFileSync(script, join(app, 'scripts/prepare-prisma.mjs'));
  copyFileSync(config, join(app, 'tsconfig.prisma.json'));
  writeFileSync(join(root, 'package.json'), JSON.stringify({
    type: 'module', scripts: {
      'predb:generate': 'node -e "process.exit(98)"',
      'db:generate': 'node generate.mjs',
      'postdb:generate': 'node -e "process.exit(99)"',
    },
  }));
  writeFileSync(join(app, 'package.json'), '{"type":"module"}');
  // Run the actual installed compiler; only the external generator is a fixture.
  writeFileSync(join(app, 'node_modules/typescript/bin/tsc'),
    `require(${JSON.stringify(join(backend, 'node_modules/typescript/bin/tsc'))});`);
  writeFileSync(join(root, 'generate.mjs'), `
    import assert from 'node:assert/strict';
    import { mkdirSync, writeFileSync } from 'node:fs';
    assert.equal(process.env.DATABASE_URL, undefined);
    writeFileSync('generation-started.txt', 'started');
    mkdirSync('generated/prisma', { recursive: true });
    writeFileSync('generated/prisma/value.ts', 'export const value = 42;');
    writeFileSync('generated/prisma/client.ts', 'export { value } from "./value.ts";');
    ${generation}
  `);
  const output = join(app, 'generated/prisma');
  mkdirSync(output, { recursive: true });
  writeFileSync(join(output, 'stale.js'), 'stale');
  // A sibling is never part of the cleanup boundary.
  writeFileSync(join(app, 'generated/keep.txt'), 'preserve');
  return { root, app, output };
}

function prepare({ root, app }) {
  return spawnSync(process.execPath, [join(app, 'scripts/prepare-prisma.mjs')], {
    cwd: root,
    env: { ...process.env, DATABASE_URL: 'must-not-reach-generator' },
    encoding: 'utf8', timeout: 30_000,
  });
}

test('preparation compiles ESM and declarations, ignores cwd and removes only stale output', async (t) => {
  const paths = fixture(t);
  const result = prepare(paths);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.ok(existsSync(join(paths.output, 'client.d.ts')));
  assert.equal(existsSync(join(paths.output, 'stale.js')), false);
  assert.equal(readFileSync(join(paths.app, 'generated/keep.txt'), 'utf8'), 'preserve');
  const imported = spawnSync(process.execPath, ['--input-type=module', '--eval',
    'const client = await import("./generated/prisma/client.js"); if (client.value !== 42) process.exit(1);'],
  { cwd: paths.app, encoding: 'utf8' });
  assert.equal(imported.status, 0, imported.stderr);
  assert.equal(prepare(paths).status, 0, 'Preparation must be repeatable');
});

test('a generator failure propagates its exit code and never starts compilation', (t) => {
  const paths = fixture(t, 'process.exit(23);');
  const result = prepare(paths);
  assert.equal(result.status, 23, result.stdout + result.stderr);
  assert.equal(existsSync(join(paths.output, 'client.js')), false);
});

test('a failed regeneration preserves the previous compiled client but reports failure', (t) => {
  const paths = fixture(t);
  assert.equal(prepare(paths).status, 0);
  const previous = readFileSync(join(paths.output, 'client.js'));
  writeFileSync(join(paths.root, 'generate.mjs'), 'process.exit(23);');
  const result = prepare(paths);
  assert.equal(result.status, 23, result.stdout + result.stderr);
  assert.deepEqual(readFileSync(join(paths.output, 'client.js')), previous);
});

test('a compiler failure returns nonzero and leaves no partial output', (t) => {
  const paths = fixture(t, 'writeFileSync("generated/prisma/client.ts", "export const value: number = \'bad\';");');
  const result = prepare(paths);
  assert.notEqual(result.status, 0);
  assert.match(result.stdout + result.stderr, /TS2322/);
  assert.equal(existsSync(paths.output), false);
  assert.equal(readFileSync(join(paths.app, 'generated/keep.txt'), 'utf8'), 'preserve');
});

test('an unsupported generated asset fails explicitly instead of silently omitting it', (t) => {
  const paths = fixture(t, 'writeFileSync("generated/prisma/engine.wasm", "fixture");');
  const result = prepare(paths);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /unsupported.*engine\.wasm/i);
});

test('cleanup rejects a redirected output directory and preserves its target', (t) => {
  const paths = fixture(t);
  const external = join(paths.root, 'outside');
  mkdirSync(external);
  writeFileSync(join(external, 'keep.txt'), 'preserve');
  rmSync(paths.output, { recursive: true });
  symlinkSync(resolve(external), paths.output, process.platform === 'win32' ? 'junction' : 'dir');
  const result = prepare(paths);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /symbolic link/i);
  assert.equal(readFileSync(join(external, 'keep.txt'), 'utf8'), 'preserve');
});

test('cleanup rejects a redirected output parent before generation starts', (t) => {
  const paths = fixture(t);
  const external = join(paths.root, 'outside');
  mkdirSync(join(external, 'prisma'), { recursive: true });
  writeFileSync(join(external, 'prisma/keep.txt'), 'preserve');
  const parent = join(paths.app, 'generated');
  rmSync(parent, { recursive: true });
  symlinkSync(resolve(external), parent, process.platform === 'win32' ? 'junction' : 'dir');
  const result = prepare(paths);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /symbolic link/i);
  assert.equal(existsSync(join(paths.root, 'generation-started.txt')), false);
  assert.equal(readFileSync(join(external, 'prisma/keep.txt'), 'utf8'), 'preserve');
});

for (const redirected of ['generated', 'generated/prisma', 'generated/prisma/internal']) {
  test(`generation rejects redirected ${redirected} before writing any source`, (t) => {
    const paths = fixture(t);
    const external = join(paths.root, 'outside');
    mkdirSync(external);
    writeFileSync(join(external, 'keep.ts'), 'preserve');
    const destination = join(paths.root, redirected);
    mkdirSync(resolve(destination, '..'), { recursive: true });
    symlinkSync(resolve(external), destination, process.platform === 'win32' ? 'junction' : 'dir');
    const result = prepare(paths);
    assert.notEqual(result.status, 0, result.stdout + result.stderr);
    assert.equal(existsSync(join(paths.root, 'generation-started.txt')), false,
      'The generator must not start through an existing redirected path');
    assert.equal(readFileSync(join(external, 'keep.ts'), 'utf8'), 'preserve');
    assert.equal(existsSync(join(external, 'client.ts')), false);
    assert.equal(existsSync(join(external, 'prisma')), false);
    assert.equal(readFileSync(join(paths.output, 'stale.js'), 'utf8'), 'stale');
  });
}
