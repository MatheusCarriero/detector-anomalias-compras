# Supplier Risk — validação científica exploratória

## 1. Objetivo, escopo e conclusão executiva

Avaliar se o desempenho da primeira rodada é estável em partições internas de TRAIN e metodologicamente defensável, sem consultar TEST, selecionar um modelo definitivo ou alterar fontes/features/splits.

**IMPLEMENTADO:** [notebook 03 executado](../ml/supplier_risk/notebooks/03_supplier_risk_validation_analysis.ipynb), com CV de cinco folds, cenários A/D, um controle negativo de labels embaralhadas, reprodução diagnóstica da Logistic Regression A anterior e análise de erros. Todos os ajustes foram experimentais; nenhum estimador foi serializado.

**RESULTADO OBSERVADO:** A alcançou F1-macro **0,92683 ± 0,00624**; D, **0,79729 ± 0,00929**. A foi superior em todos os cinco folds. Com labels embaralhadas, ambos passaram a prever somente a classe majoritária: balanced accuracy **0,50000**, ROC-AUC aproximadamente **0,50**. A reprodução da LR A confirmou os **131 FP e 81 FN** publicados na rodada anterior.

**INTERPRETAÇÃO:** há evidência adicional de sinal classificatório na fonte e consistência nessa divisão interna, não apenas uma vantagem particular da VALIDATION anterior. Entretanto, a dependência das variáveis excluídas em D permanece relevante. Isso **não valida risco empresarial real**, origem da label, generalização temporal/externa ou ausência absoluta de leakage.

O problema continua sendo estimar pertencimento a `Risk_Level`, convenção `0 = menor risco`, `1 = maior risco`. Não se prevê fraude, falha ou ruptura futura. Probabilidades continuam não calibradas e significam somente pertencimento estimado à classe 1.

## 2. Dados, alinhamento e fronteira de TEST

Entradas originais, somente leitura, em `data/processed/supplier_risk/`:

- `supplier_features_base.parquet`;
- `supplier_targets.parquet`;
- `supplier_split_assignments.parquet`.

O metadata existente de ML-Ready fornece hashes, medianas históricas e fingerprints da ordenação dos IDs; o notebook 02 fornece a referência documental. **Nenhum X_train previamente imputado foi carregado para CV**, nem qualquer Parquet separado de TEST.

Primeiro é selecionado `split == train`; features e targets são lidos com filtro nos respectivos IDs. Validação inclui schema, IDs não nulos e únicos, reconciliação exata dos conjuntos, join um-para-um, target binário, tipos numéricos, ausência de infinitos e ordenação por ID compatível com o produtor. Não há identificador ou target entre as features.

O TRAIN contém **16.894 fornecedores**, classes 0/1 com **5.008/11.886** registros e **1.022 células nulas preservadas**. A seleção de VALIDATION, com **3.539 fornecedores**, ocorre somente após terminar a CV real e o controle negativo, para diagnóstico de erros. As duas seleções têm IDs disjuntos. Nenhuma linha TEST é selecionada para análise.

**Limite físico da leitura:** a base/targets/split são Parquets compartilhados. Os filtros restringem as linhas materializadas, mas um leitor pode decodificar row groups compartilhados com outras partições; não se promete isolamento físico de bytes. Os hashes desses arquivos conferem integridade, sem analisar valores de TEST. Arquivos `X_test.parquet` e `y_test.parquet` não são abertos.

## 3. Protocolo registrado antes dos resultados

### Folds, modelo e orçamento

