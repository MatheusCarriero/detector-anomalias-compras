import {
  BadGatewayException, BadRequestException, ConflictException, GatewayTimeoutException,
  Injectable, ServiceUnavailableException,
} from '@nestjs/common';
import type { OnModuleDestroy } from '@nestjs/common';
import { execFile } from 'node:child_process';
import type { ChildProcess } from 'node:child_process';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CONTRACT, PROTOCOL, SOURCE_SHA256, parseResponse, validateRequest } from './procurement-demo-contract.js';
import type { Action, OperationIdentity } from './procurement-demo-contract.js';

// Fixed paths work in src/demo and dist/demo; HTTP/env cannot override them.
const root = fileURLToPath(new URL('../../../', import.meta.url));
const python = join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const runner = join(root, 'ml/procurement_v2/demo_runner.py');
function environment(): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {};
  for (const key of ['SystemRoot', 'WINDIR', 'TEMP', 'TMP']) {
    if (process.env[key]) env[key] = process.env[key];
  }
  return env;
}

@Injectable()
export class ProcurementDemoService implements OnModuleDestroy {
  private busy = false;
  private stopping = false;
  private child?: ChildProcess;
  private pending?: Promise<Record<string, unknown>>;

  async catalog() {
    return this.execute('catalog', { contract: CONTRACT, source_sha256: SOURCE_SHA256 });
  }
  async prepare(input: unknown) {
    const req = validateRequest(input);
    return this.execute('prepare', req, req.operation);
  }
  private async execute(action: Action, request: object, expected?: OperationIdentity) {
    if (this.stopping) throw new ServiceUnavailableException('PROCUREMENT_STOPPING');
    if (this.busy) throw new ConflictException('PROCUREMENT_BUSY');
    const input = JSON.stringify({ protocol: PROTOCOL, action, request }) + '\n';
    if (Buffer.byteLength(input, 'utf8') > 1024) throw new BadRequestException('PROCUREMENT_INPUT_LIMIT');
    this.busy = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let timedOut = false;
    let inputFailed = false;
    const operation = new Promise<Record<string, unknown>>((resolve, reject) => {
      try {
        this.child = execFile(python, ['-I', '-B', '-X', 'utf8', runner], {
          cwd: root, shell: false, windowsHide: true, encoding: 'utf8',
          maxBuffer: 65536, killSignal: 'SIGKILL', env: environment(),
        }, (error, stdout, stderr) => {
          // Callback runs after close; keep the lock until then, even on HTTP disconnect.
          if (this.stopping) return reject(new ServiceUnavailableException('PROCUREMENT_STOPPING'));
          if (error?.code === 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER'
            || Buffer.byteLength(stdout, 'utf8') > 65536 || Buffer.byteLength(stderr, 'utf8') > 65536) {
            return reject(new BadGatewayException('PROCUREMENT_OUTPUT_LIMIT'));
          }
          if (timedOut) return reject(new GatewayTimeoutException('PROCUREMENT_TIMEOUT'));
          if (inputFailed) return reject(new BadGatewayException('PROCUREMENT_INPUT_FAILED'));
          if (error?.code === 'ENOENT' || error?.code === 'EACCES') {
            return reject(new ServiceUnavailableException('PROCUREMENT_EXECUTOR_UNAVAILABLE'));
          }
          const exit = error ? error.code : 0;
          if (error?.signal || (exit !== 0 && exit !== 1 && exit !== 2)) {
            return reject(new BadGatewayException('PROCUREMENT_UNEXPECTED_EXIT'));
          }
          if (stderr.length) return reject(new BadGatewayException('PROCUREMENT_EXECUTION_FAILED'));
          try { resolve(parseResponse(stdout, exit, action, expected)); }
          catch (failure) { reject(failure); }
        });
      } catch {
        reject(new ServiceUnavailableException('PROCUREMENT_EXECUTOR_UNAVAILABLE'));
        return;
      }
      // An explicit timer distinguishes our deadline from unrelated termination.
      timer = setTimeout(() => { timedOut = true; this.terminate(); }, 30000);
      timer.unref();
      const inputFailure = () => { inputFailed = true; this.terminate(); };
      this.child.stdin?.on('error', inputFailure);
      try {
        if (!this.child.stdin) inputFailure();
        else this.child.stdin.end(input, 'utf8');
      } catch { inputFailure(); }
    });
    this.pending = operation.finally(() => {
      clearTimeout(timer);
      this.busy = false;
      this.child = undefined;
      this.pending = undefined;
    });
    return this.pending;
  }
  private terminate() {
    // Do not report completion or free the slot on kill alone; wait for close.
    try { this.child?.kill('SIGKILL'); } catch { /* close/error callback owns completion */ }
  }
  async onModuleDestroy() {
    this.stopping = true;
    this.terminate();
    await this.pending?.catch(() => undefined);
  }
}
