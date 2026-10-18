# Invoice — protocolo acadêmico de avaliação

**Versão:** invoice-academic-evaluation-1.1. **Atualização estrutural:** 13/10/2026.
**Estado de execução atualizado em 18/10/2026:** protocolo aplicado à avaliação
final única em TEST, com 60.000 faturas e as mesmas 19 features, sem fit, tuning
ou novo threshold. O resultado oficial está em
[invoice_test_final_v1.json](../ml/experiments/invoice_test_final_v1.json), separado
do histórico de VALIDATION. Este documento permanece a referência metodológica;
seus critérios não foram alterados em função dos resultados. Em 13/10/2026,
TEST ainda estava fechado e a avaliação dependia de uma tarefa futura explícita.

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
  [preparação da revisão cega](invoice_blind_review_preparation.md). Protocolo,
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
| Triagem e diagnóstico temporal | [Resultados](invoice_triage_results.md) | Enriquecimento do topo; diferenças temporais descritivas |
| IF versus valor | [Comparação](invoice_value_comparison_results.md) | Ganho incremental condicionado ao orçamento; sem superioridade uniforme |

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

A [documentação técnica](invoice_final_executor.md) descreve as responsabilidades
dos módulos. A verificação dos três JSONs históricos é uma ferramenta independente
de rastreabilidade, não requisito para executar uma avaliação normal.

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
