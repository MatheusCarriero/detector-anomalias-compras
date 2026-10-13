# Invoice — contrato acadêmico e próxima avaliação

**Versão:** invoice-academic-evaluation-1.0. **Data:** 28/09/2026.
**Estado:** escopo acadêmico documentado; TEST fechado. Não é registro de uma
execução final, autorização de TEST ou selo criptográfico de congelamento.

## 1. Decisão e fronteira do estudo

O Invoice permanece um sistema experimental de **triagem de faturas incomuns**,
não um classificador automático de fraude. A unidade é a fatura; o estudo atual
compara rankings retrospectivos de um lote disponível, no split oficial da fonte.
Não demonstra scoring online nem disponibilidade das informações no instante de
emissão, aprovação ou pagamento.

O fechamento acadêmico e a adoção operacional têm requisitos diferentes:

| Finalidade | Evidência admissível | Estado atual |
|---|---|---|
| Benchmark acadêmico retrospectivo | Enriquecimento e recuperação da referência `is_fraud`, composição por tipo e complementaridade das filas | Análises TRAIN/VALIDATION concluídas; avaliação final ainda não executada |
| Utilidade para auditoria humana | Julgamentos de pessoas reais independentes, contexto suficiente, capacidade e custo de investigação | Não demonstrada; simulações não satisfazem esse requisito |
| Produção | Validação do uso, disponibilidade temporal, contrato de inferência, segurança e monitoramento | Fora deste incremento; sem liberação |

Aceita-se estudar **o artefato legado identificado**, com suas limitações
declaradas, sem inventar a procedência do fit ou reconstruí-la por um novo treino.
Esse recorte não certifica que os bytes/IDs usados no treinamento original sejam
os atuais. Nem uma avaliação futura comprovará retrospectivamente que o fit nunca
viu determinada linha. A limitação deve acompanhar qualquer resultado final.

## 2. Encerramento do teste técnico da revisão cega

Por decisão do responsável pelo projeto, o teste com dois avaliadores artificiais
está encerrado e seus resultados foram excluídos do estudo acadêmico. Não são
revisão humana, validação científica ou confirmação de utilidade operacional.

- Não importar respostas simuladas, produzir concordância ou incluir seus
  julgamentos em relatórios científicos, JSONs de evidência ou métricas.
- Não usar simulações para escolher estratégia, algoritmo, orçamento, threshold,
  amostra ou hipótese explicativa dos resultados anteriores.
- Os ZIPs preenchidos da simulação devem permanecer fora do repositório. Não
  foram consultados neste fechamento; não se certifica aqui sua localização.
- A preparação original permanece registrada em
  [preparação da revisão cega](invoice_blind_review_preparation.md). Protocolo,
  guia, código, amostra e registros originais não foram substituídos.
- Não reclassificar o manifesto histórico de preparação como conclusão de uma
  revisão humana. Não congelar respostas artificiais como se fossem humanas.

Uma revisão humana real continua possível em etapa própria, mas não foi realizada
nem fica automaticamente autorizada por este documento. Exigirá pessoas reais
independentes, controle de exposição e respostas congeladas antes de qualquer
abertura de labels. Não se presume cegamento de alguém exposto à simulação.

## 3. Evidência científica preservada

As conclusões válidas continuam sendo exclusivamente as já registradas:

| Etapa | Referência | Limite da conclusão |
|---|---|---|
| Avaliação histórica em VALIDATION | [Resultados](invoice_validation_results.md) | Concordância limitada com a referência; não diagnóstico automático de fraude |
| Auditoria da fonte, features e modelo | [Auditoria](invoice_methodological_audit.md) | Semântica e procedência parcialmente desconhecidas; nenhuma correção de labels |
| Triagem e diagnóstico temporal | [Resultados](invoice_triage_results.md) | Enriquecimento do topo; diferenças temporais descritivas |
| IF versus valor | [Comparação](invoice_value_comparison_results.md) | Ganho incremental condicionado ao orçamento; sem superioridade uniforme |

