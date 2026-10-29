# Invoice — protocolo acadêmico de avaliação

**Versão:** invoice-academic-evaluation-1.1. **Atualização estrutural:** 13/10/2026.
**Estado de execução atualizado em 18/10/2026:** protocolo aplicado à avaliação
final única em TEST, com 60.000 faturas e as mesmas 19 features, sem fit, tuning
ou novo threshold. O resultado oficial está em
[invoice_test_final_v1.json](../ml/experiments/invoice_test_final_v1.json), separado
do histórico de VALIDATION. Este documento permanece a referência metodológica;
seus critérios não foram alterados em função dos resultados. Em 13/10/2026,
TEST ainda estava fechado e a avaliação dependia de uma tarefa futura explícita.

A consolidação documental das responsabilidades técnicas e do histórico de coordenação abaixo não altera a versão nem os critérios metodológicos do protocolo.

## 1. Decisão e fronteira do estudo

O Invoice permanece um sistema experimental de **triagem de faturas incomuns**,
não um classificador automático de fraude. A unidade é a fatura; o estudo atual
compara rankings retrospectivos de um lote disponível, no split oficial da fonte.
Não demonstra scoring online nem disponibilidade das informações no instante de
emissão, aprovação ou pagamento.

O fechamento acadêmico e a adoção operacional têm requisitos diferentes:

| Finalidade | Evidência admissível | Estado atual |
|---|---|---|
| Benchmark acadêmico retrospectivo | Enriquecimento e recuperação da referência `is_fraud`, composição por tipo e complementaridade das filas | Análises TRAIN/VALIDATION e avaliação final única em TEST concluídas, com registros separados |
| Utilidade para auditoria humana | Julgamentos de pessoas reais independentes, contexto suficiente, capacidade e custo de investigação | Não demonstrada; simulações não satisfazem esse requisito |
| Produção | Validação do uso, disponibilidade temporal, contrato de inferência, segurança e monitoramento | Fora deste incremento; sem liberação |

