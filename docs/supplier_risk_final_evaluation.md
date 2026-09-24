# Supplier Risk — avaliação final acadêmica

## Estado real e checklist de execução

**Avaliação final concluída em 19/09/2026; fechamento documental em 20/09/2026.**
TEST foi utilizado uma única vez nesta execução registrada, após congelamento,
para avaliar o candidato e a baseline. Não houve tuning, calibração, alteração
de threshold, features ou modelo após observar TEST. Esta etapa de encerramento
somente confere evidências existentes; não repete treinamento ou avaliação.

O usuário autorizou uma avaliação final única, sem tuning e sem commit.
O protocolo utilizado exige ajuste somente em TRAIN, não TRAIN + VALIDATION.
Foram utilizados 16.894 fornecedores no ajuste e 3.679 na avaliação final.
Nenhum notebook histórico, dataset, split, ML-Ready ou modelo existente foi
alterado por este encerramento. A alteração local preexistente do notebook 01
permanece integralmente preservada e fora do escopo.

- [x] Revisar protocolo, critérios de seleção e saídas históricas, sem executar
  notebooks nem abrir dados TEST.
- [x] Implementar e verificar com fixtures sintéticas o suporte mínimo exigido
  pelos gates de engenharia: carregador protegido, métricas reutilizáveis,
  contrato final separado e publicação consistente da execução.
- [x] Registrar configuração, versões e hashes antes de qualquer leitura TEST;
  revisar o congelamento e o código de execução.
- [x] Ajustar um único candidato em TRAIN; calcular a maioria somente em TRAIN.
- [x] Avaliar candidato e baseline uma vez em TEST, publicar registros e métricas
  verificáveis, sem reabrir seleção e sem serializar modelo de produção.
- [x] Consolidar resultados, integridade e estado Git. Não repetir a suíte de
  196 testes ou o Ruff completo já aprovados; testar somente o suporte novo.

## Configuração metodológica escolhida antes de TEST

**Logistic Regression, cenário C, nove features.** A regra predefinida na seção
13.6 de [supplier_risk_model.md](supplier_risk_model.md) seleciona maior
F1-macro em VALIDATION; desempata por balanced accuracy e depois D/B/C/A.
As saídas já existentes do notebook 02 mostram matrizes idênticas para LR A/C:
`[[979, 131], [81, 2348]]`. Portanto o empate é exato nas duas métricas, não uma
inferência a partir de valores arredondados. C precede A no desempate.
As condições de utilidade e os ICs bootstrap contra a baseline já foram
satisfeitos nessa rodada. Nenhuma nova consulta aos dados VALIDATION é necessária.

Features, na ordem do contrato C:

1. `financial_stability_score`
2. `on_time_delivery_rate`
3. `defect_rate`
4. `geopolitical_risk_index`
5. `lead_time_days`
6. `alternative_suppliers_available`
7. `contract_length_months`
8. `environmental_compliance`
9. `previous_disruptions`

`supplier_record_count` fica fora desta configuração em memória, sem alterar
nenhum arquivo de features. `supplier_id`, `Risk_Level` e equivalentes nunca
entram em X.

Pipeline: `SimpleImputer(strategy="median") → StandardScaler → LogisticRegression`.
Parâmetros LR: `C=1.0`, `solver="lbfgs"`, `max_iter=1000`, `random_state=42`,
`class_weight=None`, demais defaults da mesma versão scikit-learn 1.9.0 usada
na rodada anterior; todos os parâmetros efetivos constam de `freeze.json` e do
registro `LogisticRegression_C.json`. O manifest registra hashes dos resultados.
Sem calibração, tuning, seleção adicional ou otimização de threshold.
Regra de classificação: `predict()` binário padrão, corte 0,5 (empate em 0,5
favorece classe 0), mantendo a regra da rodada anterior.