- `StratifiedKFold(n_splits=5, shuffle=True, random_state=42)`, somente dentro de TRAIN.
- A e D compartilham exatamente os mesmos índices de ajuste/validação interna.
- Cada fornecedor aparece uma vez na validação interna; IDs de ajuste e validação interna são disjuntos em cada fold.
- Folds 1–4: 13.515 registros de ajuste / 3.379 de validação interna; fold 5: 13.516 / 3.378.
- Pipeline novo em cada fold: `SimpleImputer(strategy="median") → StandardScaler → LogisticRegression`.
- LR: `C=1.0`, `solver="lbfgs"`, `max_iter=1000`, `random_state=42`, sem ponderação de classes; demais parâmetros padrão. Mesma configuração da baseline anterior.
- Baseline trivial: classe majoritária calculada somente no subtreino de cada fold, sem estimador adicional.
- `predict()` padrão, sem escolher threshold, class_weight ou hiperparâmetros a partir dos resultados.

**Orçamento cumprido: 21 fits de LR** — dez na CV real, dez no controle e um na reprodução diagnóstica. Zero avisos de fit/convergência. Sem tuning, Random Forest adicional, seleção automática ou treinamento final.

O notebook confere, em cada ajuste, as medianas contra o respectivo subtreino, a média/variância do scaler contra os dados imputados desse subtreino e a quantidade de linhas vistas. Depois da predição, verifica que os estados dos transformadores não mudaram. Nulos são tratados dentro do fold, nunca usando estatísticas globais de TRAIN na CV.

### Cenários fixos

A inclui, nesta ordem:

1. `financial_stability_score`;
2. `on_time_delivery_rate`;
3. `defect_rate`;
4. `geopolitical_risk_index`;
5. `lead_time_days`;
6. `alternative_suppliers_available`;
7. `contract_length_months`;
8. `environmental_compliance`;
9. `previous_disruptions`;
10. `supplier_record_count`.

D mantém a ordem das demais e exclui **somente em memória**, no respectivo experimento, `geopolitical_risk_index` e `supplier_record_count`. Nenhuma feature foi removida ou alterada nos arquivos.

### Convenções estatísticas

Métrica principal: F1-macro. Reportadas também balanced accuracy, recall/F1 por classe e ROC-AUC com score da classe 1. Médias não ponderadas dos cinco folds e **desvio padrão amostral (ddof=1)**; não são métricas agregadas de um modelo único treinado em toda a base.

Os subtreinos se sobrepõem. Portanto, os folds **não foram tratados como observações independentes**: sem t-test, p-valor, erro padrão da média ou intervalo de confiança calculado dessa forma. Deltas A − D usam os mesmos folds, apenas de maneira descritiva. Não há afirmação de significância ou equivalência universal.

## 4. RESULTADOS OBSERVADOS — validação cruzada real

Valores: média ± DP entre os cinco folds.

| Métrica | A — 10 features | D — 8 features |
|---|---:|---:|
| F1-macro | 0,92683 ± 0,00624 | 0,79729 ± 0,00929 |
| Balanced accuracy | 0,92141 ± 0,00592 | 0,78435 ± 0,01014 |
| Recall classe 0 | 0,87640 ± 0,00948 | 0,64996 ± 0,01958 |
| Recall classe 1 | 0,96643 ± 0,00561 | 0,91873 ± 0,00238 |
| F1 classe 0 | 0,89609 ± 0,00876 | 0,70528 ± 0,01455 |
| F1 classe 1 | 0,95757 ± 0,00374 | 0,88930 ± 0,00406 |
| ROC-AUC | 0,98462 ± 0,00178 | 0,89991 ± 0,00340 |

Baseline majoritária nos folds: F1-macro **0,41300 ± 0,00005**, balanced accuracy **0,50000**, recall classe 0 = 0, recall classe 1 = 1. Seu F1 difere da baseline da VALIDATION anterior porque a prevalência é diferente, não por mudança de definição.

### Comparação pareada A × D

| Fold | F1-macro A | F1-macro D | Delta A − D |
|---|---:|---:|---:|
| 1 | 0,92799 | 0,80338 | +0,12462 |
| 2 | 0,91612 | 0,78103 | +0,13510 |
| 3 | 0,93241 | 0,80303 | +0,12938 |
| 4 | 0,92819 | 0,79894 | +0,12925 |
| 5 | 0,92944 | 0,80007 | +0,12937 |