Na comparação já registrada, o ganho líquido de positivos do IF foi **−40, +7
e +192**, respectivamente, em 1%, 5% e 10%. Esses números não foram recalculados
nem influenciados pela simulação. Não justificam escolher 10% para implantação.

Identificadores SHA-256 dos três registros existentes, sem alteração de conteúdo:

| Arquivo em `ml/experiments/` | SHA-256 |
|---|---|
| invoice_validation_v1.json | 1218ed395095c69dd8d3439e27b7e1416dfeba68b8f1d9d83328e2c2f27e12f9 |
| invoice_triage_validation_v1.json | ff218d45c54c2376d43b0be46bfda93ba8eb438c8ebd72c395e67fe7cfbdfb3d |
| invoice_value_comparison_v1.json | 9f47cdb9d70ca0cded04aef63cf4e8c1794118b84533fc880f1cba44ab59beea |

Os relatórios/protocolos históricos permanecem datados. Suas recomendações de
próximo passo descrevem o momento da emissão; o estado vigente é este contrato
e o [roadmap atualizado](implementation_roadmap.md).

`test_used=false` nos registros históricos descreve ausência de avaliação/decisão
em TEST, não certificação de ausência de leitura física dos raw compartilhados.
Os carregadores antigos usavam filtros lógicos; essa limitação não deve ser
apagada nem corrigida retrospectivamente nos JSONs. Nesta auditoria pré-TEST
não houve leitura, hashing ou avaliação de TEST.

## 4. Especificação prévia para eventual avaliação final

**PLANEJADO, não executado:** verificar em uma partição ainda não analisada nesta
sequência se o ranking do artefato legado apresenta enriquecimento e diferença
descritiva em relação à regra de valor. Não selecionar um novo modelo ou declarar
um vencedor operacional.

- **IF:** reutilizar `ml/models/isolation_forest.joblib`, sem fit. Parâmetros
  existentes: 200 árvores, contamination=0.22, random_state=42, n_jobs=-1,
  max_samples=auto, max_features=1.0, bootstrap=False, warm_start=False, verbose=0.
- **Features/preparação:** mesmas 19 features, mesma ordem do contrato
  [FEATURES](../ml/scripts/treinar_modelo.py); usar os processados existentes.
  Nenhuma imputação, normalização, transformação, feature ou mapa novo. Os mapas
  históricos não são recalculados nem ajustados em VALIDATION/TEST.
- **Score IF:** `-score_samples`, decrescente. Não usar `predict`, alterar o
  offset legado ou escolher um threshold operacional.
- **Baseline:** `invoice_amount` decrescente, sem valor absoluto nem câmbio.
  Mesma coorte e valores reconciliados por ID com a fonte; exigir uma única moeda
  não nula. Não presumir que TEST tenha a mesma composição de VALIDATION.
- **Orçamentos:** reportar todos os **1%, 5%, 10%**, sem seleção posterior.
  Para N faturas, K = ceil(N × percentual / 100), limitado a N. Registrar a
  fração efetiva e empates; desempatar por `invoice_id` crescente, não pela label.
- **Referência:** `is_fraud` apenas para avaliação. `fraud_type` apenas para
  composição, preservando NONE, ausências e divergências. Não excluir casos
  difíceis nem inferir uma label substituta.
- **População:** split oficial, estudo retrospectivo na fonte; a hipótese de
  generalização não abrange automaticamente fornecedores novos, outros sistemas
  ou novos ciclos temporais. O perfil de TEST continua desconhecido nesta etapa.

Identidade do modelo: `c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b`.
Metadata: `ba07485e8dda458e45376b6edc4bd164926efe2c6ca8385cde32f7309db86595`.
São identidades do estado atual, não prova da procedência original do fit.

