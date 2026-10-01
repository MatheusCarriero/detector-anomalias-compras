# Invoice — comparação operacional: Isolation Forest × valor da fatura

**Concluído em 28/09/2026, exclusivamente em VALIDATION. TEST permanece fechado.**

## 1. Objetivo e conclusão

Verificar se o ranking do Isolation Forest existente acrescenta informação à
priorização por valor, à mesma capacidade de revisão. O objetivo continua sendo
**triagem de faturas incomuns para auditoria humana**, não classificação automática
de fraude. `is_fraud` é referência de avaliação sem validade empresarial comprovada.

**Resultado observado:** o ganho líquido do IF é **−40, +7 e +192 positivos**
nos orçamentos fixos de 1%, 5% e 10%, respectivamente. As filas compartilham
aproximadamente 61%–64% das faturas; portanto não são equivalentes, mas têm
sobreposição substancial. O enriquecimento anterior no top 1% não demonstrava,
por si só, vantagem sobre uma regra simples: nessa capacidade a baseline por
valor recupera mais positivos.

**Interpretação:** existe evidência descritiva de complementaridade e ganho
incremental condicionado ao orçamento nesta fonte, sobretudo em SPLIT no top 10%.
Não há superioridade uniforme, escolha de vencedor, recomendação automática de
10% ou prova de benefício empresarial. As evidências anteriores foram preservadas.

## 2. Método executado

O [protocolo pré-definido](invoice_value_comparison_protocol.md) foi registrado e
hashado antes da inferência. Esta etapa não refez o planejamento nem escolheu
novos percentuais. Os resultados históricos estão na
[triagem anterior](invoice_triage_results.md).

- Coorte única: **30.000 faturas VALIDATION**, 6.773 positivos (22,5767%) e 23.227
  negativos da referência. Mesmos IDs, splits e labels nas duas estratégias.
- IF existente: 200 árvores, contamination=0.22, random_state=42, n_jobs=-1,
  mesmas 19 features. Nenhum fit, mudança do offset ou uso de predict.
- IF ordenado por `-score_samples` decrescente. Baseline por `invoice_amount`
  decrescente, sem valor absoluto ou conversão.
- Valores processados reconciliados exatamente por ID com invoices. Uma única
  moeda não nula: **ZAR**. Não houve mistura de moedas.
- Top 1%, 5%, 10%: K=300, 1.500, 3.000; arredondamento ceil.
  Empates previstos por invoice_id crescente, nunca pela label. Nenhum empate
  múltiplo observado nas seis fronteiras.
- Precision@K=positivos/K; captura=positivos/6.773;
  lift=Precision@K/0,2257666667. Negativo da referência não significa caso
  necessariamente inútil para auditoria.
- Concentração medida em dois universos: todas as faturas selecionadas e somente
  positivos. NONE/ausentes não são reclassificados.
- Comparação pareada dos conjuntos comuns/exclusivos e ganho líquido à mesma
  capacidade. A união não é uma terceira estratégia de igual custo.
- TRAIN: somente IDs/split e hashes para separação/procedência, sem scoring.
  Fontes compartilhadas filtradas antes da materialização. Nenhum TEST dedicado lido.
- Uma nova chamada de score_samples, somente em VALIDATION: necessária porque
  a evidência anterior era agregada. Resumo IF completo, coorte e fingerprints
  das três seleções coincidiram exatamente com a evidência anterior.

## 3. Resultados observados: recuperação de positivos

| Orçamento | Estratégia | K | Positivos | Negativos da referência | Precision@K | Captura | Lift |
|---|---|---:|---:|---:|---:|---:|---:|
| 1% | Isolation Forest | 300 | 255 | 45 | 85,00% | 3,76% | 3,76x |
| 1% | Valor | 300 | 295 | 5 | 98,33% | 4,36% | 4,36x |
| 5% | Isolation Forest | 1.500 | 645 | 855 | 43,00% | 9,52% | 1,90x |
| 5% | Valor | 1.500 | 638 | 862 | 42,53% | 9,42% | 1,88x |
| 10% | Isolation Forest | 3.000 | 980 | 2.020 | 32,67% | 14,47% | 1,45x |
| 10% | Valor | 3.000 | 788 | 2.212 | 26,27% | 11,63% | 1,16x |

