# Supplier Risk — auditoria do target e protocolo de split

## Objetivo e escopo

Esta etapa estabelece um target rastreável por fornecedor e partições independentes do target, antes de qualquer EDA, imputação ou treinamento. O protocolo é `1.0.0`; os resultados abaixo foram verificados em **2026-09-09**.

O script `ml/supplier_risk/scripts/prepare_target_and_split.py` é independente de `prepare_features.py`. Ele não transforma, sobrescreve ou particiona fisicamente as features. A base continua sendo `data/processed/supplier_risk/supplier_features_base.parquet`, com **24.112 fornecedores, 10 features e `supplier_id` exclusivamente para rastreabilidade**.

Esta documentação complementa [a preparação das features](supplier_risk_features.md): o split está implementado neste script separado. Posteriormente, `build_ml_dataset.py` implementou imputação train-only e gerou os derivados ML-Ready. EDA e treinamento continuam pendentes. Invoice Anomaly, Purchase Risk e o dataset auxiliar de KPIs não participam desta etapa.

## Origem e papel do target

`Risk_Level` é lido exclusivamente de `data/external/supplier_risk/supplier_risk_dataset.csv`. O arquivo bruto de referência não é utilizado para substituir ou corrigir labels.

A fonte contém classes numéricas `0` e `1`. A decisão atual do projeto adota a convenção descritiva `0 = menor risco`, `1 = maior risco`; ela não recodifica os dados nem comprova a origem da label. Na fase inicial de auditoria essa interpretação permanecia em aberto. Continua não comprovada a regra de construção, sua qualidade como verdade de referência, validade operacional ou independência das features. Não sabemos se decorre de avaliação humana, regra sintética ou outro processo.

`Risk_Level` é armazenado como `risk_level` em uma tabela separada e foi definido como target da futura classificação supervisionada do Supplier Risk. Nunca é feature. `supplier_id` é chave de associação e split, não variável preditora. A conclusão futura deverá ser a capacidade de reproduzir padrões associados à classificação de risco fornecida pelo dataset, não capacidade comprovada de prever risco real. Modelos compatíveis poderão estimar pertencimento à classe 1, não probabilidade real de problemas futuros.

## Auditoria por fornecedor

A remoção de duplicatas considera **todas as colunas da fonte**, antes da seleção ou conversão do target, reproduzindo a deduplicação exata do pipeline de features. Registros parcialmente preenchidos ou com diferenças em qualquer coluna não são descartados como duplicatas exatas.

| Verificação | Resultado |
|---|---:|
| Linhas na fonte | 28.098 |
| Duplicatas exatas removidas | 3.447 |
| Linhas após deduplicação | 24.651 |
| Fornecedores distintos | 24.112 |
| Fornecedores com exatamente um valor distinto de `Risk_Level` | 24.112 |
| Fornecedores sem target preenchido | 0 |
| Fornecedores com mais de um valor distinto | 0 |
| Fornecedores contendo simultaneamente `0` e `1` | 0 |
| Conflitos | 0 (0,0000%) |
| `Supplier_ID` nulo, vazio ou com tipo inválido | 0 |
| `Risk_Level` nulo | 0 |
| `Risk_Level` fora de `{0, 1}` | 0 |
| Problemas de tipo no target | 0 |

Não existem exemplos de conflitos nesta execução. O dtype do target na fonte é `int64`; a saída usa `int8`, sem alterar as classes. O identificador é lido como string, sem remoção de espaços, alteração de caixa ou outra normalização.

As contagens de valores distintos ignoram nulos, mas a validação de nulos é independente e bloqueante: um fornecedor com uma label conhecida e outra ausente não passa pela auditoria.

### Decisão de consolidação

Como todos os fornecedores possuem um único target válido, `supplier_targets.parquet` pôde ser criado. Após a auditoria, são mantidos os pares distintos `(supplier_id, risk_level)`, sem aplicar média, moda, máximo, mínimo ou seleção arbitrária de ocorrência.

Se uma nova fonte apresentar conflito, label nula/inválida ou identificador inválido, o script registra a falha em `supplier_target_audit.json` e termina com código de saída `1`. Não publica novos targets ou split definitivos nessa execução. Um conflito exige decisão metodológica; não há resolução automática.

Se existirem artefatos de uma execução anterior, uma falha não os apaga nem os revalida. Eles não devem ser tratados como resultados da nova entrada. Antes do consumo, conferir o status da auditoria, os hashes de entrada/saída e o hash da auditoria registrado no metadata. O metadata de sucesso é publicado por último.