## 5. Métricas e interpretação pré-especificadas

Reutilizar as definições do [protocolo de comparação](invoice_value_comparison_protocol.md):

- Para cada estratégia/orçamento: N, K, positivos, negativos da referência,
  Precision@K = positivos/K, captura = positivos/positivos totais,
  lift = Precision@K/prevalência. Denominador inexistente produz `null`.
- Composição por `fraud_type` entre todas as faturas e entre os positivos;
  participação do tipo dominante e seus empates, sem inventar um corte de
  concentração aceitável após observar dados.
- Comparação pareada: casos comuns e exclusivos, positivos adicionais do IF,
  positivos sacrificados, sobreposição = comuns/K e Jaccard = comuns/união.
  Ganho líquido = positivos exclusivos IF − positivos exclusivos valor.
- Diferenças de Precision@K e captura à mesma capacidade. A união serve apenas
  para reconciliação, não é uma estratégia adicional de igual custo.

Relatar todos os orçamentos, inclusive saldos negativos ou nulos. Ganho líquido
positivo indica recuperação incremental **da referência** naquele orçamento,
não vantagem uniforme, significância estatística ou utilidade empresarial.
Não impor agora uma meta numérica de aprovação, ocultar categorias raras ou
redefinir o objetivo para favorecer os resultados. Não há seleção por métrica
isolada. Neste escopo a análise é descritiva, sem novos testes de significância
ou intervalos que suponham faturas/top-k independentes.

## 6. Limitações que permanecem

- `is_fraud` e `fraud_type` têm divergências documentadas, com origem/regra de
  rotulagem não comprovadas; nenhum dos dois é verdade empresarial certificada.
- Fit legado sem vínculo histórico certificado aos bytes/IDs, ambiente e mapas
  originais. O hash atual do modelo não sana essa lacuna.
- Estatísticas sobre todo TRAIN, incluindo a própria linha; ausência de garantia
  ponto-a-ponto de disponibilidade temporal e de transformador persistido.
- População de fornecedores conhecidos na avaliação anterior, períodos parciais,
  mudança de distribuição, dependência entre faturas e suporte pequeno de alguns
  tipos. VALIDATION já foi consultada repetidamente.
- Ausência de contexto documental, preços/contratos e relações suficientes para
  investigar todos os mecanismos. Maior anomalia não implica maior gravidade.
- Ausência de revisão humana válida, custo observado, capacidade real e benefício
  empresarial medido. A simulação não reduz nenhuma dessas limitações.

Não alegar fraude comprovada, causalidade, probabilidade de fraude, retorno
financeiro, operação online validada ou prontidão de produção.

## 7. Condições de acesso a TEST — ainda não satisfeitas

O presente fechamento **não abre TEST**. Antes de qualquer futura execução:

1. Registrar revisão/aceitação deste escopo restrito e autorização explícita de
   execução, sem alegar certificação retroativa do fit. Não extrapolar a autorização
   para recalcular resultados, repetir a avaliação ou realizar outra rodada de seleção.
2. Utilizar a ligação técnica `invoice_real_evaluation.run_authorized_evaluation`,
   implementada e exercitada somente com fixtures sintéticas: partição autorizada,
   IDs únicos/disjuntos, alinhamento, 19 features, moeda/valores, ausência de fit,
   cálculos, empates, falhas e recusa de sobrescrita. Isso não equivale a uma
   autorização real. Não relaxar comandos históricos: recusam o checkout real
   mesmo com split `val`, pois filtros não isolam fisicamente TEST.