Em pontos percentuais, IF menos valor em Precision@K: **−13,33; +0,47; +6,40**.
Na captura: **−0,59; +0,10; +2,83**. São diferenças descritivas, sem teste de
significância, intervalo de confiança ou alegação de estabilidade independente.

## 4. Sobreposição e ganho incremental

| Orçamento | Casos comuns (positivos) | Casos exclusivos por estratégia | Sobreposição | Jaccard | Positivos só IF | Positivos só valor | Ganho líquido IF |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1% | 189 (187) | 111 | 63,00% | 45,99% | 68 | 108 | -40 |
| 5% | 965 (556) | 535 | 64,33% | 47,42% | 89 | 82 | +7 |
| 10% | 1.832 (662) | 1.168 | 61,07% | 43,95% | 318 | 126 | +192 |

Os exclusivos têm o mesmo número de linhas em cada estratégia, pois os K são
iguais. Por exemplo, no top 10%, o IF troca 1.168 casos por outros 1.168:
obtém 318 positivos exclusivos, mas deixa de recuperar 126 exclusivos do valor.
O ganho líquido é **318 − 126 = 192**, não 318.

A união contém 411/2.035/4.168 faturas e 363/727/1.106 positivos. Esses números
exigiriam capacidade maior que 300/1.500/3.000; não justificam promover a união
como melhoria de igual custo. Nenhuma estratégia combinada foi implementada.

### Composição dos positivos exclusivos

| Tipo dos positivos exclusivos | IF 1% | Valor 1% | IF 5% | Valor 5% | IF 10% | Valor 10% |
|---|---:|---:|---:|---:|---:|---:|
| DOC_TAMPER | 1 | 2 | 3 | 7 | 9 | 14 |
| DUPLICATE | 0 | 0 | 0 | 0 | 0 | 0 |
| GHOST_SUPPLIER | 2 | 0 | 26 | 28 | 45 | 69 |
| INFLATED | 65 | 106 | 0 | 36 | 0 | 5 |
| NONE | 0 | 0 | 3 | 11 | 11 | 24 |
| SPLIT | 0 | 0 | 57 | 0 | 253 | 14 |

**OBSERVAÇÕES:**

- Top 1%: os 68 positivos só IF incluem 65 INFLATED; os 108 só valor incluem
  106 INFLATED. Existe complemento, porém saldo negativo à mesma capacidade.
- Top 5%: IF encontra 57 positivos SPLIT, ausentes da fila por valor, mas
  sacrifica positivos de outros tipos. O saldo agregado é pequeno: +7.
- Top 10%: 253 dos 318 positivos só IF são SPLIT (**79,56%**);
  valor encontra 14 SPLIT exclusivos. A diferença total de SPLIT nas filas é
  +239, parcialmente compensada por −47 positivos nos demais tipos, resultando
  em +192. Nenhum positivo INFLATED é exclusivo IF nos top 5%/10%.

**INTERPRETAÇÃO:** o IF não é simplesmente a mesma ordenação por valor; introduz
mudanças relevantes na seleção. Isso não identifica qual feature causa o ganho,
não isola informação independente do valor (que já participa das 19 features)
e não demonstra captura causal de mecanismos reais de fraude.

## 5. Tipos e concentração

Cada célula: **positivos is_fraud / total de faturas daquele fraud_type**.
Ausência de um tipo aparece como zero, não como dado omitido.

| fraud_type | IF 1% | Valor 1% | IF 5% | Valor 5% | IF 10% | Valor 10% |
|---|---:|---:|---:|---:|---:|---:|
| DOC_TAMPER | 5 / 5 | 6 / 6 | 13 / 13 | 17 / 17 | 29 / 29 | 34 / 34 |
| DUPLICATE | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 1 / 1 | 1 / 1 |
| GHOST_SUPPLIER | 2 / 2 | 0 / 0 | 52 / 53 | 54 / 55 | 124 / 126 | 148 / 150 |
| INFLATED | 248 / 251 | 289 / 294 | 517 / 529 | 553 / 565 | 548 / 560 | 553 / 565 |
| NONE | 0 / 42 | 0 / 0 | 6 / 846 | 14 / 863 | 24 / 2025 | 37 / 2235 |
| SPLIT | 0 / 0 | 0 / 0 | 57 / 59 | 0 / 0 | 254 / 259 | 15 / 15 |

