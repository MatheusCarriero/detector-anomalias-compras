# Invoice Anomaly — auditoria metodológica e EDA

**Registro histórico das seções 1–9 — data:** 24/09/2026. **Estado:** auditoria concluída, sem alteração do pipeline.
**Escopo naquela auditoria:** TRAIN e VALIDATION do Invoice; TEST permanecia fechado para análise.
Supplier Risk, Purchase e o notebook EDA Supplier ficaram fora do trabalho.

Este documento reúne duas análises com fronteiras distintas. As seções 1–9
preservam o diagnóstico de 24/09/2026; a [seção 10](#10-eda-acadêmica-somente-train--08102026)
registra a EDA de 08/10/2026, limitada ao TRAIN processado. As recomendações
pré-TEST da auditoria são históricas: a avaliação final foi concluída depois,
em 18/10/2026, conforme o [protocolo acadêmico](invoice_academic_evaluation_protocol.md).
Nenhum resultado abaixo foi recalculado para esta consolidação.

## 1. Diagnóstico principal

O volume global não é a limitação mais evidente: há **240.000 faturas auditáveis
sem TEST**, incluindo **52.900 positivas** segundo `is_fraud`. O resultado limitado
é compatível com uma **combinação de problemas de referência, representação e
generalização**, não com uma causa única demonstrada.

- **Referência ambígua:** 4.847 registros (2,0196%) combinam `is_fraud=1` com
  `fraud_type=NONE`, ou `is_fraud=0` com outro tipo. A divergência já está na fonte.
- **Mudança de contexto entre períodos:** outubro está ausente do TRAIN e ocupa
  53,43% de VALIDATION; `month_sin` desses registros fica fora da faixa de treino.
  Há também 3.659 faturas em relações fornecedor/departamento não vistas
  (12,20% de VALIDATION; não uma contagem de pares distintos).
- **Features parcialmente alinhadas ao problema:** descrevem valor, frequência,
  cadastro e calendário, mas não representam diretamente os mecanismos relacionais
  ou documentais de vários tipos de fraude.
- **Objetivo do estimador:** Isolation Forest aprende isolamento estatístico, não
  uma função supervisionada de `is_fraud`. Anomalia e fraude não são equivalentes.
- **Representatividade desigual:** só há 50 exemplos TRAIN e oito VALIDATION de
  `DUPLICATE`; todos os fornecedores de VALIDATION já aparecem no TRAIN.
- **Procedência parcial:** código, metadata e atributos do modelo concordam, mas
  falta evidência histórica que vincule o fit original aos bytes atuais dos dados.

**Não foi demonstrado** qual fator responde pela maior parcela do desempenho.
Não há evidência para recomendar simplesmente mais dados do mesmo perfil,
trocar algoritmo ou ajustar threshold antes de esclarecer o problema.

## 2. Fontes, limites e método da auditoria

Foram lidos `train_features.parquet` e `val_features.parquet`, com reconciliação
dos IDs frente a `data/raw/splits.parquet` filtrado para `train`/`val`.
`labels.parquet` e `invoices.parquet` foram consultados com filtro `invoice_id in
IDs autorizados`, antes da materialização das tabelas. Do cadastro de fornecedores,
foram projetados somente ID, país e idade para os fornecedores observados no TRAIN.

Parquets compartilhados podem exigir decodificação de row groups que também
armazenam outras partições. Portanto, o isolamento garantido aqui é dos **registros
materializados/analisados**, não de todos os bytes fisicamente lidos pelo leitor.
Nenhum Parquet separado de TEST foi aberto, nem para hash. Contagens globais
vieram do manifest e dos footers, não de análise de labels ou features de TEST.

O modelo local existente foi carregado somente para inspeção de atributos;
não houve `fit`, `predict`, `score_samples` ou `decision_function`. As métricas
citadas são exclusivamente as já registradas no
[resultado de VALIDATION](invoice_validation_results.md) e no
[JSON existente](../ml/experiments/invoice_validation_v1.json).

Revisão independente, somente leitura, examinou código, documentação e histórico
Git. Não foram executados scripts globais de preparação/auditoria, pois eles
carregam também TEST. As conferências numéricas ocorreram em memória, sem salvar
novos datasets, transformar os arquivos existentes ou executar experimentos.

## 3. Suficiência e representatividade

### 3.1. Volume e distribuição

O manifest e o footer de invoices/labels/splits registram **300.000 faturas**.
A auditoria cobre 210.000 TRAIN + 30.000 VALIDATION. As 60.000 restantes não foram
perfiladas; sua distribuição de classes/tipos não é inferida neste documento.

| Partição auditada | Faturas | is_fraud=0 | is_fraud=1 | Percentual positivo |
|---|---:|---:|---:|---:|
| TRAIN | 210.000 | 163.873 | 46.127 | 21,9652% |
| VALIDATION | 30.000 | 23.227 | 6.773 | 22,5767% |
| Total auditado | 240.000 | 187.100 | 52.900 | 22,0417% |

Contagens por `fraud_type` **e** label, sem substituir um campo pelo outro:

| fraud_type | TRAIN positivo | TRAIN negativo | VALIDATION positivo | VALIDATION negativo |
|---|---:|---:|---:|---:|
| DOC_TAMPER | 1.612 | 38 | 226 | 4 |
| DUPLICATE | 50 | 0 | 8 | 0 |
| GHOST_SUPPLIER | 8.631 | 164 | 1.224 | 30 |
| INFLATED | 3.803 | 81 | 553 | 12 |
| NONE | 3.374 | 162.986 | 446 | 23.087 |
| SPLIT | 28.657 | 604 | 4.316 | 94 |

**OBSERVAÇÃO:** SPLIT responde por 32.973/52.900 (62,33%) dos positivos auditados.
Uma métrica agregada pode ocultar a fraqueza em categorias raras. O recall
anterior de DUPLICATE, 2/8, tem suporte muito pequeno para conclusão robusta;
uma única ocorrência muda esse recall em 12,5 pontos percentuais.

**INTERPRETAÇÃO:** o volume é adequado para estudar uma baseline acadêmica global
nesta fonte, mas não comprova suficiência por mecanismo, população ou operação.
Precisam de aprofundamento: duplicação, novos fornecedores, outros períodos,
estabilidade sazonal, verdade de referência e evidência de processos reais.
Não há tamanho mínimo universal que possa ser garantido apenas contando linhas.

### 3.2. População e tempo

| Aspecto | TRAIN | VALIDATION |
|---|---|---|
| Datas de invoice_date | 01/01/2023–14/09/2023 | 14/09/2023–20/10/2023 |
| Fornecedores distintos | 2.000 | 2.000, todos conhecidos |
| Departamentos distintos | 50 | 50, todos conhecidos |
| Países do cadastro | 126 | 126 |
| Menor número de faturas por fornecedor | 71 | 4 |
| Menor número de faturas por país | 115 | 14 |
| Menor número de faturas por departamento | 4.091 | 549 |
| Moeda | ZAR em todas as linhas | ZAR em todas as linhas |

Há **ordenação temporal observada**, não um split aleatório presumido:
29.307 faturas VALIDATION (97,69%) são posteriores à data máxima de TRAIN.
As demais 693 dividem o dia 14/09/2023 com 137 faturas de TRAIN. Não se comprovou
ordem de evento completa dentro desse dia nem um timestamp de disponibilidade.
A regra que gerou o split oficial não está especificada pelo manifest.

Isso qualifica a ressalva genérica do relatório anterior: existe evidência de
avaliação em período majoritariamente posterior, **mas não** validação temporal
rigorosa ponto-a-ponto, múltiplas janelas, fornecedores novos ou população externa.
As 240 mil linhas não equivalem a 240 mil entidades independentes: fornecedores
e departamentos são compartilhados. Não foram produzidos intervalos de confiança.

## 4. Qualidade e semântica da referência

| Combinação a esclarecer | TRAIN | VALIDATION | Total |
|---|---:|---:|---:|
| is_fraud=1 e fraud_type=NONE | 3.374 | 446 | 3.820 |
| is_fraud=0 e fraud_type diferente de NONE | 887 | 140 | 1.027 |
| Total | 4.261 | 586 | 4.847 |

As taxas são 2,0290% em TRAIN e 1,9533% em VALIDATION. Não há target nulo ou
fora de {0,1}, nem fraud_type nulo. As duas colunas conferem **exatamente por ID**
com a fonte nas duas partições: a divergência semântica não foi introduzida pelo
merge avaliado. IDs são únicos, disjuntos entre TRAIN/VALIDATION e reconciliados
com os registros oficiais, sem fornecedores/faturas perdidos nas leituras.

### Evidências complementares, não uma nova verdade de referência

- Todos os 3.820 positivos com NONE possuem `fraud_tags` vazio e a explicação
  literal `{"reason": "NONE"}`. Logo, esses campos não explicam a positividade.
- Todos os 1.027 negativos com tipo possuem tags não vazias; elas tampouco
  justificam automaticamente trocar o target.
- Há 2.173 TRAIN e 353 VALIDATION com múltiplas tags. `fraud_type` não é sempre
  a primeira tag: essa regra ingênua diverge em 368 e 65 linhas, respectivamente.
  Não se deve presumir exclusividade dos mecanismos nem inventar prioridade.

**HIPÓTESES:** campos podem ter definições diferentes, representar regras versus
decisão final, conter ruído ou refletir etapas distintas de geração/rotulagem.
O manifest fornece versão `v1`, geração `20251214_172643` e contagens, não a
regra de anotação. Não foi comprovada nenhuma dessas hipóteses, nem que a fonte
seja integralmente real ou sintética. Tags/explicações não são confirmação
independente de fraude e continuam proibidas como features.

### Por que a divergência conhecida não explica sozinha os falsos positivos

No resultado **já registrado**, existem 8.935 FP e 3.433 FN. Nos grupos negativos
com tipo diferente de NONE, há apenas **62 FP** (0 DOC_TAMPER + 9 GHOST_SUPPLIER
+ 12 INFLATED + 41 SPLIT); outros **8.873 FP** têm NONE. Entre os positivos NONE,
há 287 FN. Assim, 349 dos 12.368 erros registrados (2,82%) pertencem às combinações
explicitamente divergentes. Esta é uma reconciliação aritmética dos agregados,
não uma reavaliação com labels corrigidas.

A inconsistência conhecida exige esclarecimento, mas **não basta para atribuir
a ela o desempenho global limitado**. Isso também não prova que o restante das
labels esteja correto: ruído adicional sem contradição entre campos é desconhecido.

**RECOMENDAÇÃO:** obter dicionário/regra original; se indisponível, registrar
explicitamente `is_fraud` como referência não verificada da fonte. Uma revisão
documental/amostral futura em TRAIN/VALIDATION deve incluir casos concordantes
e discordantes, sem usar o score para decidir qual label é verdadeira. Não houve
correção, exclusão, reclassificação ou cálculo de métricas alternativas nesta tarefa.

## 5. Integridade tabular e fidelidade das features

Conferências executadas em TRAIN/VALIDATION:

- Nenhum ID de fatura duplicado ou compartilhado entre as partições; cobertura
  exata frente aos IDs oficiais e às leituras filtradas de invoices/labels.
- Zero nulos e infinitos nas 19 features; nenhuma feature constante nas partições.
- Zero linhas integralmente duplicadas após retirar invoice_id da tabela de
  invoices lida; zero vetores idênticos das 19 features dentro ou entre partições.
  Isso não invalida `DUPLICATE`: duplicação de negócio pode diferir em campos.
- Nenhum valor monetário não positivo; submission_hour dentro de 0–23;
  invoice_type limitado a GOODS/SERVICES; payment_terms a NET30/NET60/NET90.
- Campos tabulares centrais de invoices sem nulos. image_path está ausente em
  178.439 TRAIN e 25.621 VALIDATION; ele não integra a matriz tabular atual.
- As **19 colunas foram recalculadas somente em memória** pelas fórmulas do código,
  com estatísticas exclusivamente TRAIN, e comparadas por ID às tabelas existentes.
  **Zero divergências em ambas as partições**, tolerâncias rtol/atol=1e-12;
  a maior diferença absoluta observada foi zero. Nenhum arquivo foi regenerado.

Não há evidência nessa conferência de que erro de junção, missing numérico,
moedas misturadas ou cálculo divergente das fórmulas atuais explique o resultado.
Isso não certifica correção semântica das fórmulas, valores reais ou causalidade.

O manifest anuncia departamentos e behavioural_features, mas
`departments.parquet` e `behavioural_features.parquet` não estão neste checkout.
`images_metadata.parquet` existe; apenas seu schema/footer foi consultado.
`DataBase/` está ausente, sem backup original comprovado nesse local. Recuperar
documentação/arquivos originais é pendência; sua utilidade não pode ser presumida.
Em particular, `image_tamper_flag`, scores de risco e flags da fonte não devem
ser acrescentados automaticamente: exigem comprovação de origem e disponibilidade.

## 6. Procedência do Isolation Forest

| Item | Evidência atual |
|---|---|
| Fonte declarada pelo código | data/processed/train_features.parquet, derivado do Invoice |
| Seleção de entrada | Lista explícita de 19 features; sem IDs, split, is_fraud, fraud_type, tags ou explicações |
| Estimador | IsolationForest |
| Parâmetros explícitos | n_estimators=200; contamination=0.22; random_state=42; n_jobs=-1 |
| Outros parâmetros do artefato | max_samples=auto; max_features=1.0; bootstrap=False; warm_start=False; verbose=0 |
| Atributos ajustados inspecionados | 200 árvores; 19 features na mesma ordem; _n_samples=210000; max_samples_=256 |
| Offset preservado | -0.5211491197816622 |
| Data declarada no metadata | 2026-09-01T17:07:55-03:00 |

A lista completa é a mesma do contrato em
[treinar_modelo.py](../ml/scripts/treinar_modelo.py) e agrupa:

| Grupo | Features existentes |
|---|---|
| Valores | invoice_amount, log_invoice_amount, amount_vs_supplier_mean, supplier_amount_zscore, amount_vs_department_mean |
| Cadastro/frequências | supplier_age_days, supplier_frequency, country_frequency, department_frequency, supplier_department_frequency |
| Condições | payment_terms_days, invoice_type_encoded |
| Calendário | submission_hour_sin, submission_hour_cos, day_of_week_sin, day_of_week_cos, month_sin, month_cos, is_weekend |

**COMPROVADO AGORA:** contrato, parâmetros, tamanho declarado de amostra e estrutura
do artefato são compatíveis com código/metadata. O código atual seleciona só TRAIN
para fit; rótulos não entram no estimador. max_samples_=256 é a subamostra por
árvore, não o tamanho total do dataset. Não foi testado outro valor.

**NÃO COMPROVADO RETROATIVAMENTE:** identidade dos bytes/IDs usados no fit original,
ambiente, commit exato e mapas de agregação daquele momento. _n_samples=210000
não identifica quais 210 mil linhas foram usadas. Git já contém script/metadata
em f9867c0, de 03/09/2026; bb9965a encapsulou o treino/validações sem mudar os
parâmetros/features. O joblib é ignorado e não tem histórico Git. O metadata não
contém hash do treinamento, ambiente ou código original.

Afirmações históricas de que somente Invoice treinou o modelo descrevem o fluxo
declarado, não uma cadeia de procedência certificada. Não se devem preencher
retroativamente campos desconhecidos como se fossem evidência contemporânea.

## 7. Limitações de representação e do modelo

### 7.1. Contexto por mecanismo

| Tipo | Contexto atual | Informação potencialmente necessária, não implementada |
|---|---|---|
| INFLATED | Valores, log, razões e z-score | Item, quantidade, preço unitário, contrato e referência de preço comparável |
| DUPLICATE | Perfil individual | Identidade documental, comparação entre faturas, proximidade e pagamento repetido |
| SPLIT | Valor e frequência fornecedor/departamento | Vínculo entre operações, janelas, total conjunto e limites de aprovação |
| GHOST_SUPPLIER | Idade, frequência e país por frequência | Evidência cadastral/bancária e comprovação de existência/prestação |
| DOC_TAMPER | Sinais tabulares indiretos | Evidência de integridade documental/OCR com disponibilidade e origem auditadas |

Esses campos não constam do contrato de 19 features; vários também não constam
do schema de invoices. A tabela orienta levantamento de requisitos, não autoriza
usar outros datasets sem chaves comprovadas nem criar features novas.

### 7.2. Agregações e calendário

- As médias, desvios e frequências usam todo TRAIN, inclusive a própria linha.
  Não são histórico disponível no instante da fatura. Labels só são associadas
  depois; não há filtro de normalidade no cálculo dessas referências.
- **HIPÓTESE:** valores rotulados como fraude podem influenciar a referência e
  atenuar desvios. Sua contribuição ao desempenho não foi medida.
- Em TRAIN, supplier_department_frequency nunca é zero por construção. Na
  VALIDATION é zero em **3.659 linhas**, sendo 2.842 negativas e 817 positivas.
  Existe mudança de suporte e possível efeito da autorreferência; não se mediu
  quantos desses casos foram alertados. Novidade de relação não equivale a fraude.
- TRAIN tem meses janeiro–setembro; VALIDATION tem **13.970 setembro e 16.030
  outubro**. Para outubro, month_sin=-1 fica abaixo do mínimo TRAIN
  (-0.8660254037844385). São 12.399 negativos e 3.631 positivos em outubro.
  A codificação é matematicamente coerente, mas não elimina mudança de suporte
  sazonal. TRAIN não contém um ciclo anual completo.
- **HIPÓTESE PRIORITÁRIA:** calendário/novidade podem contribuir para alertas de
  normalidade futura como anomalia. Não há predições por linha persistidas nesta
  avaliação para associar diretamente esses grupos aos FP, e não houve nova
  inferência. Não é possível atribuir uma parcela dos 8.935 FP a esses fatores.
- Valores têm representações repetidas (valor, log, razões, z-score); calendário
  também. Isso pode enfatizar determinados sinais, sem demonstrar importância
  causal. supplier_age_days é cadastral estático, sem referência temporal provada.
- Os mapas aprendidos não são persistidos como transformador versionado. Isso
  limita reprodução de inferência futura; não exigiu mudar o pipeline nesta auditoria.

### 7.3. Adequação do estimador

Isolation Forest continua sendo uma baseline coerente para **anomalias tabulares**.
Não foi desenhado para maximizar concordância com os mecanismos da label.
TRAIN contém 21,97% de positivos segundo a referência; isso não transforma
contamination=0.22 em prevalência real ou garantia de detectar essas linhas.
O parâmetro define um offset no treino, não taxa fixa de alertas em outro período.
Ausência de scaling não foi identificada como erro demonstrado deste estimador;
aplicar scaler ou trocar modelo por suposição não resolve a semântica do target.

## 8. Estratégia de avaliação e decisões antes de TEST

### O que VALIDATION permite afirmar

É adequada para uma **baseline restrita ao split oficial**, com associação por ID,
mesma população de fornecedores e período majoritariamente posterior. Labels e
features conferem com suas fontes, e o limiar original foi preservado.

Resultados anteriores: AP=0,31607 versus prevalência/referência 0,22577;
ROC-AUC=0,57976; precision fraude=0,27210; recall fraude=0,49313;
12.275 alertas em 30.000 linhas (40,92%), dos quais 8.935 FP. Há sinal modesto,
mas não utilidade operacional comprovada. São métricas antigas, não recalculadas.

Não permite concluir desempenho com fornecedores novos, fraude comprovada,
generalização externa, ranking estável em outros ciclos ou prontidão de produção.
INFLATED teve recall 1 na avaliação existente, mas também alertou seus 12 negativos;
não é um detector perfeito desse mecanismo. Oito DUPLICATE não sustentam precisão
estatística suficiente por tipo. Múltiplas faturas de uma mesma entidade também
limitam interpretações de independência amostral.

### Critérios de passagem, ainda pendentes

1. **Semântica:** esclarecer `is_fraud`/`fraud_type`/tags e origem da referência,
   ou registrar explicitamente a limitação irredutível. Não corrigir por consenso
   entre campos que podem derivar do mesmo gerador.
2. **Uso pretendido:** definir triagem de anomalias versus classificação de fraude,
   unidade fatura, instante de score e quem revisaria alertas. Não chamar score
   de probabilidade de fraude. Não mudar a metodologia só para elevar a métrica.
3. **Evidência/protocolo:** aceitar explicitamente o limite do artefato legado
   ou planejar uma futura versão rastreável. Não reconstruir procedência fictícia.
4. **Generalização:** decidir se o objetivo é período futuro de fornecedores
   conhecidos ou também novas entidades; explicitar fronteira temporal e falta
   de disponibilidade ponto-a-ponto. Não alterar splits atuais neste diagnóstico.
5. **Utilidade:** manter AP como referência de ranking; definir custos/capacidade
   de revisão antes de eventual seleção em VALIDATION. Nenhum threshold foi
   selecionado e nenhum mínimo arbitrário de F1 foi imposto.
6. **Comparações futuras limitadas:** somente após os itens anteriores, registrar
   hipóteses e orçamento de experimentos em TRAIN/VALIDATION, distinguindo
   calendário, referência de agregação e contexto. Não abrir TEST para decidir.
7. **Congelamento final:** configuração, features, transformações, limiar, métricas,
   hashes e conclusões admissíveis devem preceder qualquer TEST autorizado.

**Recomendação:** não seguir ao TEST ainda. O próximo incremento é um **contrato
metodológico Invoice** que feche semântica e uso pretendido, acrescido da busca
restrita à documentação original de rotulagem. Se a documentação não existir,
registrar a ausência e limitar o objetivo acadêmico à referência disponível.
Só então propor um diagnóstico controlado, pré-definido, das hipóteses de
calendário e autorreferência usando TRAIN/VALIDATION. Isso é recomendação futura,
não experimento executado nem autorização de alteração nesta entrega.

## 9. Verificações, integridade e estado de entrega

Ambiente utilizado apenas para leitura/cálculos de auditoria: Python 3.14.3,
pandas 2.3.3, numpy 2.5.2, pyarrow 25.0.1, scikit-learn 1.9.0 e joblib 1.6.0,
na venv temporária isolada já disponível. Não houve instalação ou alteração de
dependências. Foram executadas asserções de schemas/IDs/labels, reconciliação de
contagens e conferência das 19 fórmulas, não testes de novos modelos.

Hashes SHA-256 identificadores dos arquivos auditados, preservados antes/depois:

| Artefato | SHA-256 |
|---|---|
| train_features.parquet | 41cfbb25baa62c1c201ce5bbc310589fd41656efae9c1d51684716cea0d6e72b |
| val_features.parquet | 564d399b84c01650dfe48c3e99b06bdf88fff686eeb7dd492e568f4cd5be12d2 |
| isolation_forest.joblib | c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b |
| model_metadata.json | ba07485e8dda458e45376b6edc4bd164926efe2c6ca8385cde32f7309db86595 |
| invoice_validation_v1.json | 1218ed395095c69dd8d3439e27b7e1416dfeba68b8f1d9d83328e2c2f27e12f9 |

Esses hashes identificam o estado atual; não certificam o treinamento histórico.
Arquivos compartilhados de fonte e arquivos TEST foram monitorados por tamanho
e mtime, sem hash completo de TEST. Essa é uma garantia de integridade mais
limitada que comparação criptográfica dos arquivos de TEST e não é apresentada
como tal. A verificação final inclui hashes dos scripts/protocolo/EDA protegido
e metadados de arquivos de dados/modelos: **10 hashes e 49 registros de
tamanho/mtime preservados**, sem diferenças. Supplier não foi reavaliado.

Entrega nova: somente este relatório. Os arquivos já modificados/não rastreados
da avaliação anterior permanecem preservados. Sem mudança de código, não foi
repetida a suíte histórica; a qualidade desta etapa foi verificada por revisão
documental independente, conferências de dados e `git diff --check`.
Nenhum dataset, split, modelo, feature, label ou resultado foi alterado;
nenhum notebook, treinamento, inferência, tuning, threshold ou TEST executado.
Nenhum commit ou staging foi realizado.

## 10. EDA acadêmica somente TRAIN — 08/10/2026

Esta análise não repetiu a auditoria das fontes originais nem utilizou VALIDATION/TEST. Suas contagens, correlações e verificações pertencem exclusivamente ao TRAIN processado.

### 10.1. Escopo e execução

Notebook: [01_invoice_eda.ipynb](../ml/notebooks/01_invoice_eda.ipynb).

A análise utiliza exclusivamente `data/processed/train_features.parquet`:
**210.000 faturas, 23 colunas, 19 features**, sem leitura de VALIDATION, TEST ou
raw compartilhados. O notebook foi executado integralmente em 08/10/2026, com
11 células de código e 14 figuras incorporadas (incluindo histogramas e boxplots
de todas as features e comparações por classe).

SHA-256 do único dataset lido:

```text
41cfbb25baa62c1c201ce5bbc310589fd41656efae9c1d51684716cea0d6e72b
```

O hash permaneceu igual após a execução. Uma proteção de I/O externa durante a
validação permitiu somente esse arquivo nas pastas de dados: duas leituras
(leitura analítica e reconferência do hash), nenhuma tentativa de leitura de
outros datasets. Também foram bloqueados carregamento de modelos, fit e
inferência. O notebook não grava dados nem acessa o adaptador TRAIN/VALIDATION.

### 10.2. Colunas efetivamente analisadas e limite da fonte

A lista e ordem das 19 features vêm diretamente de `FEATURES`, em
`ml/scripts/treinar_modelo.py`, cuja importação não executa `main()`. A tabela
de correlações abaixo lista todas elas. Não há nova engenharia de features.

As quatro colunas adicionais têm usos separados:

- `invoice_id`: integridade, unicidade e duplicidades; não é feature.
- `split`: confirmação exclusiva de `train`; não é feature.
- `is_fraud`: referência binária para descrição e associação; não é feature.
- `fraud_type`: frequências e cruzamento descritivo com a referência; não é feature.

**Não disponíveis:** identificadores originais de fornecedor/departamento, país,
datas, horas originais e outros atributos brutos. Não se calcularam quantidade de
fornecedores, departamentos ou países, suas categorias, período ou tendências
temporais. Frequências agregadas e componentes cíclicos não foram invertidos
para reconstruir essas informações. A visão estrutural é do TRAIN processado,
não uma auditoria completa do dataset original.

### 10.3. Qualidade e referência

Não foram encontrados nulos, infinitos nas features, IDs duplicados, duplicatas
exatas das 23 colunas ou vetores repetidos das 19 features. Isso não certifica
integridade semântica nem ausência de problemas nos dados originais.

A referência contém **163.873 registros 0 (78,0348%)** e
**46.127 registros 1 (21,9652%)**. São labels do dataset, sem comprovação de fraude
empresarial. O Isolation Forest continua não supervisionado e voltado à triagem.

O cruzamento disponível no próprio TRAIN mostra 3.374 registros com
`is_fraud=1/fraud_type=NONE` e 887 com `is_fraud=0/fraud_type!=NONE`.
São divergências entre os campos, não motivo para corrigir labels por hipótese.
Há seis categorias de `fraud_type`; DUPLICATE tem somente 50 registros, enquanto
SPLIT possui 29.261 (incluindo ambas as classes). Essa assimetria limita
interpretações por tipo.

### 10.4. Estatísticas e distribuições observadas

O notebook contém count, média, mediana, desvio padrão amostral, mínimo, Q1, Q3,
máximo, nulos e zeros de todas as features; também apresenta assimetria,
cardinalidade, histogramas, boxplots e estatísticas separadas por classe.

- `invoice_amount`: média **7.566,23**, mediana **4.898,56**, desvio padrão
  **8.793,29**, mínimo **70,00**, Q1 **2.640,85**, Q3 **9.178,67** e máximo
  **294.048,72**, nas unidades monetárias da fonte, sem presumir moeda.
  Assimetria à direita de **4,7168**; 15.382 observações (**7,3248%**) ficam
  fora das cercas de 1,5×IQR.
- `log_invoice_amount`, já existente no artefato: distribuição visualmente
  mais simétrica (assimetria **0,0108**). Nenhuma transformação nova foi aplicada.
- `amount_vs_department_mean`, `amount_vs_supplier_mean` e
  `supplier_amount_zscore`: caudas à direita; respectivamente 15.377, 9.524 e
  9.865 observações fora das cercas IQR. Z-score por fornecedor não implica
  normalidade da distribuição global.
- `supplier_age_days`: faixa de 30 a 4.999, com concentração visual no início
  da faixa; `supplier_frequency` concentra-se em torno de 0,000505.
  `department_frequency` ocupa uma faixa estreita (0,019481–0,020510).
  `country_frequency` e `supplier_department_frequency` têm frequências
  discretas/irregulares; não identificam as entidades originais.
- `payment_terms_days` apresenta três valores, com mediana 30 e máximo 90.
  `invoice_type_encoded` e `is_weekend` são binárias; há 115.248 e 150.132
  zeros, respectivamente. Os componentes seno/cosseno apresentam concentrações
  discretas próprias da representação; não permitem avaliar período nesta EDA.

Zeros são contados por igualdade exata: componentes trigonométricos podem ter
valores muito próximos de zero por ponto flutuante. Números arredondados a zero
na tabela não são necessariamente zeros exatos.

**Outlier estatístico não deve ser tratado automaticamente como erro de dados.**
Não houve exclusão, clipping, imputação, scaling ou recodificação.

Na comparação de classes, o valor da fatura tem média maior na classe 1
(**8.067,28** contra **7.425,19**), mas mediana menor (**2.928,06** contra
**5.450,35**) e maior desvio padrão (**14.635,78** contra **6.221,11**).
Essa combinação descreve formas diferentes de distribuição; não comprova um
mecanismo empresarial e não fundamentou mudanças no modelo.

### 10.5. Correlação entre features

Maiores associações positivas observadas:

- Pearson: `invoice_amount × amount_vs_department_mean` = **0,999804**;
  `amount_vs_supplier_mean × supplier_amount_zscore` = **0,991878**.
- Spearman: `invoice_amount × log_invoice_amount` = **1,000000**;
  `invoice_amount × amount_vs_department_mean` = **0,999853**;
  `amount_vs_supplier_mean × supplier_amount_zscore` = **0,993936**.

A associação negativa mais forte é `day_of_week_sin × is_weekend`:
Pearson **−0,786100**, Spearman **−0,790050**. Representações derivadas/cíclicas
compartilham informação; correlação não demonstra causalidade nem justifica,
nesta tarefa, remover features. Matrizes e demais pares estão no notebook.

### 10.6. Ranking de associação com is_fraud

Ordenado por |Pearson|, com sinais preservados. Para referência binária 0/1,
Pearson equivale à correlação ponto-bisserial; Spearman usa postos. Nenhuma
categoria nominal adicional foi codificada.

| Feature | Pearson / ponto-bisserial | Spearman |
|---|---:|---:|
| `supplier_amount_zscore` | -0.226773 | -0.381746 |
| `amount_vs_supplier_mean` | -0.221630 | -0.392119 |
| `log_invoice_amount` | -0.196891 | -0.218852 |
| `invoice_amount` | 0.030232 | -0.218852 |
| `amount_vs_department_mean` | 0.030133 | -0.218734 |
| `month_cos` | -0.019146 | -0.018539 |
| `submission_hour_sin` | 0.013972 | 0.012274 |
| `submission_hour_cos` | 0.012994 | 0.013729 |
| `supplier_age_days` | -0.011511 | -0.012496 |
| `supplier_frequency` | 0.011219 | 0.005823 |
| `month_sin` | 0.008905 | 0.013318 |
| `country_frequency` | -0.007936 | -0.006726 |
| `day_of_week_sin` | -0.004017 | -0.004195 |
| `day_of_week_cos` | -0.002877 | -0.003452 |
| `department_frequency` | 0.002700 | 0.002572 |
| `is_weekend` | 0.001932 | 0.001932 |
| `invoice_type_encoded` | -0.001491 | -0.001491 |
| `payment_terms_days` | 0.001026 | 0.001529 |
| `supplier_department_frequency` | -0.001003 | -0.001035 |

As três maiores associações absolutas são negativas. A maior positiva de
Pearson é `invoice_amount`, mas pequena (**0,030232**). Nessa variável,
Spearman tem sinal negativo (**−0,218852**): as medidas descrevem aspectos
diferentes da distribuição e não devem ser interpretadas como uma regra única.

As outras 16 features possuem |Pearson| < 0,05, critério apenas descritivo para
“próxima de zero”, não teste de independência. Isso não implica ausência de
relações conjuntas ou não lineares. `payment_terms_days`,
`supplier_department_frequency` e `invoice_type_encoded` estão particularmente
próximas de zero nas duas medidas.

`invoice_type_encoded` usa a codificação existente GOODS=0/SERVICES=1.
A interpretação depende dessa codificação, não de uma ordem natural dos tipos.

### 10.7. Limitações e preservação metodológica

- Correlação não é causalidade nem importância de feature do Isolation Forest.
- Não se calculam p-valores nem se presume independência de faturas que podem
  compartilhar fornecedores; seus IDs originais não estão disponíveis.
- Agregações do TRAIN têm limitações ponto-no-tempo e incluem contribuições das
  próprias faturas, conforme a engenharia existente, que não foi alterada.
- `source_reconciled=false` permanece: integridade do Parquet processado não
  certifica procedência independente do treinamento legado.
- Não há extrapolação para VALIDATION, TEST, fraude real, utilidade operacional
  ou retorno financeiro. Os resultados anteriores foram preservados.
- Nenhuma análise selecionou features, modificou parâmetros/threshold, treinou
  ou avaliou um modelo. `is_fraud` não entrou no treinamento.

### 10.8. Reprodução e testes

Procedimento de reprodução registrado naquela entrega, não uma instrução de execução nesta consolidação: abrir o notebook a partir da raiz do projeto ou de `ml/notebooks/` e executar
todas as células com kernel Python do ambiente escolhido. A execução registrada
utilizou Python 3.14.3, pandas 2.3.3, NumPy 2.5.2, PyArrow 25.0.1,
scikit-learn 1.9.0 e Matplotlib 3.10.8. As dependências opcionais já adotadas para
notebooks foram instaladas somente em runtime temporário; requirements e ambiente
principal não foram alterados.

`tests/invoice/test_invoice_eda.py` exercita as funções locais do notebook com
fixtures sintéticas: schema, ordem, IDs, split, referência, infinitos, preservação
de nulos, caminho fixo sem fallback/redirecionamento, estatísticas, correlações,
constantes, alinhamento e comparação por classe. Não exige datasets do projeto.

Comandos de qualidade, em ambiente com as dependências de desenvolvimento:

Validação histórica da entrega da EDA: **26 testes focados aprovados**; regressão completa com
**918 aprovados e 8 ignorados**, estes por indisponibilidade de privilégios de
symlink no Windows. A suíte foi executada com proteção de I/O e registrou zero
tentativas de acesso a datasets/modelos reais. Ruff dos arquivos novos e
`git diff --check` aprovados. A revisão independente não encontrou bloqueadores.

```powershell
python -m pytest -q
python -m ruff check ml/notebooks/01_invoice_eda.ipynb tests/invoice/test_invoice_eda.py
git diff --check
```