Ajuste somente em TRAIN. O ML-Ready já contém imputação mediana aprendida em
TRAIN; a etapa SimpleImputer do Pipeline foi neutra nesses dados sem nulos,
como na comparação que selecionou C. O scaler foi ajustado somente em TRAIN.
Esta avaliação não é CV e não reutiliza a imputação global de TRAIN em folds.
A baseline prediz a classe mais frequente de y_train, não de TEST.

## Métricas congeladas

F1-macro (principal), balanced accuracy, precision/recall/F1 e suporte das
classes 0/1, matriz de confusão na ordem [0, 1] (linhas reais, colunas previstas),
ROC-AUC e **Average Precision (AP, average_precision_score)** com score contínuo
da classe 1. AP não é integração trapezoidal da curva PR. Accuracy é apenas
complementar; zero_division=0, sem omitir classes não reconhecidas.
Nenhum parâmetro, feature ou modelo foi escolhido após observar TEST.
O resultado está encerrado, sem nova rodada ou seleção nesse TEST.

## Interpretação e limitações pré-registradas

O uso é exclusivamente acadêmico: medir classificação do Risk_Level fornecido
pelo dataset. Não é validação de risco empresarial, fraude, falhas futuras ou
ruptura. Origem e regra de Risk_Level continuam desconhecidas.

O índice geopolítico é mantido provisoriamente no cenário selecionado, com origem,
fórmula e referência temporal não comprovadas. Sua forte contribuição observada
pode refletir particularidades da geração dos dados ou proxies; não comprova
causalidade. A contagem excluída não representava histórico temporal comprovado.
Compliance acima de 100 e lead time zero permanecem sem correção automática.
Não há validação temporal ou externa. Probabilidades não calibradas representam
somente pertencimento estimado à classe 1, não probabilidade real de falha.

## Suporte implementado e limites do encerramento

O contrato de desenvolvimento 1.0.0 permanece restrito a TRAIN/VALIDATION.
A avaliação final utiliza API/schema distintos, ligados ao hash do congelamento,
sem liberar TEST no caminho de desenvolvimento. Marcadores exclusivos bloqueiam
reexecução automática no mesmo diretório, desde antes do fit e da abertura de
TEST. Não houve falha registrada nem retreinamento automático.

Artefatos foram preparados em diretório exclusivo e publicados como conjunto
apenas após validação, sem sobrescrever uma execução existente. Esta proteção
cobre a avaliação final, não declara corrigidos os produtores históricos de
features/ML-Ready nem concluído o roadmap de produto.

## Verificação do executor antes do congelamento

Foram aprovados **43 testes sintéticos** exclusivamente dos arquivos
`test_final_evaluation.py` e `test_final_evaluation_artifact.py`, na etapa anterior
ao congelamento. Cobrem rejeição de TEST pelo carregador de desenvolvimento,
alinhamento, hashes, contrato final, integridade dos bytes consumidos,
configuração divergente, falhas, bloqueio de reexecução e publicação do conjunto.
Esse resultado histórico não é uma nova execução de testes neste fechamento.
Não foram repetidos pytest, os 196 testes anteriores, o Ruff completo ou notebooks.
A revisão estática adicional identificou uma lacuna específica de cobertura,
registrada nas pendências abaixo, sem evidência de invalidação do resultado real.

O congelamento usa escrita exclusiva e digest ancorado antes da avaliação.
Trata-se de imutabilidade operacional e detecção de alteração, não de assinatura
digital ou armazenamento inviolável. O executor compara o digest recebido
externamente; não aceita simplesmente recalculá-lo depois de modificar o arquivo.

## Evidência de congelamento anterior à abertura de TEST

Registro exclusivo criado em **2026-09-19T13:20:53.140325Z**, sem fit e sem leitura
dos Parquets TEST:
[`freeze.json`](../ml/supplier_risk/experiments/final_evaluation_v1/freeze.json).

SHA-256 ancorado antes da execução:

```text
70817bc7d270f4fb5d1d7ce27bc48920babe41cd72c317ded7bda300da7db151
```

