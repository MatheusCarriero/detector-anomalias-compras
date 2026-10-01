# Invoice: comparação operacional com priorização por valor

## Protocolo pré-definido — invoice-value-comparison-1.0

Registro da comparação já acordada, sem novo planejamento: VALIDATION como base
principal; TRAIN somente para separação/procedência; TEST fechado.

- IF: `-score_samples` do modelo existente, decrescente.
- Baseline: `invoice_amount` existente, decrescente, não valor absoluto.
- Mesmas faturas, percentuais fixos **1%, 5%, 10%**; `K = ceil(N × percentual)`.
- Empates: `invoice_id` crescente, nunca labels. Registrar empates no corte.
- Confirmar igualdade dos valores processados com a fonte por ID e uma única
  moeda não nula na coorte. Não converter moedas nem criar features.
- Não usar predict, mudar offset, selecionar threshold ou orçamento pelos resultados.

Para cada fila: K, positivos is_fraud, negativos de referência, Precision@K
(positivos/K), captura (positivos/positivos totais) e lift (Precision@K/prevalência).
Captura/lift indefinidos sem positivos. Distribuir fraud_type entre todos os casos
e entre positivos, incluindo NONE/ausentes. Concentração = maior participação de
um tipo em cada universo; explicitar empates sem criar corte de concentração.

Comparar conjuntos comuns, exclusivos IF e exclusivos valor: contagens, positivos,
negativos e tipos; sobreposição = comuns/K; Jaccard = comuns/união.
**Ganho líquido à mesma capacidade = positivos exclusivos IF − positivos
exclusivos valor.** Registrar adicional bruto, positivos sacrificados e diferenças
de precisão/captura. União é reconciliação, não terceira estratégia de igual custo.

## Execução e rastreabilidade

Reutilizar validações existentes de IDs, schema, labels e separação TRAIN/VAL.
Verificar hashes do modelo, metadata e processados contra evidências anteriores.
Recalcular scores apenas em VALIDATION, pois a evidência anterior é agregada;
reconciliar integralmente resumo IF e hashes das seleções com a triagem anterior.
Nenhum fit. JSON exclusivo, sem sobrescrita, com hashes das entradas autorizadas,
código/protocolo, IDs e projeção de valores/moeda, versões e estatísticas dos
arquivos compartilhados antes/depois. Filtrar Parquets brutos antes de materializar
IDs/splits autorizados; row groups físicos podem ser compartilhados com outros
splits. Nenhum arquivo dedicado a TEST será lido.

Implementação em arquivos novos no checkout atual para preservar helpers e
evidências ainda não commitados. Nenhuma alteração dos pipelines, dados, labels,
features, modelos ou Supplier Risk. Sem commit.

## Interpretação delimitada

is_fraud é referência secundária não comprovada empresarialmente; divergências
com fraud_type não serão corrigidas. Mais positivos não comprova mais fraudes reais
ou retorno financeiro. Avaliar cobertura, complementaridade e concentração juntas;
não declarar vencedor por métrica isolada ou escolher orçamento retrospectivo.
Análise descritiva na VALIDATION já explorada, sem significância, causalidade ou
comprovação de generalização. Limitações temporais, de contexto e procedência do
fit legado permanecem conforme a [auditoria](invoice_methodological_audit.md) e o
[protocolo de triagem](invoice_triage_protocol.md).