Diferença média A − D: **+0,12954 em F1-macro** (12,95 pontos percentuais) e **+0,13707 em balanced accuracy**. A melhora em todos os cinco folds. O recall médio da classe 0 cai de **0,87640** para **0,64996** ao passar de A para D; também há redução na classe 1.

**INTERPRETAÇÃO:** o ganho de A se repete nesse particionamento interno. A diferença não parece exclusiva da VALIDATION da primeira rodada. D, contudo, permanece bem acima da referência trivial: existe sinal fora das duas variáveis excluídas.

A comparação A/D **não identifica separadamente** o efeito de cada uma das duas features. As ablações B/C do [relatório anterior](supplier_risk_baseline_models.md) já sugeriam forte contribuição do índice geopolítico e ausência de ganho claro da contagem naquela configuração. Esses resultados são contexto anterior, não novos testes de B/C. Dispersão pequena em uma CV não prova estabilidade em outra fonte, período, país ou mecanismo de coleta.

## 5. RESULTADOS OBSERVADOS — controle negativo

Uma única permutação das labels entre fornecedores de TRAIN, usando `numpy.random.default_rng(2026)`. X e IDs ficaram idênticos; a distribuição das classes foi preservada. O target original não foi sobrescrito.

Cinco folds estratificados pela **label permutada**, com seed 42, compartilhados por A/D. Os folds do controle podem diferir dos reais; não se interpretaram diferenças entre esses folds como comparações pareadas. O treinamento e a avaliação interna usam o target permutado.

| Cenário embaralhado | F1-macro | Balanced accuracy | ROC-AUC |
|---|---:|---:|---:|
| A | 0,41300 ± 0,00005 | 0,50000 ± 0,00000 | 0,50025 ± 0,00904 |
| D | 0,41300 ± 0,00005 | 0,50000 ± 0,00000 | 0,50242 ± 0,00911 |

Nos dois cenários, em todos os folds:

- recall/F1 classe 0 = **0**;
- recall classe 1 = **1**;
- F1 classe 1 médio = **0,82599**;
- todas as predições de classe são **1**, iguais à estratégia majoritária;
- scores contínuos apresentam ROC-AUC próximo de 0,5, sem evidência descritiva de discriminação útil nesse controle.

**INTERPRETAÇÃO:** o pipeline não manteve a vantagem preditiva ao romper a associação entre X e y. É um teste de sanidade favorável. Não equivale a prova absoluta de ausência de leakage: uma label originalmente construída a partir das features também perderia associação após embaralhamento. O controle não valida sua independência conceitual, origem ou significado empresarial.

**LIMITAÇÃO:** foi executada uma permutação, não uma distribuição de múltiplas permutações para teste formal. Não se calcula p-valor nem se escolhe outra seed após observar o resultado.

## 6. Recuperação e análise dos erros anteriores

### Limitação de persistência e reprodução controlada

O notebook 02 salvou tabelas e coeficientes, mas não persistiu o estimador ou vetor de predições por fornecedor. Não é possível recuperar literalmente os erros individuais daquele vetor inexistente.

Foi reproduzida **somente a LR A**, com mesmos parâmetros e TRAIN original. As medianas coincidiram com as registradas pelo produtor ML-Ready; os valores após imputação coincidiram com o preenchimento por essas medianas. A ordenação por ID foi validada contra os fingerprints históricos. A reprodução confirmou:

- matriz de confusão exata: TN = **979**, FP = **131**, FN = **81**, TP = **2.348**;
- F1-macro **0,92955**, balanced accuracy **0,92432**, recalls 0/1 **0,88198/0,96665**;
- métricas e coeficientes publicados, dentro do arredondamento de cinco casas;
- intercepto publicado, com tolerância de 1e-9.

