# Supplier Risk — primeira EDA (somente TRAIN)

## Escopo e execução

**IMPLEMENTADO em 16/09/2026:** [notebook executado](../ml/supplier_risk/notebooks/01_supplier_risk_eda.ipynb), com 12 células de código e seis figuras. Base pré-imputação, targets e split existentes; leitura filtrada por `split == "train"` e depois pelos respectivos IDs. Foram analisados **16.894 fornecedores e 10 features**, com IDs únicos, correspondência exata entre tabelas, zero infinitos e zero perfis completos de features repetidos.

**VALIDATION e TEST permaneceram cegos nesta EDA.** Não foram consultados os Parquets ML-Ready. Os hashes conferem integridade de arquivos, sem produzir estatísticas dos holdouts. Nenhum modelo foi treinado, nenhuma decisão final de modelo foi tomada e não houve tuning, seleção de threshold ou alteração de dados.

## Observações dos dados

### Target e estatísticas

Classe 0: **5.008 (29,644%)**; classe 1: **11.886 (70,356%)**. O desbalanceamento não foi tratado como erro. Estatísticas abaixo usam somente valores presentes; percentuais de missing usam todos os fornecedores TRAIN.

| Feature | Média | Mediana | Nulos | Missing % |
|---|---:|---:|---:|---:|
| financial_stability_score | 56,6564 | 56,5768 | 201 | 1,190 |
| on_time_delivery_rate | 77,5560 | 77,7036 | 105 | 0,622 |
| defect_rate | 4,7150 | 4,5628 | 157 | 0,929 |
| geopolitical_risk_index | 33,4210 | 31,0000 | 0 | 0 |
| lead_time_days | 25,6333 | 25,0000 | 128 | 0,758 |
| alternative_suppliers_available | 2,8583 | 3,0000 | 143 | 0,846 |
| contract_length_months | 19,0227 | 19,0000 | 0 | 0 |
| environmental_compliance | 70,9402 | 71,4000 | 179 | 1,060 |
| previous_disruptions | 0,9585 | 1,0000 | 109 | 0,645 |
| supplier_record_count | 1,0227 | 1,0000 | 0 | 0 |

O notebook contém também count, desvio padrão amostral, mínimo, Q1, Q3, máximo, zeros, cardinalidade, histogramas e boxplots. Foram preservadas **1.022 células nulas**, sem imputação.

### Diferenças entre classes, correlações e missing

- Estabilidade financeira: média **68,2487 na classe 0 versus 51,7867 na classe 1**; diferença absoluta 16,4620.
- Índice geopolítico: **24,6464 versus 37,1181**; diferença 12,4718.
- Compliance ambiental: **75,0143 versus 69,2241**. Fornecedores alternativos: **3,4921 versus 2,5912**.
- Taxa de defeitos apresentou médias próximas: **4,6536 versus 4,7409**. Contagem de registros: **1,0214 versus 1,0233**.
- Entre features, nenhuma correlação alta: máximo absoluto **Pearson 0,0420 / Spearman 0,0466**, ambos entre estabilidade financeira e índice geopolítico. Cálculo por pares presentes, com suporte exibido; não demonstra independência nem exclui interações.
- A taxa máxima de missing foi 1,190%. Entre os 201 casos sem estabilidade financeira, 65,17% pertencem à classe 1, contra 70,42% entre os presentes. Para lead time: 64,06% de classe 1 nos 128 ausentes, contra 70,40% nos presentes. São diferenças descritivas, sem inferência sobre o mecanismo de ausência.

### Qualidade e features provisórias

