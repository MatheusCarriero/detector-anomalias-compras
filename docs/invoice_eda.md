# EDA acadêmica do Invoice — somente TRAIN

## Escopo e execução

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

## Colunas efetivamente analisadas e limite da fonte

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

## Qualidade e referência

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

## Estatísticas e distribuições observadas

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

## Correlação entre features

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

## Ranking de associação com is_fraud

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

## Limitações e preservação metodológica

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

## Reprodução e testes

Abrir o notebook a partir da raiz do projeto ou de `ml/notebooks/` e executar
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

Validação desta entrega: **26 testes focados aprovados**; regressão completa com
**918 aprovados e 8 ignorados**, estes por indisponibilidade de privilégios de
symlink no Windows. A suíte foi executada com proteção de I/O e registrou zero
tentativas de acesso a datasets/modelos reais. Ruff dos arquivos novos e
`git diff --check` aprovados. A revisão independente não encontrou bloqueadores.

```powershell
python -m pytest -q
python -m ruff check ml/notebooks/01_invoice_eda.ipynb tests/invoice/test_invoice_eda.py
git diff --check
```
