export type DiagnosticKind = 'stage' | 'failure';
export function diagnosticError(code: string): Error & { readonly diagnosticCode: string };
export function diagnosticCode(error: unknown, fallback: string): string;
export function isDiagnosticError(error: unknown): boolean;
export function transactionErrorCategory(error: unknown): string;
export function reportDiagnostic(kind: DiagnosticKind, code: string): void;
export function parseDiagnostic(line: string): { kind: DiagnosticKind; code: string } | undefined;