- **Compliance > 100:** 985 fornecedores, **5,8305% do TRAIN** (5,8929% dos presentes); valores **100,10–100,95**; classe 0 = 415, classe 1 = 570 (57,87% dos casos). Possível inconsistência de domínio pendente de confirmação da escala; sem clipping.
- **Lead time = 0:** 770 fornecedores, **4,5578% do TRAIN** (4,5926% dos presentes); classe 0 = 248, classe 1 = 522 (67,79% dos casos). Significado não confirmado; zeros mantidos. Nenhuma feature apresentou negativos.
- **Índice geopolítico:** 17 valores distintos, de 11 a 87, sem missing; o valor 31 concentra 33,69% do TRAIN. Procedência, fórmula, data e mapeamento por país continuam não comprovados. Country e a versão alternativa da fonte não foram analisados nesta EDA.
- **Contagem de registros:** 1 = **16.515 (97,7566%)**; 2 = **374 (2,2138%)**; 3 = **5 (0,0296%)**. Percentuais de classe 1: 70,32%, 71,93% e 80%, respectivamente. O último grupo é demasiado pequeno para conclusão estável; a contagem não representa histórico temporal.
- Outlier estatístico não equivale a erro: IQR zero na contagem sinaliza todos os 379 casos com contagem 2/3; isso não justifica excluí-los. Compliance > 100 sequer ultrapassa o limite superior de Tukey (119,8425), evidenciando a diferença entre critério estatístico e domínio.

### Indícios univariados de proxies

- Estabilidade financeira teve associação com target de **Pearson −0,5166 / Spearman −0,5132**. No menor decil observado (3,1949–37,9934), **1.649/1.670 = 98,74%** são classe 1; no maior (75,3939–100), **282/1.670 = 16,89%**.
- Índice geopolítico: **Pearson 0,3694 / Spearman 0,3619**. Na faixa descritiva 64–87, **919/960 = 95,73%** são classe 1. Nos valores 82/84/85/86/87, todos são classe 1, mas são apenas **45 fornecedores somados**.
- Há sobreposição entre classes; não foi demonstrada regra univariada perfeitamente determinística. As faixas resultam de quantis da feature, não de busca pelo melhor corte. A contagem apresenta associação univariada muito pequena com target (Pearson 0,0059).

## Hipóteses / interpretações

1. Estabilidade financeira e índice geopolítico **podem ter participado da construção de Risk_Level**, ou refletir outras relações não documentadas. É hipótese, não fato comprovado, causalidade ou evidência de risco empresarial real.
2. Contagem e missing podem refletir coleta/completude. A EDA não comprova o mecanismo nem autoriza criar indicadores ou remover features.
3. Correlações fracas entre features não eliminam possíveis regras multivariadas da label. A procedência continua pendente; nenhuma métrica futura deve ser interpretada automaticamente como previsão de falhas reais.

## Protocolo preservado e qualidade

Continuam obrigatórios **A: 10 features; B: sem geopolitical_risk_index; C: sem supplier_record_count; D: sem ambas**. Hipóteses da EDA não substituem o [protocolo experimental](supplier_risk_model.md#13-protocolo-experimental-pré-definido--planejado). Nenhuma ablação ou escolha de modelo foi executada.

Reprodução: Python 3.14.3, pandas 2.3.3, NumPy 2.5.2, PyArrow 25.0.1 e ferramentas opcionais fixadas em [notebooks/requirements.txt](../ml/supplier_risk/notebooks/requirements.txt): matplotlib 3.10.8, nbformat 5.10.4, nbclient 0.10.4 e ipykernel 7.2.0. Instalação somente no ambiente temporário isolado; a `.venv` principal e os requisitos dos pipelines não foram alterados. As versões relevantes e hashes das entradas estão incorporados ao notebook.

Notebook executado integralmente, sem erros; **113 testes sintéticos aprovados**. Ruff: `All checks passed!`; `git diff --check`: aprovado. **63 arquivos preexistentes monitorados mantiveram seus SHA-256**, incluindo dados, splits, ML-Ready, modelos, scripts, testes e requisitos dos pipelines. Nenhum commit criado. O executor Jupyter emitiu aviso não bloqueante sobre o event loop do Windows e utilizou o fallback do PyZMQ; a execução foi concluída com zero erros nas células.
