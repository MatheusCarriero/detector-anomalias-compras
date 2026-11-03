import {
  BadGatewayException, ConflictException, GatewayTimeoutException,
  Injectable, ServiceUnavailableException,
} from '@nestjs/common';
import type { OnModuleDestroy } from '@nestjs/common';
import { execFile } from 'node:child_process';
import type { ChildProcess, ExecFileException } from 'node:child_process';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseInvoiceDemoResponse } from './invoice-demo-response.js';
import type { InvoiceDemoResponse } from './invoice-demo-response.js';

// Same relative location in src/demo and dist/demo; never supplied by HTTP/env.
const root = fileURLToPath(new URL('../../../', import.meta.url));
const python = join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const runner = join(root, 'ml/scripts/invoice_demo_runner.py');

function pythonEnvironment(): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {};
  // Python is isolated (-I). Do not pass database credentials or application secrets.
  for (const key of ['SystemRoot', 'WINDIR', 'TEMP', 'TMP']) {
    if (process.env[key]) env[key] = process.env[key];
  }
  return env;
}

function processFailure(error: ExecFileException) {
  if (error.code === 'ENOENT') return new ServiceUnavailableException('DEMO_EXECUTOR_UNAVAILABLE');
  if (error.code === 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER') return new BadGatewayException('DEMO_OUTPUT_LIMIT');
  if (error.killed) return new GatewayTimeoutException('DEMO_TIMEOUT');
  return new BadGatewayException('DEMO_EXECUTION_FAILED');
}

@Injectable()
export class InvoiceDemoService implements OnModuleDestroy {
  private busy = false;
  private stopping = false;
  private child?: ChildProcess;
  private pending?: Promise<InvoiceDemoResponse>;

  async run(): Promise<InvoiceDemoResponse> {
    if (this.stopping) throw new ServiceUnavailableException('DEMO_STOPPING');
    if (this.busy) throw new ConflictException('DEMO_BUSY');
    this.busy = true;

    const operation = new Promise<InvoiceDemoResponse>((resolve, reject) => {
      try {
        this.child = execFile(python, ['-I', '-B', runner], {
          cwd: root, shell: false, windowsHide: true, encoding: 'utf8',
          timeout: 30_000, maxBuffer: 65_536, killSignal: 'SIGKILL',
          env: pythonEnvironment(),
        }, (error, stdout, stderr) => {
          if (this.stopping) return reject(new ServiceUnavailableException('DEMO_STOPPING'));
          if (error) return reject(processFailure(error));
          if (stderr.length) return reject(new BadGatewayException('DEMO_EXECUTION_FAILED'));
          try {
            resolve(parseInvoiceDemoResponse(stdout));
          } catch {
            reject(new BadGatewayException('DEMO_INVALID_RESPONSE'));
          }
        });
      } catch {
        reject(new ServiceUnavailableException('DEMO_EXECUTOR_UNAVAILABLE'));
        return;
      }
      this.child.stdin?.end();
    });
    this.pending = operation.finally(() => {
      // execFile calls back after child close, including timeout/output overflow.
      // A disconnected HTTP client does not release this per-process lock early.
      this.busy = false;
      this.child = undefined;
      this.pending = undefined;
    });
    return this.pending;
  }

  async onModuleDestroy(): Promise<void> {
    this.stopping = true;
    this.child?.kill('SIGKILL');
    await this.pending?.catch(() => undefined);
  }
}