## Contratos dos artefatos

Todos os arquivos abaixo ficam em `data/processed/supplier_risk/`.

| Arquivo | Conteúdo e finalidade |
|---|---|
| `supplier_targets.parquet` | Exatamente `supplier_id` (`string`) e `risk_level` (`int8`); 24.112 linhas, chave única, target binário não nulo. |
| `supplier_split_assignments.parquet` | Exatamente `supplier_id` (`string`) e `split` (`string`); 24.112 linhas, chave única, valores `train`, `validation` ou `test`. |
| `supplier_target_audit.json` | Dtypes, deduplicação, verificação de labels/IDs, conflitos, exemplos, erros e reconciliação. Relatório separado, não uma matriz de features. |
| `supplier_split_metadata.json` | Versão, data UTC, protocolo, limiares, proporções, contagens, classes posteriores, reconciliação, overlap e hashes SHA-256. |

Os Parquets permanecem ignorados pelo Git. Apenas os dois JSONs receberam exceções específicas no `.gitignore`; nenhum arquivo foi adicionado ao índice nem houve commit.

## Split determinístico e independente do target

Cada fornecedor recebe uma partição utilizando apenas os bytes UTF-8 de seu `supplier_id` exato:

1. Calcular `SHA-256(supplier_id.encode("utf-8"))`.
2. Interpretar o digest completo como inteiro sem sinal de 256 bits, em ordem big-endian, denominado `h`.
3. Atribuir `train` se `h < (2**256 * 70 // 100)`.
4. Caso contrário, atribuir `validation` se `h < (2**256 * 85 // 100)`.
5. Atribuir `test` aos demais valores.

As fronteiras são inteiras e exclusivas. Não se usa `hash()` do Python, seed, salt, estratificação, quotas exatas, target, features ou posição da linha. As linhas são ordenadas por ID apenas para estabilizar a apresentação dos arquivos.

A função de criação do split recebe exclusivamente IDs. A consolidação segura do target é uma condição de continuidade desta etapa, mas os valores das classes não determinam a partição. A distribuição das classes é consultada somente depois de as atribuições estarem fixadas e não provoca rebalanceamento.

O mesmo ID conserva sua partição em reexecuções e na inclusão de outros fornecedores, desde que sua representação textual e o protocolo permaneçam iguais. Mudanças na grafia do ID podem mudar o hash; por isso a padronização de identidade não pode ser alterada silenciosamente. A proporção é aproximada, não uma garantia de tamanho exato ou de balanceamento de classes.

| Partição | Proporção planejada | Fornecedores | Proporção obtida |
|---|---:|---:|---:|
| `train` | 70% | 16.894 | 70,0647% |
| `validation` | 15% | 3.539 | 14,6773% |
| `test` | 15% | 3.679 | 15,2580% |
| Total | 100% | 24.112 | 100,0000% |

## Distribuição posterior de Risk_Level

Os percentuais das classes utilizam como denominador a quantidade de fornecedores da respectiva partição, não a quantidade de registros da fonte.

| Partição | Classe 0 | Classe 0 (%) | Classe 1 | Classe 1 (%) |
|---|---:|---:|---:|---:|
| `train` | 5.008 | 29,6437% | 11.886 | 70,3563% |
| `validation` | 1.110 | 31,3648% | 2.429 | 68,6352% |
| `test` | 1.115 | 30,3071% | 2.564 | 69,6929% |

No conjunto completo há 7.233 fornecedores com classe `0` e 16.879 com classe `1`. As diferenças entre as partições foram apenas registradas. Não foi alterado nenhum ID de partição para aproximar as distribuições.

## Validações e reconciliação

Os conjuntos de IDs da base, dos targets e das atribuições são exatamente iguais: **24.112 esperados e 24.112 obtidos, zero perdidos, zero inesperados e zero duplicados**.

| Interseção de IDs | Quantidade |
|---|---:|
| `train` / `validation` | 0 |
| `train` / `test` | 0 |
| `validation` / `test` | 0 |

As validações rejeitam base vazia, coluna de ID ausente, IDs nulos/vazios/não textuais ou duplicados, falta de partição, partição inválida, atribuição múltipla, divergência de IDs entre tabelas, targets nulos, não binários ou conflitantes. Igualdade de contagens isoladamente não é suficiente: a reconciliação compara os conjuntos completos.

