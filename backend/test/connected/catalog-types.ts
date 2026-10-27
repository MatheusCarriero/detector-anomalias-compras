export type CatalogCheck = {
  readonly code: string;
  readonly sql: string;
  readonly validate: (rows: unknown) => void;
};