3. Persistir antes do primeiro acesso a TEST um registro exclusivo contendo
   este protocolo, configuração completa/lista ordenada de features, hashes de
   código/modelo/metadata/evidências anteriores, versões, partição autorizada e
   caminhos de entrada/saída. Não apresentar este Markdown mutável como selo.
   Hashes do conteúdo de TEST e dos IDs lidos só serão obtidos **após** a abertura
   autorizada, associados ao registro anterior; não inspecioná-los para planejar.
   O contrato técnico 1.3 exige `historical_evidence_sha256`: o gate verifica os
   bytes dos três JSONs do item 3, seus vínculos internos e a configuração contra
   pins fixos em `invoice_historical_evidence.py`. O hash deste Markdown não
   substitui essa verificação. Integridade histórica não certifica o fit legado.
4. Registrar o início antes da leitura/scoring e impedir nova avaliação ou
   sobrescrita se já houver registro de início/conclusão. Diante de falha após
   acesso, conservar o estado e relatar o incidente; não apagar marcadores para
   reexecutar ou afirmar que TEST permaneceu fechado.
5. Na única execução autorizada, validar a coorte sem exclusões silenciosas,
   sem reparos automáticos de dados e sem fit. Incompatibilidade de schema,
   IDs, valores ou moedas interrompe a execução e exige registro do desvio,
   não escolha de uma nova população para obter resultado.
6. Publicar todas as métricas previstas com hashes e limites. Nenhum resultado
   de TEST realimenta orçamento, threshold, features, modelo ou novo experimento.

## 8. Entrega atual e próximo passo

**CONCLUÍDO nesta etapa:** reconciliação documental do estado Invoice, exclusão
da simulação por decisão explícita e contrato acadêmico acima. Nenhuma resposta
simulada, inferência, treinamento ou análise nova de dados foi realizada.

**Atualização técnica de 30/09/2026:** o executor sintético e o adaptador separado
TRAIN/VALIDATION foram implementados e verificados. O gate pré-acesso descrito
abaixo complementa o contrato; não constitui avaliação, congelamento real emitido
ou autorização já concedida. A execução real continua bloqueada até o cumprimento
de todas as condições. Revisão humana/adoção operacional permanecem trilha separada;
não se exige fingir que foram realizadas para concluir o benchmark.

## 9. Contrato de procedência para a avaliação real

Os seguintes campos devem permanecer explicitamente falsos no congelamento, no
recibo de autorização e em qualquer evidência final futura:

```json
{
  "source_reconciled": false,
  "legacy_training_provenance_certified": false,
  "raw_independence_certified": false
}
```

A origem do treinamento legado não pode ser certificada criptograficamente.
O hash do modelo identifica o artefato atual; não certifica os dados/IDs que
participaram do fit original, nem que TEST esteve ausente desse treinamento.

Os raw compartilhados têm um único row group por arquivo. Filtrar linhas não
prova isolamento físico: esses arquivos não podem fundamentar uma declaração
de independência de TEST. Não existe fonte independente segura para reconciliar
toda a coorte mantendo a fronteira atual. `source_reconciled=false` não pode ser
omitido, convertido em sucesso ou substituído por uma declaração de aprovação.
Neste contrato de avaliação real, o campo expressa a ausência de comprovação
independente da origem, não apenas o resultado de um join por ID. Uma eventual
verificação futura de consistência de linhas deverá ter registro separado,
sem ser apresentada como certificação da procedência do fit.

A aceitação explícita dessa limitação autoriza, no máximo, o escopo restrito do
benchmark legado; não produz evidência de procedência. A avaliação final deverá
registrá-la junto das métricas, sem alegar certificação retroativa do fit.

Isso não dispensa as validações técnicas do item 4: IDs, schema, ordem das
features, moeda e igualdade dos valores. Uma futura reconciliação de linhas,
eventualmente realizada dentro de uma abertura formalmente autorizada, verifica
consistência dessas linhas, não independência histórica do treinamento. Não deve
promover nenhum dos três campos acima a `true`. A rota de leitura autorizada
registra separadamente `source_rows_consistent`, sem reclassificar procedência.

## 10. Autorização formal e gate pré-acesso

