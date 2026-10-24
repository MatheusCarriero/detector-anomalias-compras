import { spawnSync } from 'node:child_process';
import { accessSync, existsSync, lstatSync, readdirSync, realpathSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const backend = realpathSync(fileURLToPath(new URL('../', import.meta.url)));
const root = dirname(backend);
const generated = join(root, 'generated/prisma');
const output = join(backend, 'generated/prisma');
const compiler = join(backend, 'node_modules/typescript/bin/tsc');
const config = join(backend, 'tsconfig.prisma.json');

function checkDirectoryBoundary(parent, target) {
  // Both generation and cleanup must reject redirected directories before writing.
  for (const directory of [parent, target]) {
    try {
      const entry = lstatSync(directory);
      if (entry.isSymbolicLink() || !entry.isDirectory()) {
        throw new Error(`Refusing a symbolic link or non-directory: ${directory}`);
      }
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }
}

function checkOutputBoundary() {
  checkDirectoryBoundary(join(backend, 'generated'), output);
  if (resolve(output) !== join(backend, 'generated', 'prisma')) {
    throw new Error('Output must stay inside backend/generated/prisma');
  }
}

function checkSourceBoundary() {
  checkDirectoryBoundary(join(root, 'generated'), generated);
  if (existsSync(generated)) checkGeneratedFiles(generated);
}

function checkGeneratedFiles(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) checkGeneratedFiles(path);
    else if (!entry.isFile() || !entry.name.endsWith('.ts')) {
      throw new Error(`Unsupported generated asset; review before compiling: ${path}`);
    }
  }
}

const env = { ...process.env, npm_config_ignore_scripts: 'true' };
// Generation and compilation are offline operations, never database consumers.
delete env.DATABASE_URL;

function run(args, cwd) {
  // npm_execpath avoids invoking a .cmd file through a shell on Windows.
  const result = spawnSync(process.execPath, args, { cwd, env, stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    const error = new Error(`Prisma preparation failed (exit ${result.status ?? result.signal})`);
    error.exitCode = result.status ?? 1;
    throw error;
  }
}

let compiling = false;
try {
  const npmCli = process.env.npm_execpath;
  if (!npmCli) throw new Error('Run this script with npm.cmd run prisma:prepare');
  accessSync(npmCli);
  accessSync(compiler);
  accessSync(config);
  checkOutputBoundary();
  checkSourceBoundary();
  run([npmCli, 'run', 'db:generate', '--ignore-scripts'], root);
  checkSourceBoundary();
  accessSync(join(generated, 'client.ts'));
  checkOutputBoundary();
  rmSync(output, { recursive: true, force: true });
  compiling = true;
  run([compiler, '--project', config], backend);
  accessSync(join(output, 'client.js'));
  accessSync(join(output, 'client.d.ts'));
  console.log('Prisma Client prepared in backend/generated/prisma (no database connection).');
} catch (error) {
  if (compiling) {
    checkOutputBoundary();
    rmSync(output, { recursive: true, force: true });
  }
  console.error(error.message);
  process.exitCode = error.exitCode ?? 1;
}