Na implementação original, foram exercitados 29 cenários em memória. A consolidação de qualidade persistiu testes em `tests/supplier_risk/test_target_and_split.py`, cobrindo conflitos sem resolução automática, IDs, fronteiras do SHA-256, reordenação completa, independência das labels e auditoria de falhas em `tmp_path`. Não são experimentos de ML e não dependem dos datasets reais. A leitura independente das saídas reais realizada na etapa anterior confirmou schemas, nulos e metadata; nesta consolidação os artefatos existentes foram somente conferidos por hash, sem regeneração.

## Preservação das features e preparação futura

Na etapa de auditoria/split, a base foi somente lida e manteve seus **1.486 valores ausentes**, sem imputação. A etapa posterior ML-Ready já produziu versões derivadas com medianas aprendidas somente no treino. Essa evolução não alterou a base, os targets nem as atribuições. Os indicadores de ausência de imputação no metadata do split descrevem esse script específico, não negam o preprocessamento posterior. Não houve scaling, encoding, EDA ou treinamento de modelo.

`supplier_record_count` permanece apenas como feature candidata, com a definição:

> Quantidade de registros distintos da fonte associados ao fornecedor após a remoção de duplicatas exatas.

Não há histórico temporal comprovado. A contagem não representa maturidade nem quantidade de períodos observados. Sua utilidade será avaliada futuramente comparando modelo com e sem essa feature, preservando o mesmo split.

Fluxo atual entre camadas; o script de target/split não executa a camada ML-Ready:

```text
Base com nulos + atribuições de split por supplier_id
  ↓
Selecionar somente as features aprovadas de TRAIN
  ↓
Fit de SimpleImputer(strategy="median") somente em TRAIN [implementado]
  ↓
Transformar TRAIN, validation e test com o MESMO imputador [implementado]
  ↓
EDA somente em TRAIN, treinamento e avaliação [futuros]
```

Reutilização do imputador em produção ainda não foi implementada. O treinamento seguirá Logistic Regression como baseline inicial, candidatos Random Forest/Gradient Boosting, escolha em validation e avaliação final única em test, comparando também com a classe majoritária. Ver [contrato supervisionado](supplier_risk_model.md).

O identificador, a coluna `split` e o target devem permanecer fora da matriz de entrada. A associação futura entre tabelas precisa validar cardinalidade um-para-um. As features devem ser selecionadas por contrato explícito, não por todas as colunas de uma tabela resultante de join. A base atual não é uma matriz pronta para ser passada diretamente a `fit()`.

## Execução e integridade

Executar a partir da raiz do projeto:

```powershell
python ml/supplier_risk/scripts/prepare_target_and_split.py
ruff check .
```

Os caminhos são resolvidos a partir de `Path(__file__).resolve().parents[3]`, sem depender do diretório corrente. O pipeline compara os hashes das entradas antes e após o processamento. A verificação final também comparou os arquivos originais e os componentes protegidos de Invoice/Purchase com o estado anterior à execução.

SHA-256 das entradas desta execução:

- Fonte principal: `2A772A6AABB65CCA3785CDBC61335D4AD42AFACE2A61F523691ECCC0641D00D2`.
- Base de features: `5FEBC2B6843B9C0C0ED50EF3786AC74E9E82F5E47C8F8C73E2B6277EDCBADEA6`.

O CSV bruto de referência também foi preservado: `781CA4AD1BF7D670ED8853571A93BD1DAB47B5103E9249BC6CDC1B740AF39CFF`.

Os hashes de targets, atribuições e relatório de auditoria estão no metadata. A data de geração dos JSONs muda a cada execução; determinismo das atribuições não significa timestamp imutável. O resultado do Ruff foi `All checks passed!`. Não houve alteração de dependências nem commit.

## Pendências metodológicas

- Confirmar origem, regra de construção e significado de `Risk_Level` antes de interpretá-lo como verdade operacional. Consistência por ID não comprova validade do target nem ausência de circularidade com as features.
- O split mede separação entre fornecedores, não desempenho temporal. Não há datas comprovadas para estabelecer um teste fora do tempo.
- Conservar a ressalva de origem do índice geopolítico e as pendências de domínio da base de features, descritas na documentação anterior.
- Avaliar futuramente a imputação train-only já implementada; o pipeline atual interrompe se uma coluna estiver totalmente ausente em TRAIN, sem buscar valores em holdout.
- Avaliar a utilidade de `supplier_record_count` com e sem a feature em experimento futuro. Não alterar o split com base nos resultados ou na distribuição observada do target.
- Manter o teste reservado à avaliação final; este diagnóstico de contagens não autoriza usar seus resultados para ajustar transformações, features ou modelos.