Protocolo: `supplier-risk-1.0/final-academic-1.0`. Base Git:
`bb9965a735f2269aa1540b0c979b763fb2187fde`; as mudanças ainda não commitadas do
executor e da API são identificadas pelos seus hashes, não atribuídas ao commit.
Os hashes do protocolo, das saídas históricas da baseline, dos inputs TRAIN,
do metadata e das atribuições de split também constam do registro. Os hashes
esperados de TEST foram copiados do metadata do produtor, sem abrir TEST.

O registro congela TRAIN com **16.894 fornecedores**, baseline **classe 1**,
partições preexistentes e seus fingerprints, parâmetros efetivos de todas as
etapas e orçamento de um fit/uma avaliação final. As versões de execução são
Python 3.14.3, pandas 2.3.3, numpy 2.5.2, pyarrow 25.0.1 e scikit-learn 1.9.0,
no ambiente isolado já utilizado na validação científica. O metadata histórico
do produtor informa pandas 2.2.2; ele foi preservado, sem regenerar ML-Ready ou
afirmar que o ambiente de produção dos dados era idêntico ao desta avaliação.

O hash acima foi passado literalmente como `expected_freeze_sha256` na única
execução autorizada. Sua conferência posterior não altera a âncora nem autoriza
aceitar um congelamento diferente. A documentação identificada dentro do freeze
e o código congelado não foram editados após a execução.

## Resultado observado no TEST

Fonte oficial: [`results/metrics.json`](../ml/supplier_risk/experiments/final_evaluation_v1/results/metrics.json).
Os valores abaixo são transcrições arredondadas a cinco casas decimais; o JSON
preserva a precisão original. Nenhuma métrica foi recalculada neste fechamento.

| Métrica | Logistic Regression C | Baseline majoritária |
|---|---:|---:|
| F1-macro (principal) | 0,92883 | 0,41070 |
| Balanced accuracy | 0,92460 | 0,50000 |
| ROC-AUC | 0,98630 | 0,50000 |
| Average Precision (classe 1) | 0,99385 | 0,69693 |
| Accuracy (complementar) | 0,94047 | 0,69693 |

Average Precision é a implementação `average_precision_score`, não a área
trapezoidal sob a curva PR. A baseline sempre prediz classe 1, definida pela
maioria de TRAIN. Seu score constante não discrimina fornecedores: ROC-AUC é
0,5 e AP equivale à prevalência da classe 1 em TEST.

### Métricas por classe

| Estimador | Classe | Precision | Recall | F1 | Suporte |
|---|---:|---:|---:|---:|---:|
| Logistic Regression C | 0 | 0,91636 | 0,88430 | 0,90005 | 1.115 |
| Logistic Regression C | 1 | 0,95044 | 0,96490 | 0,95762 | 2.564 |
| Baseline majoritária | 0 | 0,00000 | 0,00000 | 0,00000 | 1.115 |
| Baseline majoritária | 1 | 0,69693 | 1,00000 | 0,82140 | 2.564 |

As métricas indefinidas de precision/F1 da classe não prevista pela baseline
foram registradas como zero (`zero_division=0`), sem excluir essa classe.

### Matrizes de confusão

Linhas representam a classe real; colunas, a prevista. Ordem das classes: [0, 1].

| Logistic Regression C | Previsto 0 | Previsto 1 |
|---|---:|---:|
| Real 0 | 986 | 129 |
| Real 1 | 90 | 2474 |

| Baseline majoritária | Previsto 0 | Previsto 1 |
|---|---:|---:|
| Real 0 | 0 | 1115 |
| Real 1 | 0 | 2564 |

Considerando classe 1 como positiva, o candidato registrou 129 falsos positivos
e 90 falsos negativos. Ambas as matrizes totalizam 3.679 fornecedores.

## Interpretação do resultado e limites da conclusão

**RESULTADO OBSERVADO:** a configuração previamente escolhida superou a baseline
em F1-macro e balanced accuracy e reconheceu ambas as classes, atendendo ao
critério mínimo de utilidade no experimento. O recall da classe 0 (0,88430) é
inferior ao da classe 1 (0,96490); o resultado não se resume à previsão da maioria.

