/** Assumptions for P4.10C fixtures ONLY. These do not enrich or reinterpret the
 * p4-catalog/1.0 records, describe market prices, or certify real equivalence. */
export const SPECIFICATION_CONTRACT = 'p4-experimental-specifications/1.0';
export const PRICE_BASIS = Object.freeze({
  id: 'experimental-net-tax-included-no-freight/1', currency: 'BRL',
  discount: 'Unit price already net of every simulated discount.',
  tax: 'All simulated nonrecoverable item taxes included; no tax credits.',
  freight: 'Freight excluded and not allocated to item prices.',
  comparability: 'Same payment days and delivery zone; no urgency or other fees in this experiment.',
});
export const EXPERIMENTAL_PRODUCTS = Object.freeze([
  Object.freeze({ productId: 'prod-cimento', specificationId: 'exp-cimento-1', unit: 'saco', packaging: '50 kg',
    specification: 'Cimento CP II-F-32, fabricante fictício EXP, linha única, novo e dentro da validade.' }),
  Object.freeze({ productId: 'prod-tijolo', specificationId: 'exp-tijolo-1', unit: 'unidade', packaging: '1 peça',
    specification: 'Tijolo cerâmico de vedação, 8 furos, 9 × 19 × 19 cm, resistência declarada 1,5 MPa, fabricante fictício EXP.' }),
  Object.freeze({ productId: 'prod-vergalhao', specificationId: 'exp-vergalhao-1', unit: 'barra', packaging: '12 m',
    specification: 'Vergalhão nervurado CA-50, diâmetro 10 mm, fabricante fictício EXP, novo.' }),
  Object.freeze({ productId: 'prod-argamassa', specificationId: 'exp-argamassa-1', unit: 'saco', packaging: '20 kg',
    specification: 'Argamassa colante AC-I cinza para interior, fabricante fictício EXP, linha única, dentro da validade.' }),
  Object.freeze({ productId: 'prod-tubo', specificationId: 'exp-tubo-1', unit: 'barra', packaging: '6 m',
    specification: 'Tubo PVC soldável para água fria, diâmetro externo 25 mm, PN 750 kPa, parede 1,7 mm, fabricante fictício EXP.' }),
]);