Aceita-se estudar **o artefato legado identificado**, com suas limitações
declaradas, sem inventar a procedência do fit ou reconstruí-la por um novo treino.
Esse recorte não certifica que os bytes/IDs usados no treinamento original sejam
os atuais. A avaliação final não comprova retrospectivamente que o fit nunca
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
  [histórico de coordenação](#9-preparação-da-revisão-cega--histórico-de-coordenação). Protocolo,
  guia, código, amostra e registros originais não foram substituídos.
- Não reclassificar o manifesto histórico de preparação como conclusão de uma
  revisão humana. Não congelar respostas artificiais como se fossem humanas.

Uma revisão humana real continua possível em etapa própria, mas não foi realizada
nem fica automaticamente autorizada por este documento. Exigirá pessoas reais
independentes, controle de exposição e respostas congeladas antes de qualquer
abertura de labels. Não se presume cegamento de alguém exposto à simulação.

## 3. Evidência científica preservada

As evidências históricas anteriores à avaliação final permanecem preservadas:

| Etapa | Referência | Limite da conclusão |
|---|---|---|
| Avaliação histórica em VALIDATION | [Resultados](invoice_validation_results.md) | Concordância limitada com a referência; não diagnóstico automático de fraude |
| Auditoria da fonte, features e modelo | [Auditoria](invoice_methodological_audit.md) | Semântica e procedência parcialmente desconhecidas; nenhuma correção de labels |
| Triagem e diagnóstico temporal | [Resultados](invoice_validation_results.md#2-triagem-e-diagnóstico-temporal--27092026) | Enriquecimento do topo; diferenças temporais descritivas |
| IF versus valor | [Comparação](invoice_validation_results.md#3-comparação-if--valor--28092026) | Ganho incremental condicionado ao orçamento; sem superioridade uniforme |

Na comparação histórica em VALIDATION, o ganho líquido de positivos do IF foi **−40, +7
e +192**, respectivamente, em 1%, 5% e 10%. Esses números não foram recalculados
nem influenciados pela simulação. Não justificam escolher 10% para implantação.

Identificadores SHA-256 dos três registros existentes, sem alteração de conteúdo:

| Arquivo em `ml/experiments/` | SHA-256 |
|---|---|
| invoice_validation_v1.json | 1218ed395095c69dd8d3439e27b7e1416dfeba68b8f1d9d83328e2c2f27e12f9 |
| invoice_triage_validation_v1.json | ff218d45c54c2376d43b0be46bfda93ba8eb438c8ebd72c395e67fe7cfbdfb3d |
| invoice_value_comparison_v1.json | 9f47cdb9d70ca0cded04aef63cf4e8c1794118b84533fc880f1cba44ab59beea |

Os relatórios/protocolos históricos permanecem datados. Suas recomendações de
próximo passo descrevem o momento da emissão; o estado vigente é este protocolo
e o [roadmap atualizado](implementation_roadmap.md).

`test_used=false` nos registros históricos descreve ausência de avaliação/decisão
em TEST, não certificação de ausência de leitura física dos raw compartilhados.
Os carregadores antigos usavam filtros lógicos; essa limitação não deve ser
apagada nem corrigida retrospectivamente nos JSONs. Na auditoria pré-TEST
não houve leitura, hashing ou avaliação de TEST.

## 4. Especificação prévia para eventual avaliação final

**Especificação anterior à execução, preservada:** quando este plano foi definido,
a avaliação estava planejada, não executada. Foi aplicada em 18/10/2026 sem
revisão dos critérios abaixo. O objetivo previamente definido era verificar
em uma partição ainda não analisada nesta
sequência se o ranking do artefato legado apresenta enriquecimento e diferença
descritiva em relação à regra de valor. Não selecionar um novo modelo ou declarar
um vencedor operacional.

- **IF:** reutilizar `ml/models/isolation_forest.joblib`, sem fit. Parâmetros
  existentes: 200 árvores, contamination=0.22, random_state=42, n_jobs=-1,
  max_samples=auto, max_features=1.0, bootstrap=False, warm_start=False, verbose=0.
  Offset legado preservado: `-0.5211491197816622`.
- **Features/preparação:** mesmas 19 features, mesma ordem do contrato
  [FEATURES](../ml/scripts/treinar_modelo.py); usar os processados existentes.
  Nenhuma imputação, normalização, transformação, feature ou mapa novo. Os mapas
  históricos não são recalculados nem ajustados em VALIDATION/TEST.
- **Score IF:** `-score_samples`, decrescente. Não usar `predict`, alterar o
  offset legado ou escolher um threshold operacional. O avaliador também não
  chama `decision_function`.
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
  ou novos ciclos temporais. O perfil de TEST era desconhecido na definição deste plano.

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

As matrizes de seleção têm linhas de referência [0, 1] e colunas
[não selecionada, selecionada]. Por tipo, aplicar a máscara global, sem criar
uma fila própria. Não interpretá-las como classificação automática de fraude
pelo threshold legado. Grupos sem seleção permanecem visíveis.

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

## 7. Fluxo acadêmico e avaliação final concluída

O fluxo é dados → preparação → EDA → features → treinamento → validação →
avaliação final → resultados. A simplificação estrutural não repete as etapas
científicas concluídas nem muda configuração, features, labels ou resultados.

TEST permaneceu fechado durante a refatoração de 13/10/2026; sua avaliação
ocorreu depois, em tarefa explícita, seguindo as decisões dos itens 4 e 5.
A execução final foi única e não deve ser repetida. Não usar
TEST para EDA, debugging, tuning, escolha de features, threshold ou orçamento.
Não executar a rota real para conferir seu funcionamento.

A avaliação recebe dados e modelo explicitamente, valida schema, IDs,
separação das partições, features, labels, valores e moeda, calcula os rankings
sem fit e grava um JSON normal em destino novo. Incompatibilidades interrompem
o cálculo; não reparar dados nem excluir casos silenciosamente para melhorar
o resultado. Registrar partição, configuração, features, métricas, resultados,
limitações e timestamp. Preservar falhas e resultados já produzidos; não
sobrescrever resultados nem usar a troca de destino para repetir TEST.

### 7.1. Responsabilidades dos módulos

- [invoice_final_evaluation.py](../ml/scripts/invoice_final_evaluation.py)
  calcula a avaliação com dados/modelo explicitamente fornecidos, sem fit.
- [invoice_data_adapter.py](../ml/scripts/invoice_data_adapter.py) valida
  schema, ordem das features, IDs únicos/disjuntos, partições, labels e
  compatibilidade do modelo com metadata e features.
- [invoice_real_inputs.py](../ml/scripts/invoice_real_inputs.py) confere
  cobertura dos IDs, correspondência de labels por ID, ausência de
  sobreposição e consistência de valores monetários/moeda.
- [invoice_real_evaluation.py](../ml/scripts/invoice_real_evaluation.py)
  fornece a entrada pública `run_final_evaluation(output_path, *, frames, model,
  metadata, splits, labels, amounts, configuration, evaluation_id)`. Ela exige
  as partições e fontes em memória e chama `validate_frames()` antes de avaliar
  o frame/modelo retornados e gravar um JSON normal. Falha de validação impede
  scoring e gravação; destino existente é recusado antes da validação. Não aceita
  apenas frame/modelo nem oferece opção para pular a validação das fontes.
- [invoice_historical_evidence.py](../ml/scripts/invoice_historical_evidence.py)
  verifica os três resultados históricos separadamente. Não é requisito para
  avaliar novos inputs.

Os scripts científicos históricos e seus resultados são preservados. Rotas
antigas que leem raw compartilhado continuam impróprias para ensaios no checkout
real: filtrar TRAIN/VALIDATION não isola fisicamente TEST.

### 7.2. Validação antes do scoring

Usar exatamente as 19 features e sua ordem em
[FEATURES](../ml/scripts/treinar_modelo.py), sem labels/IDs como features.
Features são numéricas, finitas e sem nulos; labels binárias válidas; IDs
únicos e partições separadas. Não descartar colunas inesperadas ou corrigir
labels silenciosamente. Alinhar fontes por ID, nunca pela posição das linhas.

### 7.3. Registro da execução final — 18/10/2026

O chamador fornece explicitamente os dados/modelo e o destino. A avaliação final
foi realizada em tarefa própria, após a refatoração, com validação das fontes
concluída antes do scoring: schema, IDs, partições sem sobreposição, ordem das
19 features, labels, valores/moeda e compatibilidade do modelo com a metadata.
TRAIN e VALIDATION participaram das verificações de consistência e separação;
somente os 60.000 registros de TEST foram pontuados. A moeda validada foi ZAR.

O executor utilizou `ml/models/isolation_forest.joblib` e
`ml/models/model_metadata.json`, sem alterar parâmetros ou offset. Houve uma
única chamada de `score_samples`, nenhum fit, nenhum tuning e uma gravação
exclusiva em [ml/experiments/invoice_test_final_v1.json](../ml/experiments/invoice_test_final_v1.json).

- Identificação: `invoice_test_final_v1`.
- SHA-256: `203e9ceb18c028c73eb0e3688eaaa24ead21129aa60d61daf0ae19468512b58a`.

O arquivo contém a comparação IF × valor em 1%, 5% e 10%, matrizes de seleção
globais e por tipo e limitações. Os JSONs históricos de VALIDATION foram
preservados. Não repetir TEST nem usá-lo para debugging, tuning ou exploração.

### 7.4. Verificação técnica isolada

Testes usam fixtures sintéticas e diretórios temporários. Seus resultados não
são evidência científica e não devem ser inseridos em `ml/experiments/`.
Excluir da execução testes que acessam dados reais ou executam células da EDA;
não executar notebooks. A verificação técnica inclui testes científicos
isolados, Ruff, imports e referências documentais, sem avaliar datasets reais.

## 8. Procedência e limites do artefato legado

O resultado final mantém os indicadores previstos no protocolo:

```json
{
  "source_reconciled": false,
  "legacy_training_provenance_certified": false,
  "raw_independence_certified": false
}
```

O hash atual do modelo identifica bytes; não comprova quais dados/IDs,
ambiente ou mapas participaram do fit original nem certifica a ausência de
TEST naquele treinamento. Compatibilidade do modelo e consistência de linhas
não eliminam essa limitação. Uma conferência por ID deve ser registrada
separadamente e não promover esses campos a `true`.

Os raw compartilhados não isolam fisicamente TEST por filtros de linhas. Não
acessá-los no desenvolvimento nem repetir avaliações históricas para verificar
a refatoração. O indicador histórico `test_used=false` descreve ausência de
avaliação/decisão em TEST, sem certificar ausência de leitura física antiga.

A avaliação final foi concluída, sem eliminar estas limitações. Revisão humana real, custos, capacidade
de investigação e adoção operacional permanecem uma trilha separada; nenhum
resultado sintético ou benchmark retrospectivo supre essas evidências.

## 9. Preparação da revisão cega — histórico de coordenação

**Registro de 28/09/2026; teste técnico encerrado, sem revisão humana válida.**
Esta seção é exclusiva da coordenação. Não encaminhar este documento consolidado aos avaliadores; o material neutro permanece no [guia do avaliador](invoice_blind_review_reviewer_guide.md).

A preparação original foi concluída em 28/09/2026. Pacotes em branco, protocolo, guia, código e registros de coordenação foram preservados; o manifesto descreve a preparação, não valida a simulação nem comprova revisão com pessoas reais. Nenhuma label individual foi aberta nessa preparação. As restrições às respostas artificiais estão na seção 2. A localização dos ZIPs preenchidos não foi certificada naquele fechamento.

TEST permanecia fechado nessa data; sua avaliação final posterior, de 18/10/2026, é o estudo independente registrado na seção 7.3. Uma revisão humana real continua exigindo etapa própria.

### 9.1. Protocolo e amostra

[Protocolo aprovado](invoice_blind_review_protocol.md), versão invoice-blind-review-1.0.
Dois avaliadores independentes, mesmas faturas, pseudônimos e ordens próprias.

| Orçamento | Grupo | População elegível | Sorteados |
|---|---|---:|---:|
| 1% | Comuns | 189 | 25 |
| 1% | Exclusivos IF | 111 | 25 |
| 1% | Exclusivos valor | 111 | 25 |
| 1% | Controle não selecionado | 29.589 | 25 |
| 5% | Comuns | 965 | 25 |
| 5% | Exclusivos IF | 535 | 25 |
| 5% | Exclusivos valor | 535 | 25 |
| 5% | Controle não selecionado | 27.965 | 25 |
| 10% | Comuns | 1.832 | 25 |
| 10% | Exclusivos IF | 1.168 | 25 |
| 10% | Exclusivos valor | 1.168 | 25 |
| 10% | Controle não selecionado | 25.832 | 25 |

Total: **300 vínculos sorteados, 295 faturas únicas em cada pacote**.
290 faturas participam de um único estrato sorteado e 5 participam de dois.
Deduplicação apenas na apresentação: a chave preserva todos os vínculos, sem
acrescentar estratos não sorteados. O desenho previa 295 avaliações individuais
por pessoa, 590 no total, não 600 casos independentes. Isso não é contagem de
avaliações humanas realizadas.

A seed de 256 bits está registrada somente na área privada. O sorteio por
HMAC-SHA256 foi fixado previamente, sem labels ou ajuste posterior da amostra.
Todos os fingerprints de top-k foram reconciliados com a comparação anterior.

- Registro anterior ao sorteio/inferência: **2026-09-28T18:49:03.562563+00:00**.
- Pacotes concluídos: **2026-09-28T18:49:05.769797+00:00**.
- SHA-256 do congelamento: `a5ba4bd238c7639298f9749aa6198c3825a7714e1ad7ef7ec37155fd450c7cb8`.
- SHA-256 do manifesto: `24694e35aab8d2649972f7c5a4d16037cc9a41035c947f957674df806e2d7ffe`.

Não sortear novamente ou substituir casos por parecerem difíceis/inadequados.

### 9.2. Entrega originalmente prevista (histórico)

Na pasta local ignorada pelo Git:
`ml/experiments/invoice_blind_review_v1/`.

Em eventual revisão real autorizada, entregar SOMENTE os pacotes originais:

- `avaliador_01.zip` à primeira pessoa: 24118 bytes;
  SHA-256 `c6f8a08702edf75200cb735a34e00b846a4762195898b38c0d1d3def8ddce90b`.
- `avaliador_02.zip` à segunda pessoa: 24156 bytes;
  SHA-256 `ed125fdb01649a8322b7097f10ed273594ab979ed6ded0f6e0126e8543e6902e`.

Cada ZIP contém exatamente:

1. LEIA_PRIMEIRO.md — guia neutro.
2. FICHAS.md — 295 casos e campos de resposta vazios.
3. DECLARACAO.md — identidade/experiência, exposição prévia, independência e conclusão.

Os arquivos Markdown podem ser abertos/editados em editor de texto. Preservar
o ZIP original; cada participante extrai e preenche somente seus próprios arquivos.
Não misturar as duas devoluções, apesar de terem os mesmos nomes de arquivo.

**Não compartilhar** a pasta coordinator, esta seção de coordenação, o protocolo da
coordenação, a seed, o código, os resultados anteriores ou o repositório.
Não entregar os dois ZIPs à mesma pessoa. A separação dos arquivos não substitui
controle de acesso: Git ignorado não é criptografia nem isolamento de permissões.

### 9.3. Conteúdo e qualidade do cegamento

Campos permitidos uniformes: dados tabulares da fatura, pseudônimos de fornecedor/
departamento e quatro descritores contextuais existentes. Nenhum score de anomalia,
posição, estratégia, grupo, orçamento, label, fraud_type, tag, imagem/caminho ou
ID original é mostrado. Os valores monetários preservam os centavos.

As estratégias são mascaradas, mas valores/contexto visíveis podem sugerir a
origem de um caso. Não se garante impossibilidade de inferência. Contexto limitado
e informação insuficiente são resultados possíveis, não motivo de substituição.

A rubrica inclui relevância 0–3 ou insuficiência, motivo concreto, evidência
necessária, facilidade de justificar, esforço estimado e observações. Nenhuma
resposta foi sugerida/preenchida nos pacotes originais gerados. O assistente não
atuou como avaliador humano na preparação; as respostas artificiais posteriores
não modificam esse registro nem validam a revisão.

### 9.4. Validações realizadas na preparação (histórico)

- 14 testes novos sintéticos; suíte completa: **322 passed in 22.34s**.
- Testes cobrem quotas exatas, estratos, deduplicação, reprodutibilidade,
  independência das labels/ordem de entrada, pseudônimos, respostas vazias,
  projeção sem labels, filtros sem TEST, bloqueio de sobrescrita, registro antes
  do scoring e divergências com a seleção anterior.
- Defeito de apresentação monetária detectado por teste que falhou e depois
  passou: removido arredondamento que poderia suprimir centavos. Corrigido antes
  da geração real, sem mudar dados.
- Revisões independentes do protocolo/guia e do código concluídas; nenhum
  bloqueador restante.
- Ruff dos dois arquivos novos: **All checks passed!**
- Ruff global mantém três avisos preexistentes no Supplier Risk:
  I001/RUF100 em final_evaluation.py e I001 em test_final_evaluation_artifact.py.
  Não foram corrigidos por estarem fora do escopo.
- ZIPs íntegros; nomes dos três membros conferidos; hashes internos e externos
  reconciliados com o manifesto. 295 códigos únicos e respostas inteiramente
  vazias em cada pacote; códigos e ordens diferentes entre avaliadores.
- 12 quotas de 25 e os 300 vínculos conferidos sem repetir sorteio/inferência.
- Hashes de inputs/código/protocolo/guia conferidos; seed não exposta nos pacotes.
  A fase real fez somente uma inferência em VALIDATION, sem fit.
- Nenhuma leitura materializada de is_fraud/fraud_type: leitura seletiva de
  features sem labels e fonte tabular filtrada pelos IDs sorteados. Hashes de
  arquivos completos identificam os bytes; não constituem análise de labels.
  A evidência agregada anterior foi usada apenas para procedência/seleções.
- Arquivos dedicados a TEST não foram abertos. Fontes globais tiveram projeção
  e filtros lógicos; row groups físicos podem conter outros splits.

### 9.5. Arquivos da preparação (histórico)

Criados: protocolo, guia do avaliador, esta seção de coordenação,
ml/scripts/preparar_revisao_cega_invoice.py e
tests/invoice/test_invoice_blind_review.py.

Artefatos locais privados: dois ZIPs e coordinator/freeze.json/manifest.json.
O marcador temporário PREPARATION_INCOMPLETE foi removido pelo gerador somente
após conclusão; não restam marcadores de preparação pendente.

Única alteração de arquivo preexistente: .gitignore, acrescentando a exclusão da
pasta privada. As alterações locais anteriores, inclusive os dois notebooks
Supplier, continuam fora do escopo e preservadas. Sem staging ou commit.

### 9.6. Fluxo humano futuro, não executado nem autorizado por este fechamento

O fluxo abaixo não se aplica às devoluções artificiais e não deve ser executado
com elas. Antes de eventual retomada, confirmar pessoas reais independentes,
contexto suficiente e ausência de exposição que comprometa o cegamento.

1. O responsável identifica duas pessoas e entrega individualmente os ZIPs.
2. Cada pessoa declara exposição prévia e avalia de forma independente.
3. Aguardar AMBAS as devoluções; até lá, não produzir comparações ou abrir labels.
4. Conferir completude sem descegar; preservar as respostas de cada autor.
5. Registrar cópias finais exclusivas e um manifesto de congelamento CONJUNTO,
   com hashes/datas das duas respostas e declarações.
6. Só depois desse registro, executar a análise descritiva já prevista. Qualquer
   análise com labels será uma fase complementar posterior, justificada e separada.

O congelamento original é **do sorteio/protocolo**, não das respostas: as fichas
originais foram geradas em branco. Não há congelamento de respostas humanas
válidas nem comando de análise/descegamento nesta entrega.

Procedimento técnico registrado na preparação, sem autorização de reexecução: em uma cópia controlada, o gerador é
`python -m ml.scripts.preparar_revisao_cega_invoice --split val`; nesta pasta ele
recusa nova execução porque a entrega já existe. Uma reprodução idêntica requer
a seed privada e os mesmos hashes, nunca uma seed nova para substituir a amostra.
Não apagar os artefatos existentes para repetir a geração.

O próximo passo recomendado naquele registro era o fechamento acadêmico; o estado vigente está nas seções 1–8 deste documento, não a importação,
comparação ou abertura de labels das respostas simuladas.

Na preparação de 28/09/2026, TEST permaneceu fechado; não houve treino, tuning ou mudança de threshold/algoritmo, dataset, split, label, modelo, Supplier Risk, notebook ou frontend.
