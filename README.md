# Detector Inteligente de Anomalias em Compras

Projeto acadêmico de Machine Learning com três domínios independentes: anomalias em faturas, classificação de risco de fornecedores e risco de pedidos de compra. O Invoice possui um Isolation Forest treinado; o Supplier Risk possui dados ML-Ready e primeira EDA exclusivamente no TRAIN, mas ainda não possui classificador treinado ou avaliação preditiva. Backend e frontend ainda não estão implementados.

## Objetivo

O Invoice Anomaly Model identifica padrões incomuns em faturas com Isolation Forest. O Supplier Risk Model será uma classificação supervisionada de `Risk_Level`: estimar o pertencimento à classe de risco definida pelo dataset, não prever acontecimentos futuros. O Purchase mantém a fronteira pré-aprovação, mas ainda precisa escolher entre detecção de anomalias e previsão de um desfecho específico; sua fonte representa linhas de pedido.

As fontes representam populações diferentes, sem chaves reais comuns para integração. Não há merge direto entre suas features. Uma eventual integração de scores seria uma etapa conceitual futura, com validação própria. O Procurement KPI é somente auxiliar.

## Estado atual

| Domínio | Concluído | Pendente |
|---|---|---|
| Invoice Anomaly | Inspeção, validação, 19 features, split oficial, Isolation Forest treinado e salvo | Revisão metodológica da avaliação, seleção de threshold/hiperparâmetros e avaliação final |
| Supplier Risk | Base por fornecedor, qualidade, auditoria do target, split determinístico, ML-Ready com imputação train-only, suíte pytest sintética, protocolo experimental e EDA pré-imputação somente em TRAIN | Baselines, ablações e avaliação; nenhum classificador treinado |
| Purchase Risk | Dataset analisado, granularidade da fonte em linha de pedido e fronteira pré-aprovação documentadas | Escolher anomalia ou desfecho específico; feature engineering, modelagem e avaliação |

A consolidação anterior de qualidade não executou treinamento, EDA nem reprocessamento dos dados reais. Em 16/09/2026 foi concluída a [primeira EDA Supplier, somente TRAIN](docs/supplier_risk_eda.md), sem alterar datasets ou treinar modelos. O artefato Invoice existente não foi modificado.

## Tecnologias

Tecnologias utilizadas atualmente:

- Python
- Pandas
- NumPy
- Scikit-learn
- PyArrow
- Isolation Forest
- pytest e Ruff (desenvolvimento)

Tecnologias planejadas para etapas posteriores:

- FastAPI
- PostgreSQL
- React
- TypeScript

O backend, o banco de dados e o frontend ainda não fazem parte da implementação atual.

## Machine Learning

O Invoice utiliza Isolation Forest, um algoritmo não supervisionado para detecção de anomalias. Seus labels não entram como features; `is_fraud` é reservado à avaliação e `fraud_type` às análises complementares. Modelo e metadata já existem em `ml/models/` no ambiente com os dados locais.

Para evitar data leakage entre partições, campos derivados do risco conhecido (`supplier_risk_score` e `blacklisted_flag`), labels e explicações não entram nas features. As estatísticas de fornecedores, departamentos, países e relações fornecedor/departamento são calculadas exclusivamente no conjunto de treino, mas **não são ponto-a-ponto temporais dentro do TRAIN**: usam todo o período de treino, inclusive a própria observação. `contamination=0.22` é configuração inicial, não desempenho comprovado. Faltam avaliação consolidada e por `fraud_type`; o experimento atual avalia principalmente novas faturas de fornecedores já conhecidos. Threshold deverá ser escolhido em validação, nunca em TEST. Nenhuma mudança no pipeline Invoice foi feita neste fechamento.

No Supplier Risk, `Risk_Level` é o **target supervisionado**, nunca uma feature. A convenção adotada no projeto é `0 = menor risco`, `1 = maior risco`. Para modelos compatíveis, a saída poderá incluir a **probabilidade estimada de pertencimento à classe de risco**, não a probabilidade real de ocorrer um problema. A origem/regra da label não foi comprovada; resultados deverão ser interpretados como capacidade de reproduzir padrões associados à classificação fornecida pelo dataset. Ver [objetivo e limitações](docs/supplier_risk_model.md).