A configuração admissível é a definida neste protocolo: artefato/model metadata
identificados no item 4, nove parâmetros, 19 features na ordem original, offset
legado `-0.5211491197816622`, todos os orçamentos 1%/5%/10% e seleção@K. Não se
escolhe um threshold novo nem se relaxa a configuração em função dos resultados.

O gate de `invoice_final_evaluation.py` exige três documentos JSON estritos:
congelamento portátil, contexto concreto de execução e autorização. Os SHA-256
esperados devem ser fornecidos externamente. A autorização precisa vincular os
bytes exatos do congelamento **e do contexto**, a configuração canônica, o
destino exclusivo, a partição `test`, a finalidade acadêmica e o
reconhecimento explícito dos três limites de procedência. Ausência, divergência,
configuração incompatível ou tentativa anterior bloqueiam o gate.

O contrato técnico 1.3 exige `expires_at` com fuso e a cronologia
`congelamento <= contexto <= emissão <= presente < expiração`. O congelamento e a autorização
devem declarar o escopo `processed_test_and_physical_shared_raw_for_consistency_only`.
Ele vincula os quatro inputs pré-acesso, o processado TEST e os três raw de
splits, labels e faturas. Exige também `authorized_operation=evaluate_and_publish_once`
e os três hashes de evidência histórica no freeze. **Contratos reais antigos 1.0/1.1/1.2
não habilitam a nova rota e não são migrados automaticamente.** Não foi emitida
autorização real nesta etapa.
O escopo reconhece que ler os raw acessa arquivos físicos compartilhados; filtros
não garantem isolamento. Seus hashes de conteúdo, assim como o de TEST, só podem
ser obtidos após uma futura abertura expressamente autorizada.

O responsável pelo projeto deverá aprovar a execução em etapa futura e fornecer
a referência/hash confiável da autorização por canal independente. **Calcular o
hash automaticamente do próprio arquivo apresentado não prova aprovação.** Os
hashes comprovam integridade dos bytes, não assinatura digital ou identidade civil
do aprovador; essa identidade/referência depende do procedimento externo. Não há
emissor automático de autorizações reais, credencial embutida ou flag de liberação.

O gate cria somente um recibo exclusivo pré-acesso, preservando configuração,
hashes e limitações; não lê dados, não desserializa modelo e não faz scoring.
`test_used=false`, `data_access_performed=false` e
`evaluation_started=false` distinguem esse recibo de uma avaliação iniciada.
O campo `real_execution_available=true` do recibo 1.2 indica apenas que há uma
API implementada para consumo explícito; não indica que a execução começou.
Um recibo existente, inclusive parcial, impede nova tentativa no mesmo destino;
cópias do congelamento para outro destino não habilitam repetição. Não apagar
registros para tentar novamente. O controle é local, não proteção contra remoção
deliberada dos arquivos ou emissão de uma nova autorização pelo responsável.

`invoice_real_inputs.validate_authorized_inputs` consome o recibo em chamada
separada e explicitamente iniciada. Revalida os quatro documentos (freeze, contexto, autorização e recibo) e seus hashes,
escopo, expiração, configuração e código antes de acessar inputs; cria marcador
exclusivo de início antes da leitura. Confere bytes, modelo, 19 features,
coortes/splits, labels, valores e moeda, sem fit, scoring ou métricas. O recibo
sozinho nunca inicia essa operação. Sucesso produz somente registro técnico de
inputs validados; falha conserva a tentativa, sem retry ou limpeza automática.

Somente fixtures artificiais exercitaram essas APIs. Não foi emitida autorização
real; implementação e testes não autorizam TEST. A API pública `evaluate_frame`
continua exclusivamente sintética. A ligação explícita é a API separada
`run_authorized_evaluation(..., start_evaluation=False)`: exige início explícito,
documentos/pins válidos e recibo ainda não consumido; valida inputs internamente,
registra início de scoring, calcula uma vez e publica bundle no destino congelado.
Não aceita frame/modelo/métricas/destino substitutos do chamador. O verificador
do bundle não reabre datasets nem recalcula métricas.