Isso sustenta compatibilidade com o experimento anterior, mas **não prova igualdade bit a bit de predições individuais antigas**, pois não existe vetor persistido para comparar. O diagnóstico se refere às predições reconstruídas dessa configuração fixa. Não houve nova seleção, nova baseline RF, incorporação de VALIDATION no fit ou treinamento final.

### Missing, compliance e lead time — OBSERVAÇÃO

Os indicadores abaixo foram calculados sobre os valores originais **pré-imputação de VALIDATION** e nunca usados como features. FPR = FP / classe real 0 do grupo; FNR = FN / classe real 1 do grupo.

| Condição | Grupo | N | FP / classe 0 | FPR | FN / classe 1 | FNR |
|---|---|---:|---:|---:|---:|---:|
| Ao menos uma feature nula | Condição presente | 225 | 9/75 | 12,00% | 14/150 | 9,33% |
| Ao menos uma feature nula | Referência sem a condição | 3314 | 122/1035 | 11,79% | 67/2279 | 2,94% |
| Compliance > 100 | Condição presente | 185 | 7/79 | 8,86% | 4/106 | 3,77% |
| Compliance > 100 | Referência sem a condição | 3308 | 123/1017 | 12,09% | 75/2291 | 3,27% |
| Compliance > 100 | Valor desconhecido (nulo) | 46 | 1/14 | 7,14% | 2/32 | 6,25% |
| Lead time = 0 | Condição presente | 181 | 5/57 | 8,77% | 5/124 | 4,03% |
| Lead time = 0 | Referência sem a condição | 3332 | 126/1045 | 12,06% | 75/2287 | 3,28% |
| Lead time = 0 | Valor desconhecido (nulo) | 26 | 0/8 | 0,00% | 1/18 | 5,56% |

Referência para compliance: valores conhecidos ≤ 100. Referência para lead time: valores conhecidos diferentes de zero. Missing dessas features foi separado como desconhecido, não tratado como condição ausente. Os grupos de condições podem se sobrepor; seus totais não devem ser somados entre condições.

**Padrões observados:**

- Com ao menos uma feature nula, FNR = **14/150 = 9,33%**; sem nulos, **67/2.279 = 2,94%**. FPR ficou próximo: **12,00% versus 11,79%**. São 225 fornecedores com alguma ausência.
- Ausência de fornecedores alternativos tem **4 FN em 14 casos de classe 1 (28,57%)**; estabilidade financeira ausente tem **4/38 (10,53%)**. Os suportes são pequenos; não há conclusão confiável de causalidade ou regra corretiva a partir desses subgrupos.
- Compliance > 100: FPR **8,86%** e FNR **3,77%**, comparados a **12,09% / 3,27%** na referência. Não houve aumento uniforme dos dois tipos de erro.
- Lead time = 0: FPR **8,77%** e FNR **4,03%**, comparados a **12,06% / 3,28%** na referência. São apenas cinco FP e cinco FN no grupo com zero.

**HIPÓTESES/INTERPRETAÇÕES:** a imputação e/ou o processo de ausência podem estar associados à dificuldade de reconhecer a classe 1. A comparação é pós-hoc, sem controle por outras features, sem ajuste de multiplicidade e com suportes desiguais. Ela não comprova que missing causa os erros nem autoriza acrescentar flags, excluir registros ou trocar a imputação automaticamente.

Compliance acima de 100 e lead time zero continuam pendências de domínio; desempenho observado não resolve o significado desses valores. Não foi aplicado clipping, remoção ou regra nova.

### Comportamento das principais features — OBSERVAÇÃO

Médias calculadas apenas sobre valores presentes; os denominadores são exibidos:

| Grupo | N do grupo | Estabilidade financeira: média (N presente) | Índice geopolítico: média (N presente) |
|---|---:|---:|---:|
| TN | 979 | 69,275 (967) | 22,728 (979) |
| FP | 131 | 59,458 (127) | 29,420 (131) |
| FN | 81 | 62,189 (77) | 27,173 (81) |
| TP | 2348 | 51,594 (2314) | 37,627 (2348) |