| Orçamento | Estratégia | Tipo dominante em todas as faturas | Participação | Tipo dominante nos positivos | Participação |
|---|---|---|---:|---|---:|
| 1% | IF | INFLATED | 83,67% | INFLATED | 97,25% |
| 1% | Valor | INFLATED | 98,00% | INFLATED | 97,97% |
| 5% | IF | NONE | 56,40% | INFLATED | 80,16% |
| 5% | Valor | NONE | 57,53% | INFLATED | 86,68% |
| 10% | IF | NONE | 67,50% | INFLATED | 55,92% |
| 10% | Valor | NONE | 74,50% | INFLATED | 70,18% |

**OBSERVAÇÃO:** no top 1%, INFLATED representa 97,25% dos positivos IF e 97,97%
dos positivos da baseline por valor. Ambos têm forte concentração no mesmo tipo.
No top 10%, essa concentração cai para 55,92% no IF e 70,18% em valor, enquanto
o diferencial exclusivo IF se concentra principalmente em SPLIT.

**INTERPRETAÇÃO:** diversificação relativa existe, mas não equivale a cobertura
ampla e validada de todos os mecanismos. Não foi criado um limiar pós-resultado
para chamar concentração de excessiva. NONE continua podendo conter positivos,
pois `fraud_type` e `is_fraud` não são semanticamente intercambiáveis.

Os casos com combinação divergente segundo a regra da auditoria anterior são
3/21/43 nas filas IF e 5/27/51 nas filas por valor. Nenhuma label foi corrigida.

## 6. Limitações e hipóteses

- A origem/regra empresarial de is_fraud não foi comprovada. Métricas não são
  taxas de fraudes confirmadas, e scores não são probabilidades de fraude.
- Há ambiguidades entre labels e tipos. Positivos NONE foram preservados e não
  tratados como mecanismo conhecido. Duplicação tem poucos exemplos para conclusões.
- VALIDATION já foi usada em diagnósticos anteriores; não é avaliação final
  independente. Os top-k são aninhados, e faturas de um mesmo fornecedor podem
  ser dependentes. Não se afirma significância ou generalização.
- Permanecem as limitações temporais, agregações sobre todo TRAIN, fornecedores
  conhecidos, falta de contexto documental/transacional e procedência incompleta
  do fit legado descritas na [auditoria](invoice_methodological_audit.md).
- Não há custos, capacidade real dos auditores, severidade confirmada, perda
  evitada ou julgamento humano independente. Mais positivos não comprova maior
  utilidade operacional ou retorno financeiro.
- **Hipótese, não causalidade:** outros componentes do perfil tabular podem mudar
  a seleção em favor dos casos rotulados SPLIT. Este experimento não atribui
  importância causal nem autoriza novas features ou ajustes.
- A validade de negócio de `fraud_type` também não é garantida; distribuição
  por tipo é evidência descritiva da fonte.
- A integridade de TEST foi monitorada por tamanho/mtime, não por hash de seu
  conteúdo. Row groups físicos de fontes globais podem ser compartilhados com
  outros splits; os filtros garantem isolamento lógico, não físico.

## 7. Evidência, validação e integridade

Evidência: [invoice_value_comparison_v1.json](../ml/experiments/invoice_value_comparison_v1.json),
gerada em **2026-09-28T13:49:30.181043+00:00**, com criação exclusiva e sem sobrescrita.
Inclui métricas completas, fronteiras descritivas, conjuntos comuns/exclusivos,
tipos/concentração, hashes de IDs, versões, código/protocolo e inputs.

| Item | SHA-256 |
|---|---|
| JSON do resultado | 9f47cdb9d70ca0cded04aef63cf4e8c1794118b84533fc880f1cba44ab59beea |
| Protocolo anterior à inferência | 259f5155000cd444965f54f461b0287251ac88cb3e41953b3878bec93369b5ec |
| Script executado | 75b6b23ea0b365add1a792bc359d0029168e2bf3cd15dfd775df0d2e55d4e6b3 |
| Modelo preservado | c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b |

Os demais hashes constam do JSON. `selected_ids_sha256` preserva ordem do ranking;
`ids_sha256` nos grupos usa IDs ordenados alfabeticamente para representar o
conjunto. São fingerprints distintos por definição.

