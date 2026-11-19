import { startPurchaseApi } from './purchases/purchase-api.js';

try { await startPurchaseApi(); }
catch { console.error('P4_API_START_FAILED'); process.exitCode = 1; }
