# Detector Inteligente de Anomalias em Compras

Projeto acadêmico de Machine Learning com três domínios independentes: anomalias em faturas, classificação de risco de fornecedores e risco de pedidos de compra. O Invoice possui um Isolation Forest treinado; o Supplier Risk possui dados ML-Ready, mas ainda não possui EDA, modelo treinado ou avaliação. Backend e frontend ainda não estão implementados.

## Objetivo

O Invoice Anomaly Model identifica padrões incomuns em faturas com Isolation Forest. O Supplier Risk Model será uma classificação supervisionada de `Risk_Level`: estimar o pertencimento à classe de risco definida pelo dataset, não prever acontecimentos futuros. O Purchase Risk Model mantém seu escopo de análise de pedidos antes da aprovação.

As fontes representam populações diferentes, sem chaves reais comuns para integração. Não há merge direto entre suas features. Uma eventual integração de scores seria uma etapa conceitual futura, com validação própria. O Procurement KPI é somente auxiliar.

## Estado atual

| Domínio | Concluído | Pendente |
|---|---|---|
| Invoice Anomaly | Inspeção, validação, 19 features, split oficial, Isolation Forest treinado e salvo | Revisão metodológica da avaliação, seleção de threshold/hiperparâmetros e avaliação final |
| Supplier Risk | Base por fornecedor, qualidade, auditoria do target, split determinístico, ML-Ready com imputação train-only, suíte pytest sintética | EDA somente em TRAIN, baseline, modelos candidatos e avaliação |
| Purchase Risk | Dataset analisado e estratégia pré-aprovação definida | Feature engineering, modelagem e avaliação |

Esta consolidação de qualidade não executou treinamento, EDA nem reprocessamento dos dados reais. O artefato Invoice existente não foi modificado.

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

Para evitar data leakage, campos derivados do risco conhecido (`supplier_risk_score` e `blacklisted_flag`), labels e explicações não entram nas features. As estatísticas históricas de fornecedores, departamentos, países e relações fornecedor/departamento são calculadas exclusivamente no conjunto de treino.

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

**Ambiente atualmente validado com Python 3.14.3.** A versão está registrada em `.python-version`; não há alegação de compatibilidade com outras versões.

`requirements.txt` fixa as dependências de execução e suas transitivas verificadas; `requirements-dev.txt` inclui execução, pytest e Ruff. Não foi feito upgrade de bibliotecas. Matplotlib não está instalado nem é importado pelos scripts atuais; XGBoost não foi adicionado.

Procedimento de instalação para um ambiente novo, sujeito à limitação abaixo (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

**Limitação de reprodução:** as versões fixadas correspondem ao ambiente local funcional, e a sintaxe/compatibilidade declarada das dependências foi conferida. Entretanto, a resolução limpa com `--ignore-installed --only-binary=:all:` falhou porque não há wheel de `pandas==2.2.2` para o Python 3.14 desta execução. Instalação a partir do código-fonte e instalação completa em ambiente novo não foram validadas. Fixar versões não resolve essa indisponibilidade; a reprodução em um clone novo ainda depende de resolver esse ponto, sem upgrades silenciosos.

Para executar os testes nesta consolidação foi criada uma `.venv` local com `--system-site-packages`, reutilizando as bibliotecas já funcionais. Foram adicionados somente pytest 9.1.1, iniconfig 2.3.0 e pluggy 1.6.0 nessa `.venv`; o ambiente principal não foi atualizado. Isso valida os testes localmente, **não uma instalação limpa**.

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

**CI:** não foi criado `.github/workflows/quality.yml`, pois ainda não foi demonstrada uma instalação limpa confiável para a combinação fixada de Python/pandas. A suíte já é independente dos datasets e poderá ser utilizada em CI quando essa limitação do ambiente for resolvida.

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

Todas as estatísticas históricas são calculadas somente no conjunto de treino para evitar data leakage.

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

EDA somente no TRAIN → baseline ingênua majoritária e Logistic Regression → Random Forest / Gradient Boosting candidatos → avaliação em validation → escolha → avaliação final única em test.

XGBoost dependerá de justificativa futura. Accuracy isolada não será suficiente para a distribuição aproximada de 30% classe 0 e 70% classe 1; estão previstas confusion matrix, precision, recall, F1-score, ROC-AUC e PR-AUC quando aplicável. Não se pretende prever fraude, eventos futuros, rupturas ou probabilidade real de falha, nem substituir avaliação humana.

O projeto ainda não possui aplicação backend/frontend, banco integrado ou avaliação final consolidada. Os detalhes e decisões históricas estão em [Estratégia de Dados](docs/data_strategy.md), [Estratégia de Modelos](docs/model_strategy.md) e [Supplier Risk](docs/supplier_risk_model.md).