- **25 testes novos sintéticos aprovados**: cálculos independentes, ganhos
  negativos/zero/positivos, sobreposição, empates, ausência de positivos, dados
  inválidos, filtros antes da materialização, divergências de fonte/moeda,
  hashes/coorte/seleções anteriores, nenhum fit e recusa de sobrescrita.
- **Suíte completa: 308 passed in 20.82s.** Fixtures temporárias; nenhum treino
  real ou uso dos datasets reais pelos testes.
- Ruff nos dois arquivos novos: **All checks passed!**
- Ruff global: **3 avisos preexistentes**, preservados por estarem fora do escopo:
  I001 e RUF100 em `ml/supplier_risk/scripts/final_evaluation.py`;
  I001 em `tests/supplier_risk/test_final_evaluation_artifact.py`.
- Revisão independente antes da execução: nenhum problema crítico/importante.
  Sugestão menor não bloqueante deixada para manutenção: adicionar caso sintético
  com fonte de valores embaralhada; o realinhamento por ID foi revisado e está correto.
- Reconciliação posterior apenas dos JSONs: métricas IF anteriores, decomposição
  de todos os grupos/tipos e ganhos líquidos; **11 hashes** de inputs/código/
  protocolo conferidos. Nenhuma segunda inferência.
- `git diff --check`: sem erros. Os cinco arquivos novos também foram verificados
  individualmente com `--no-index --check`: nenhuma ocorrência de whitespace;
  status 1 indica arquivos novos/diferentes de /dev/null, não erro de whitespace.
  Links locais, timestamp e hashes citados na documentação conferidos.
- **91 arquivos preexistentes com hashes preservados**; **59 arquivos protegidos
  com tamanho/mtime preservados**, incluindo dados, modelos e Supplier/Purchase.
  Ambos os notebooks locais Supplier 01/02 permaneceram byte a byte inalterados.
- Python 3.14.3; pandas 2.3.3; numpy 2.5.2; pyarrow 25.0.1; scikit-learn 1.9.0;
  joblib 1.6.0. Ambiente isolado preexistente, sem instalar ou alterar dependências.

Nenhum dataset, split, label, feature ou modelo alterado. Zero fits reais,
zero tuning, zero escolha de threshold/orçamento. Nenhum notebook ou execução
real de Supplier/Purchase. Sem frontend, staging ou commit.

## 8. Arquivos e reprodução

Criados somente nesta etapa:

- [Protocolo](invoice_value_comparison_protocol.md).
- [Comparador](../ml/scripts/comparar_triagem_invoice.py).
- [Testes](../tests/invoice/test_invoice_comparison.py).
- [JSON](../ml/experiments/invoice_value_comparison_v1.json).
- Este relatório.

Nenhum arquivo preexistente foi editado. As alterações locais anteriores continuam
no checkout e não pertencem a esta entrega. HEAD permanece `b624204`, sem staging
ou novo commit; os cinco arquivos desta entrega permanecem não rastreados.

Para reprodução independente, a partir da raiz, com os mesmos artefatos e ambiente:

```powershell
python -m ml.scripts.comparar_triagem_invoice --split val
```

**A execução atual já terminou.** O comando recusa sobrescrever o JSON existente
antes de acessar dados/modelo; não apagar a evidência para repetir. Uma reprodução
deve usar cópia separada e conferida do projeto/artefatos. O ambiente principal
não foi reparado nem declarado reproduzível nesta etapa.

Verificações sintéticas, sem datasets:

```powershell
python -m pytest -q tests/invoice/test_invoice_comparison.py
python -m ruff check ml/scripts/comparar_triagem_invoice.py tests/invoice/test_invoice_comparison.py
git diff --check
```

## 9. Próximo passo recomendado — ainda não executado

Manter TEST fechado. Definir um protocolo curto de **revisão humana cega de uma
amostra pré-especificada dos casos comuns e discordantes em TRAIN/VALIDATION**,
com critérios de relevância independentes de score/is_fraud, contexto disponível,
capacidade e custo de investigação. Documentar quando faltarem evidências para
julgar um caso, sem corrigir labels por suposição.

A questão seguinte é se os exclusivos IF — especialmente SPLIT — são úteis para
auditoria, e se compensam os casos sacrificados e o esforço. Somente depois de
fixar finalidade, capacidade por critério externo e conclusões admissíveis,
definir eventual protocolo final antes de qualquer TEST autorizado. Não escolher
10% por ter mostrado maior ganho neste relatório e não promover o modelo a produção.
