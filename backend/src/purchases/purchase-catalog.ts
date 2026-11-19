// Stable source IDs, not database UUIDs. Keep this fictional catalog separate
// from Invoice, the Procurement CSV and the academic Supplier dataset.
export const PURCHASE_CATALOG = Object.freeze({
  version: 'p4-catalog/1.0',
  origin: 'synthetic',
  suppliers: Object.freeze([
    Object.freeze({ id: 'sup-obra', name: 'Obra Exemplo — materiais de construção' }),
    Object.freeze({ id: 'sup-base', name: 'Base Exemplo — suprimentos' }),
    Object.freeze({ id: 'sup-estrutura', name: 'Estrutura Exemplo — materiais' }),
  ]),
  products: Object.freeze([
    Object.freeze({ id: 'prod-cimento', name: 'Cimento CP II · saco de 50 kg', unit: 'saco de 50 kg' }),
    Object.freeze({ id: 'prod-tijolo', name: 'Tijolo cerâmico · unidade', unit: 'unidade' }),
    Object.freeze({ id: 'prod-vergalhao', name: 'Vergalhão de aço · barra de 12 m', unit: 'barra de 12 m' }),
    Object.freeze({ id: 'prod-argamassa', name: 'Argamassa · saco de 20 kg', unit: 'saco de 20 kg' }),
    Object.freeze({ id: 'prod-tubo', name: 'Tubo PVC · barra de 6 m', unit: 'barra de 6 m' }),
  ]),
  departments: Object.freeze([
    Object.freeze({ id: 'dep-obras', name: 'Obras' }),
    Object.freeze({ id: 'dep-manutencao', name: 'Manutenção' }),
    Object.freeze({ id: 'dep-almoxarifado', name: 'Almoxarifado' }),
  ]),
} as const);