## Dataset principal

O **Procurement Invoice Fraud Dataset** contém 300.000 faturas, divididas oficialmente em:

- 210.000 registros de treino
- 30.000 registros de validação
- 60.000 registros de teste

Os dados brutos e processados não são armazenados no GitHub.

## Dataset auxiliar

O **Procurement KPI Analysis Dataset** contém 777 pedidos de compra e permanece apenas como fonte auxiliar: referência complementar, exploração futura de KPIs e possível apoio ao dashboard. Nesta fase, não participa do treinamento do Invoice Anomaly Model, Supplier Risk Model ou Purchase Risk Model. O arquivo local é preservado em `data/auxiliary/dataset_auxiliar_kpi_compras.csv`. A responsabilidade de cada fonte está descrita em [Estratégia de Dados](docs/data_strategy.md).

## Instalação

**IMPLEMENTADO — instalação limpa validada em Windows x64 / Python 3.14.3 em 2026-09-16.** A versão de Python permanece registrada em `.python-version`, presente, versionado e não ignorado. Nenhuma outra versão de Python foi declarada suportada.

A correção foi restrita a **pandas 2.2.2 → 2.3.3** em `requirements.txt`; as outras 21 versões fixadas foram mantidas e `requirements-dev.txt` não mudou. A escolha é sustentada pelo [suporte a Python 3.14 documentado pelo pandas 2.3.3](https://pandas.pydata.org/docs/whatsnew/v2.3.3.html), sem migrar para pandas 3.x. Matplotlib e ferramentas Jupyter ficam no [manifesto opcional de EDA Supplier](ml/supplier_risk/notebooks/requirements.txt), sem ampliar as dependências dos pipelines ou da CI. XGBoost permanece ausente.

### Instalação em um checkout novo

Confirmar que o executável escolhido é Python 3.14.3 antes dos comandos abaixo. `.python-version` não troca automaticamente o interpretador. No host auditado, `C:\Python314\python.exe` é 3.14.3, enquanto `py -3.14` aponta para 3.14.4; não confundir os dois.

```powershell
python -c "import sys; assert sys.version_info[:3] == (3, 14, 3), sys.version"
if ($LASTEXITCODE -ne 0) { throw "Selecione o Python 3.14.3 antes de continuar." }
if (Test-Path -LiteralPath .venv) { throw "A .venv já existe; preserve-a e use outro local novo." }
python -I -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o ambiente isolado." }
.\.venv\Scripts\python.exe -I -m pip --isolated install --only-binary=:all: --index-url https://pypi.org/simple --no-cache-dir --disable-pip-version-check -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Falha na instalação das dependências." }
.\.venv\Scripts\python.exe -I -m pip check
```

Não utilizar `--system-site-packages`. A instalação foi comprovada usando wheels do PyPI e pip 25.3, sem cache, em venv nova com `include-system-site-packages=false`. Foi verificado que os pacotes instalados pertencem à venv, que o user-site está desabilitado e que `pip check` não identifica conflitos. Os 113 testes sintéticos e o Ruff passaram nesse ambiente.

**Ambiente principal preservado:** a `.venv` antiga não foi substituída nem atualizada; continua usando Python 3.14.3 e pandas 2.2.2 com pacotes externos à venv. Ela não corresponde aos requisitos corrigidos. A validação utilizou uma venv temporária separada; para o trabalho futuro, criar um ambiente novo a partir dos requisitos atuais, sem instalar sobre o ambiente legado automaticamente.

### Combinações verificadas e histórico

| Interpretador / ambiente | Verificação | Resultado / limite |
|---|---|---|
| Python 3.14.3, Windows x64, venv nova e isolada, pandas 2.3.3 e demais pins atuais | Instalação completa por wheels, isolamento, pip check, Ruff e pytest | **Aprovado em 2026-09-16: 113 testes**, sem datasets externos |
| Python 3.14.3 na `.venv` principal antiga, pandas 2.2.2 | Pins anteriores, pip check e suíte sintética | Funcional, mas reutiliza pacotes externos; preservada, não é a instalação limpa |
| Python 3.14.3 em venv temporária com os requisitos antigos | Resolução limpa por wheels em 14–15/09/2026 | Falhou em pandas 2.2.2; combinação substituída |
| Python 3.13.14 em venv temporária com os requisitos antigos | Mesma sondagem de resolução por wheels | Falhou em pandas 2.2.2; requisitos atuais e suíte não testados nessa versão |
| Python 3.14.4 registrado no launcher | Somente versão/executável consultados | Projeto não validado nessa versão |
| Linux, macOS, Python free-threaded, compilação a partir da fonte | Não testados | Nenhuma alegação de compatibilidade |

As **22 versões fixadas** para a nova instalação são:

- execução: pandas 2.3.3, numpy 2.5.2, pyarrow 25.0.1, scikit-learn 1.9.0, joblib 1.6.0, openpyxl 3.1.5;
- transitivas de execução: python-dateutil 2.9.0.post0, pytz 2026.2, tzdata 2025.3, six 1.17.0, et-xmlfile 2.0.0, scipy 1.18.1, threadpoolctl 3.6.0, narwhals 2.21.2, cloudpickle 3.1.2;
- desenvolvimento: pytest 9.1.1, ruff 0.16.5, colorama 0.4.6 (Windows), iniconfig 2.3.0, packaging 26.0, pluggy 1.6.0, pygments 2.20.0.

**Registro histórico:** em 2026-09-14, `git status` indicava exclusão local de `.python-version`; `git ls-files` confirmou o versionamento e `git check-ignore -v` não identificou regra de exclusão. Foi restaurado o conteúdo do HEAD, `3.14.3`, sem mudança de versão; a causa da exclusão não foi comprovada. Na consolidação anterior, a venv compartilhada recebeu somente pytest 9.1.1, iniconfig 2.3.0 e pluggy 1.6.0. As sondagens de 14–15/09 usaram `pip install --dry-run --only-binary=:all: --index-url https://pypi.org/simple --no-cache-dir -r requirements-dev.txt` e não completaram a instalação antiga. Essa limitação motivou a correção controlada atual; não houve upgrade/downgrade do Python.

**LIMITES:** comprovamos instalação e testes sintéticos em Windows local, não reprodução integral de modelos ou resultados dos datasets reais. Os artefatos e seus metadados históricos permanecem intactos, inclusive quando registram pandas 2.2.2. Não há garantia de equivalência bit a bit de artefatos entre versões. Os requirements fixam versões, mas não são um lock com hashes de todos os wheels; disponibilidade futura no PyPI e validação no runner remoto ainda são dependências externas. A CI está configurada no arquivo [quality.yml](.github/workflows/quality.yml), mas sua primeira execução no GitHub ainda está pendente.

## Qualidade e testes

Com o ambiente de desenvolvimento ativo:

```powershell
ruff check .
pytest -q
```

```text
tests/supplier_risk/
├── conftest.py
├── test_prepare_features.py
├── test_target_and_split.py
└── test_build_ml_dataset.py
```

A suíte usa pequenos DataFrames sintéticos e `tmp_path`. Os caminhos dos três scripts Supplier Risk são redirecionados para diretórios temporários; nenhum teste depende de Kaggle, dos Parquets reais, de credenciais ou do treinamento de modelos. Os testes de imputação ajustam apenas o transformador em dados sintéticos.

Resultado local desta consolidação: **113 testes aprovados**, aproximadamente **5 a 17 segundos** nas execuções locais da suíte; Ruff: `All checks passed!`. São cobertos deduplicação, nulos preservados na base, conflitos de target, determinismo do hash, reconciliação de IDs, train-only, alinhamento X/y e reexecução equivalente.

Revalidação no fechamento metodológico de 14–15/09/2026: **113 aprovados em 3,74 segundos**, Ruff aprovado e `git diff --check` sem erros. Para contornar a permissão negada previamente observada no diretório temporário padrão do Windows, a execução usou `--basetemp` apontando para um caminho temporário novo e exclusivo, via `PYTEST_ADDOPTS`, com cache pytest desabilitado. Nunca apontar `--basetemp` para dados, workspace ou diretório existente com arquivos importantes: o pytest gerencia esse conteúdo como descartável. Não foram alterados testes, pipelines, requirements ou datasets.

**Revalidação isolada em 2026-09-16:** Python 3.14.3 / pandas 2.3.3, `pip check` sem conflitos, **113 testes aprovados em 4,09 segundos** e Ruff aprovado, sem modificar testes ou scripts. Os comandos foram executados com `python -I` para excluir pacotes do usuário, `--basetemp` exclusivo e caches de teste/lint desabilitados.

Uma segunda execução em cópia temporária contendo somente scripts Supplier, testes e configurações, sem a pasta `data/`, aprovou os mesmos **113 testes em 3,19 segundos**. A conferência final de SHA-256 preservou os 62 arquivos monitorados de dados, artefatos, scripts, testes e configurações protegidas; as versões instaladas na `.venv` principal também permaneceram iguais.

**CI configurada, execução remota pendente:** [`.github/workflows/quality.yml`](.github/workflows/quality.yml) usa Windows 2025 x64, a versão de `.python-version`, venv isolada e os requirements fixados. Executa instalação por wheels, `pip check`, Ruff e pytest sintético, sem dados Kaggle, EDA ou treinamento. As ações oficiais estão fixadas por SHA, com permissão somente de leitura e sem persistência de credenciais. Após um futuro envio, rodará em push/pull request ou acionamento manual; nenhum commit, push ou disparo remoto foi realizado nesta etapa.

## Configuração dos datasets

Coloque os arquivos do dataset principal em `data/raw/`:

```text
data/raw/
├── invoices.parquet
├── labels.parquet
├── suppliers.parquet
├── splits.parquet
└── images_metadata.parquet
```

O arquivo de metadados `manifest.json` pode permanecer nessa pasta e é versionado intencionalmente. Coloque o dataset auxiliar em:

```text
data/auxiliary/dataset_auxiliar_kpi_compras.csv
```

As fontes externas ficam em `data/external/supplier_risk/` (`supplier_risk_dataset.csv` e o CSV bruto de referência) e `data/external/purchase_orders/` (`Dataset_Procurement.xlsx`). Elas são necessárias para os respectivos pipelines reais, **não para os testes**.

Esses datasets não são enviados ao GitHub. Os scripts de extração são opcionais e servem apenas para a obtenção inicial dos dados. Caso necessário, coloque `archive.zip` em `data/raw/` e `dataset_auxiliar_kpi_compras.zip` em `data/auxiliary/`; ambos são ignorados pelo Git. Por compatibilidade, os scripts também reconhecem os ZIPs mantidos localmente na pasta legada `DataBase/`.

## Features iniciais

O primeiro modelo utiliza 19 features, entre elas:

- valor e logaritmo do valor da fatura;
- frequência e idade do fornecedor;
- comparação com a média histórica e z-score do fornecedor;
- frequência do departamento e relação fornecedor/departamento;
- prazo de pagamento e tipo de fatura;
- features temporais cíclicas de hora, dia da semana e mês.

Todas essas estatísticas usam apenas o conjunto de treino, sem usar validation/test; isso não equivale a reconstruir o histórico disponível no instante de cada fatura do próprio TRAIN.

## Estrutura do projeto

```text
.
├── data/
│   ├── raw/
│   ├── auxiliary/
│   ├── external/
│   └── processed/
│       └── supplier_risk/ml_ready/
├── ml/
│   ├── scripts/
│   ├── models/
│   ├── notebooks/
│   ├── supplier_risk/  # scripts/, models/, notebooks/
│   └── purchase_risk/  # scripts/, models/, notebooks/
├── tests/supplier_risk/
├── backend/
├── frontend/
├── docs/
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── .python-version
├── pytest.ini
└── README.md
```

## Execução dos scripts

Os comandos abaixo documentam os pipelines existentes. Eles usam dados locais e podem sobrescrever artefatos processados; **não fazem parte da suíte de testes nem foram executados nesta consolidação**. Invoice:

```bash
python ml/scripts/analisar_dataset.py
python ml/scripts/validar_dataset.py
python ml/scripts/preparar_features.py
```

Supplier Risk, na ordem de dependência (não inclui EDA ou treinamento):

```powershell
python ml/supplier_risk/scripts/prepare_features.py
python ml/supplier_risk/scripts/prepare_target_and_split.py
python ml/supplier_risk/scripts/build_ml_dataset.py
```

Estado preservado: 24.112 fornecedores, 10 features, partições de 16.894 / 3.539 / 3.679 fornecedores. A base mantém nulos; somente os derivados ML-Ready utilizam `SimpleImputer(strategy="median")`, com `fit_transform()` em TRAIN e `transform()` nos outros conjuntos.

Para inspecionar o dataset auxiliar:

```bash
python ml/scripts/inspecionar_dataset_auxiliar.py
```

Os caminhos são resolvidos a partir da localização dos próprios scripts, portanto os comandos também funcionam quando chamados a partir de outro diretório.

## Próxima fase do Supplier Risk

**EDA concluída:** 16.894 fornecedores TRAIN, 10 features, base pré-imputação e holdouts cegos. Consulte o [relatório](docs/supplier_risk_eda.md) e o [notebook executado](ml/supplier_risk/notebooks/01_supplier_risk_eda.ipynb). Os indícios de associação com a label não comprovam sua origem nem autorizam alterar antecipadamente A/B/C/D. A próxima etapa planejada é executar as baselines segundo o protocolo; nenhum treinamento foi realizado nesta EDA.

**PLANEJADO — protocolo 1.0, registrado antes de EDA/treinamento:** EDA somente no TRAIN → baseline 0 majoritária → baseline 1 Logistic Regression → primeiro candidato não linear RandomForestClassifier → comparação em VALIDATION → congelamento → avaliação final única em TEST.

O [protocolo experimental do Supplier](docs/supplier_risk_model.md#13-protocolo-experimental-pré-definido--planejado) é a referência para as decisões abaixo:

- A/B/C/D: dez features / sem `geopolitical_risk_index` / sem `supplier_record_count` / sem ambas. Nenhuma ablação altera os Parquets atuais ou usa TEST para seleção.
- Logistic Regression: `SimpleImputer(median) → StandardScaler → LogisticRegression` dentro de Pipeline, ajustado somente em TRAIN. Random Forest é o primeiro candidato baseado em árvores; XGBoost permanece fora das dependências.
- Métrica principal: **F1-macro**. Secundárias: precision/recall/F1 de cada classe, balanced accuracy, ROC-AUC, PR-AUC reportada como Average Precision e confusion matrix. Accuracy é apenas complementar.
- Utilidade mínima: superar claramente a baseline majoritária em F1-macro e balanced accuracy, identificar ambas as classes e não depender apenas de prever classe 1. O protocolo inclui avaliação de incerteza, sem impor um F1 absoluto arbitrário.
- TRAIN explora/ajusta/treina; VALIDATION compara features/modelos/hiperparâmetros/threshold; TEST somente avalia ao final, sem EDA, tuning ou calibração.
- CV futura: base com nulos + IDs de TRAIN, com imputação e demais transformações dentro de Pipeline em cada fold. O `X_train` já imputado não deve alimentar diretamente essa CV; continua válido para experimentos simples train/validation.
- Probabilidades significam somente pertencimento à classe 1. `predict_proba()` exige avaliação posterior de calibração antes de exibir percentuais como confiáveis; calibration curve, Brier score e eventual CalibratedClassifierCV são planejados, não implementados.

**LIMITAÇÕES:** origem/regra de Risk_Level não comprovadas; índice geopolítico provisório e associado a Country; contagem pode refletir coleta, não histórico; 1.386 fornecedores com compliance > 100 e 1.134 com lead time = 0 foram preservados sem clipping/exclusão automática. Não se pretende prever fraude, falhas ou rupturas futuras, validar risco empresarial real, nem substituir avaliação humana.

**Purchase — somente documentação:** o Vocabulary & Notes define PO_Number como linha de pedido, Lead_Time_Days como pós-entrega, ESG como simulado e valores em moedas locais sem câmbio. Falta escolher anomalia ou desfecho específico e confirmar dados pré-aprovação; anomalia não será chamada automaticamente de risco. Ver [contrato Purchase](docs/purchase_risk_model.md).

O projeto ainda não possui aplicação backend/frontend, banco integrado ou avaliação final consolidada. Os detalhes e decisões históricas estão em [Estratégia de Dados](docs/data_strategy.md), [Estratégia de Modelos](docs/model_strategy.md) e [Supplier Risk](docs/supplier_risk_model.md).
