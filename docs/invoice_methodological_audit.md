# Invoice Anomaly — diagnóstico metodológico

**Data:** 24/09/2026. **Estado:** auditoria concluída, sem alteração do pipeline.
**Escopo:** TRAIN e VALIDATION do Invoice; TEST permanece fechado para análise.
Supplier Risk, Purchase e o notebook EDA Supplier ficaram fora do trabalho.

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