Continuam faltando congelamento real exclusivo, aceitação das limitações e
autorização humana por canal independente. Não iniciar a rota de inputs como
dry-run real: ela já abre dados e consome a tentativa, mesmo sem scoring; uma
tentativa input-only não pode ser retomada como avaliação. Falhas preservam os
registros parciais, sem nova execução automática. Nenhuma decisão metodológica
ou resultado científico foi alterado pelo fechamento técnico de 05/10/2026.

## 11. Separação portátil/concreta — contratos técnicos vigentes

A alteração é de rastreabilidade, não de metodologia. Mantém modelo, 19 features
ordenadas, offset, orçamentos, labels e limitações. Não emite congelamento formal
definitivo nem autorização humana; não autoriza um ensaio da rota real.

- **Freeze portátil `invoice-portable-freeze/1.1`:** UUID, data, configuração,
  versões exatas, allowlists relativas e hashes de código/protocolo, modelo,
  metadata, TRAIN/VALIDATION e três evidências históricas. Não contém
  `project_root`, `run_dir`, destino ou caminhos pessoais; `test_authorized=false`.
  A revisão 1.1 inclui os hashes de `requirements.txt`, `requirements-dev.txt`
  e `.python-version`. Todos os pins ativos são registrados e confrontados com
  os metadados instalados e com esses descritores; são 22 distribuições ativas
  no Windows, além de Python. Não há instalação nem importação de cada pacote
  para essa conferência. Freeze portátil 1.0 é recusado, sem migração silenciosa.
- **Contexto `invoice-execution-context/1.0`:** UUID, data, hash e caminho do
  freeze, `project_root`, `run_dir`, oito inputs absolutos e destino exato
  `run_dir/results`. Deve estar em `run_dir/context.json`. Os quatro hashes
  pré-acesso devem corresponder ao freeze; hashes de TEST/raw são obrigatoriamente
  `null`. Sua identidade de conteúdo não foi atestada antes da autorização.
- **Autorização `invoice-real-authorization/1.3`:** vincula SHA-256 do freeze,
  SHA-256 do contexto, SHA-256 da configuração e destino, além de escopo,
  operação, responsável externo, referência, emissão e expiração. SHA-256
  assegura integridade, não autentica a identidade do aprovador.
- **Recibos e publicação:** o contexto é reconferido antes dos acessos, do
  cálculo e da publicação. Seu hash e destino ficam nos recibos/evidência e o
  documento integra o bundle. Verificar um bundle não executa nem autoriza nada.
  O manifesto real 1.2 tem hash fixado antes da escrita; os bytes são conferidos
  no staging e no destino. A publicação exige `publication_complete.json` 1.0
  externo ao staging, vinculado ao manifesto e aos documentos autorizados,
  criado exclusivamente ao concluir com autorização vigente. `failure.json`
  ou ausência de conclusão impedem aceitação; renomear o staging não basta.
  São garantias locais de verificação, não atomicidade contra escrita arbitrária
  nem prova criptográfica de identidade humana; ver o [contrato técnico](invoice_final_executor.md).

Copiar o freeze preserva sua identidade portátil, mas não desloca o contexto nem
autoriza reexecução. Mudar raiz, inputs, caminho do freeze, run_dir ou destino
exige outro contexto e nova aprovação independente. Os registros anteriores
permanecem preservados. Não há conversão silenciosa de contratos reais antigos.

Integridade dos arquivos e compatibilidade do contrato são verificáveis; a
independência do treinamento legado não é. `source_reconciled=false` e os outros
dois limites de procedência continuam obrigatórios. Não usar os raw compartilhados
para contornar essa limitação. O bloqueio local depende da preservação dos
marcadores; não substitui custódia externa nem protege contra operador privilegiado.