Comparações dentro da mesma classe real:

- FP versus TN: estabilidade financeira menor (**59,458 versus 69,275**) e índice geopolítico maior (**29,420 versus 22,728**).
- FN versus TP: estabilidade financeira maior (**62,189 versus 51,594**) e índice geopolítico menor (**27,173 versus 37,627**).

O notebook também registra mediana, quartis, presença/ausência e médias de todas as dez features por TN/FP/FN/TP, além de distribuições das probabilidades não calibradas.

**INTERPRETAÇÃO:** esses erros se concentram em perfis que, nessas duas variáveis, se aproximam do padrão associado à outra classe no modelo. Isso é coerente com seus coeficientes, mas não identifica causa dos erros, erro da label ou regra determinística de risco.

## 7. Coeficientes e procedência

Coeficientes padronizados por fold, média ± DP; o sinal foi consistente nos cinco folds para todas as features de cada cenário.

| Feature | Coeficiente A: média ± DP | Coeficiente D: média ± DP |
|---|---:|---:|
| alternative_suppliers_available | -2,41454 ± 0,03794 | -0,90414 ± 0,01092 |
| contract_length_months | 1,45505 ± 0,02770 | 0,58401 ± 0,01886 |
| defect_rate | 0,10167 ± 0,02104 | 0,05486 ± 0,01594 |
| environmental_compliance | -1,80734 ± 0,01884 | -0,67143 ± 0,01652 |
| financial_stability_score | -5,58424 ± 0,05651 | -2,12410 ± 0,01328 |
| geopolitical_risk_index | 4,17135 ± 0,05763 | Excluída apenas neste cenário |
| lead_time_days | 0,50144 ± 0,01529 | 0,19515 ± 0,00747 |
| on_time_delivery_rate | -0,77030 ± 0,02050 | -0,30069 ± 0,00968 |
| previous_disruptions | 1,89149 ± 0,01835 | 0,73875 ± 0,01662 |
| supplier_record_count | 0,03023 ± 0,01204 | Excluída apenas neste cenário |

### OBSERVAÇÃO

Em A, estabilidade financeira tem coeficiente **−5,58424 ± 0,05651** e índice geopolítico **+4,17135 ± 0,05763**. São as maiores magnitudes, com sinais negativo/positivo em todos os cinco folds. Em D, estabilidade financeira continua negativa (**−2,12410 ± 0,01328**).

A contagem tem coeficiente pequeno em A (**+0,03023 ± 0,01204**). Sinal positivo estável não demonstra ganho preditivo útil, e sua magnitude não constitui teste de relevância.

### HIPÓTESES/INTERPRETAÇÕES

Os sinais são compatíveis com os padrões da EDA e da primeira rodada. Features podem ter participado da construção da label, representar proxies ou refletir outras relações da fonte. **Não foi comprovada a fórmula de Risk_Level**, nem causalidade. A origem da label continua pendente.

Coeficientes descrevem log-odds estimados condicionais às demais features, para uma unidade padronizada pelo respectivo subtreino. Magnitudes mudam com regularização, especificação e escala. Comparar A/D não representa decomposição causal.

**geopolitical_risk_index:** forte contribuição observada anteriormente e dependência compatível com a CV atual, mas origem, fórmula e referência temporal não comprovadas. Mantém-se como feature provisória; não foi buscada ou inventada uma justificativa para sua transformação.

**supplier_record_count:** quantidade de registros distintos da fonte após deduplicação; não há histórico temporal comprovado. Pode refletir coleta/completude. Sua utilidade continua sujeita a experimentos controlados; A/D atual não a isola, e as ablações anteriores não demonstraram ganho claro. Nenhuma remoção automática foi aplicada.

## 8. Limitações e decisões pendentes