**INTERPRETAÇÃO:** há evidência de capacidade classificatória para a label
Risk_Level desta fonte e desta divisão por fornecedor. O TEST avalia uma escolha
anterior; não foi usado para eleger um novo vencedor, revisar features, pesos,
threshold ou hiperparâmetros. Não houve experimento condicionado ao resultado.

**LIMITAÇÕES:** a origem da label e do índice geopolítico permanece desconhecida.
Reprodução de padrões da geração do dataset ou proxies continua uma hipótese,
não uma conclusão causal. Não há validação temporal/externa ou comprovação de
risco empresarial, fraude, ruptura ou falha futura. `predict_proba()` representa
pertencimento estimado à classe 1; não probabilidade real de ocorrência.
Probabilidades não foram calibradas. A CV histórica foi A/D, não C. Não foram
produzidos novos intervalos de confiança ou testes de significância no TEST.
O resultado não transforma o estimador em modelo de produção.

## Cronologia registrada e execução única

| Evento | Horário UTC em 19/09/2026 |
|---|---|
| Congelamento | 13:20:53.140325 |
| Reserva exclusiva da execução | 13:21:55.380117 |
| Fit concluído e estado salvo | 13:21:55.497130 |
| Marcador anterior à abertura de TEST | 13:21:55.497720 |
| Métricas concluídas | 13:21:55.687750 |

Os JSONs registram `classifier_fits=1`, `test_evaluations=1` e
`test_used_for_selection=false`. O estado pré-TEST registra 16.894 linhas vistas
pelo scaler. Os dois estimadores comparados possuem 3.679 predições sobre os
mesmos IDs e targets. A baseline é uma regra constante, sem segundo ajuste de
classificador. Os registros são compatíveis com uma única execução autorizada;
esta conferência de integridade não constitui outra avaliação.

Existem `execution_started.json`, `fitted_state_before_test.json` e
`test_access_started.json`, preservados como evidência e bloqueio de repetição.
Não existem `failure.json` ou `results.pending`; `results` contém exatamente
os três arquivos previstos pelo manifest e o próprio manifest. Marcadores
`*_started` não representam execução pendente quando acompanhados desse conjunto
final publicado. Não devem ser apagados para permitir nova execução.

## Conferência ampliada de integridade — 20/09/2026

- SHA-256 do congelamento igual à âncora anterior à avaliação.
- Todos os oito JSONs inventariados; hashes dos três resultados conferidos
  contra o manifest, sem arquivo ausente ou inesperado.
- Ambos os registros validados por `verify_final_evaluation_record`, schema
  `supplier-risk-final/1.0.0`, incluindo digest, IDs únicos, probabilidades,
  fingerprints de split e vínculo ao congelamento.
- Features, parâmetros, versão do código, fontes congeladas, contagens e
  cronologia coerentes entre freeze, registros, estado ajustado e métricas.
- Matrizes confrontadas com as contagens das predições **já salvas**, sem chamar
  o estimador, ler tabelas TEST ou recalcular métricas de desempenho.
- Doze arquivos de dados/auditoria conferidos contra hashes históricos:
  fonte principal Supplier, base, qualidade, targets, splits, auditoria do target
  e os seis Parquets ML-Ready, incluindo ambos os arquivos TEST.
- TEST foi acessado somente como bytes para SHA-256 nesta conferência, sem
  desserializar Parquet ou observar valores para tomar decisões.

Hashes dos arquivos TEST, iguais ao metadata anterior à avaliação:

```text
X_test.parquet  c80ee0e47be00196296432cfee101c0280b799ae1b0093cc12109d0492b0606c
y_test.parquet  95e99b69547a45c37343077402a2a253f4070a99304b608e31701ffbde696fc8
```

Inventário SHA-256 dos artefatos, relativo a `final_evaluation_v1/`:

```text
freeze.json
  70817bc7d270f4fb5d1d7ce27bc48920babe41cd72c317ded7bda300da7db151
execution_started.json
  d60032da8fcc7f58a6bcf870735aee71392ccbfee7a3c0fbfd0533bd81833ffc
fitted_state_before_test.json
  376ee9a0248036cb04fbc467300f2e2705a01f058d2770262df2910340248c8e
test_access_started.json
  91718e15c6b3dd18fe8ecd3722aa0a7a3889c00a9b156b0143194221123668b2
results/LogisticRegression_C.json
  eaf6280e5cd12544aff8e6ac231f1166f8d9ae702a77ab495778593da3541dd0
results/Baseline_majoritaria.json
  0acb8f2edfe12639923d99600dda98b9d3367a11e1c18f3a14592a82c1a5b48d
results/metrics.json
  11ada09a67fccaeab089e84ab0ce2e2d08fe0cf9c9bc37d3d6640d73638dbaa5
results/manifest.json
  298e1ca618ee349ed2e2f07bc7907d16a048b34abb1d747f8dfe173d7f418658
```

`artifact_id` é o digest canônico do contrato; não é o SHA-256 do arquivo inteiro
listado acima. Os dois controles foram conferidos separadamente.

## Limites de engenharia e pendências documentadas

1. Hashes e timestamps locais comprovam consistência dos registros, não autoria,
   procedência autenticada ou impossibilidade absoluta de execução fora deste
   fluxo. O bloqueio é por diretório; remover marcadores ou usar outro diretório
   está fora da garantia. Nenhum desses procedimentos foi realizado nesta etapa.
2. A associação fornecedor/linha depende do contrato posicional do produtor de
   ML-Ready, que remove IDs de X/y. Os hashes e fingerprints foram conferidos,
   mas não demonstram isoladamente a correção semântica do produtor original.
3. O teste parametrizado `test_invalid_features_fail` usa fingerprint inválido:
   falha antes de alcançar as verificações de dtype/NaN/infinito que pretende
   exercitar. É uma lacuna de cobertura a corrigir em etapa futura com fixtures
   válidas e mensagens específicas. A validação existe no executor; não foi
   encontrada evidência de dado inválido nesta execução. Nenhum código ou teste
   foi alterado para este encerramento.
4. O fluxo assume filesystem local cooperativo; hashes não são defesa completa
   contra um agente que troque arquivos concorrentemente. Assinatura digital,
   armazenamento imutável externo e retenção continuam fora deste fechamento.

`docs/supplier_risk_model.md` foi mantido byte a byte: integra o congelamento,
identifica as seções históricas e já aponta para este relatório como status real.
`docs/supplier_risk_experiment_records.md` também foi revisado sem alteração:
descreve corretamente o contrato final e seus limites. Não se reescreveu o
protocolo pré-TEST retrospectivamente.

## Encerramento e próximo passo

Nesta etapa, somente este relatório foi atualizado; nenhum arquivo novo foi
criado. Os scripts, testes novos e oito artefatos JSON já existiam da avaliação
anterior. A comparação antes/depois deste fechamento preservou os hashes de
67 arquivos protegidos de dados, código, testes, modelos, notebooks e evidências.
O notebook EDA manteve o hash
`d813023ec278737a435383da404ebeee4ad737856da5657836ec92c995366f68`.

`git diff --check` não indicou erros; avisos LF/CRLF não são falhas de conteúdo.
HEAD permaneceu `bb9965a735f2269aa1540b0c979b763fb2187fde`, sem staging ou commit.
As alterações da etapa anterior continuam locais, inclusive a alteração de EDA
que não pertence ao fechamento. Não se executaram notebooks, Invoice, Purchase,
treinamento, calibração, tuning ou nova avaliação neste encerramento.

Próximo passo: revisão humana do relatório e seleção explícita dos arquivos para
um eventual commit autorizado, excluindo o notebook EDA. Antes de publicar JSONs
com IDs e labels individuais, conferir licença, retenção e acesso da fonte.
Pendências de procedência e engenharia não autorizam reutilizar TEST para
melhorar o resultado. A avaliação final está encerrada.