1. Uma fonte e uma única estratificação de cinco folds; nenhuma replicação temporal ou externa. Os splits por fornecedor não demonstram independência por país, processo de coleta ou geração da label.
2. Folds compartilham registros de subtreino. Não são observações independentes para testes convencionais; DP não é intervalo de confiança.
3. Uma permutação negativa é um controle de sanidade, não um teste formal nem uma prova de ausência de leakage/proxies.
4. A label pode incorporar as próprias features. A boa classificação pode reproduzir sua regra de construção, ainda desconhecida.
5. Diagnóstico de VALIDATION é pós-hoc e não uma nova avaliação independente. Usar esses achados repetidamente para ajustar regras esgotaria sua função de comparação.
6. Ausências, compliance > 100 e lead time zero não tiveram seus mecanismos/escala confirmados. Os subgrupos pequenos não sustentam correções automáticas.
7. A/D remove duas features simultaneamente; não atribuir isoladamente o delta a uma delas.
8. Predições individuais da primeira rodada não estavam persistidas; a reprodução diagnóstica confere agregados e coeficientes, não um vetor antigo.
9. Probabilidades não calibradas; nenhum threshold escolhido, custo operacional definido ou validação empresarial.
10. **TEST permanece congelado**. Não foi escolhido modelo definitivo nem autorizado teste final nesta etapa.

Próxima decisão metodológica: revisar a evidência e a procedência, registrar qualquer novo experimento antes de executá-lo e limitar novas consultas a VALIDATION. A preservação futura de predições experimentais com IDs/hashes pode melhorar rastreabilidade, mas nenhum novo dataset de predições foi criado nesta entrega.

## 9. Reprodução e qualidade

Ambiente temporário isolado já existente, sem instalação ou mudança de dependências: Python **3.14.3**, pandas **2.3.3**, NumPy **2.5.2**, PyArrow **25.0.1**, scikit-learn **1.9.0**, matplotlib **3.10.8**, nbformat **5.10.4**, nbclient **0.10.4**. Requisitos opcionais: [notebooks/requirements.txt](../ml/supplier_risk/notebooks/requirements.txt).

Notebook executado completamente: **11 células de código, zero erros**, 21 ajustes experimentais sem avisos de fit e cinco figuras verificadas visualmente. O kernel emitiu aviso de encerramento após a saída do processo pai; não foi erro de célula ou de ajuste.

**Pytest:** 113 testes sintéticos aprovados em **3,86 segundos**, sem dependência dos datasets Kaggle; cache desabilitado e basetemp temporário exclusivo.

**Ruff:** `ruff check .` passou com **All checks passed!**, usando cache desabilitado. **Git:** `git diff --check` retornou código 0, sem erros; somente avisos LF/CRLF relativos aos arquivos que já estavam modificados antes desta etapa. Os dois arquivos novos também foram conferidos quanto a whitespace e estrutura do notebook.

**Integridade:** os **74 arquivos preexistentes monitorados mantiveram seus SHA-256**, incluindo fontes, base, targets, splits, ML-Ready fora de TEST, modelos, scripts, testes, requisitos e documentação anterior. Somente o notebook 03 e este relatório foram acrescentados. Os três Parquets separados de TEST existentes mantiveram tamanho e data de modificação; seus bytes não foram abertos nem para calcular hashes. Não se alega uma comparação SHA-256 desses Parquets de TEST.

O HEAD permaneceu inalterado. Nenhum dataset, split ou arquivo preexistente foi modificado; Invoice, Purchase e o ambiente principal foram preservados. Nenhum commit, treinamento final, modelo definitivo ou artefato de produção foi criado. Os 21 fits desta entrega são exclusivamente os experimentos e a reprodução diagnóstica documentados acima.

As alterações desta etapa ficam restritas a este relatório e ao notebook 03. Modificações preexistentes em README, documentação Supplier e notebook 02 são preservadas.
