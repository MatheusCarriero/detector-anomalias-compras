# Detector Inteligente de Anomalias em Compras

Projeto acadêmico de Machine Learning para identificar comportamentos anômalos em compras e faturas. Nesta etapa, o projeto organiza e prepara os dados para modelagem, sem treinar ou disponibilizar o modelo em uma aplicação.

## Objetivo

O sistema busca identificar padrões incomuns em dados de compras por meio de técnicas de Machine Learning não supervisionado. O foco inicial é o algoritmo Isolation Forest.

## Tecnologias

Tecnologias utilizadas atualmente:

- Python
- Pandas
- NumPy
- Scikit-learn
- PyArrow
- Isolation Forest

Tecnologias planejadas para etapas posteriores:

- FastAPI
- PostgreSQL
- React
- TypeScript

O backend, o banco de dados e o frontend ainda não fazem parte da implementação atual.

## Machine Learning

O primeiro modelo utilizará Isolation Forest, um algoritmo não supervisionado para detecção de anomalias. Os labels existentes no dataset não serão usados como features durante o treinamento. A coluna `is_fraud` será utilizada somente na avaliação posterior do desempenho do modelo; `fraud_type` será reservado para análises complementares.

Para evitar data leakage, campos derivados do risco conhecido (`supplier_risk_score` e `blacklisted_flag`), labels e explicações não entram nas features. As estatísticas históricas de fornecedores, departamentos, países e relações fornecedor/departamento são calculadas exclusivamente no conjunto de treino.

## Dataset principal

O **Procurement Invoice Fraud Dataset** contém 300.000 faturas, divididas oficialmente em:

- 210.000 registros de treino
- 30.000 registros de validação
- 60.000 registros de teste

Os dados brutos e processados não são armazenados no GitHub.

## Dataset auxiliar

O **Procurement KPI Analysis Dataset** contém 777 pedidos de compra. Ele será utilizado futuramente como experimento complementar ou demonstração adicional de detecção de anomalias.

## Instalação

Crie e ative um ambiente virtual Python e instale as dependências:

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

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
│   └── processed/
├── ml/
│   ├── scripts/
│   ├── models/
│   └── notebooks/
├── backend/
├── frontend/
├── docs/
├── .gitignore
├── requirements.txt
└── README.md
```

## Execução dos scripts

Execute os scripts a partir da raiz do projeto, na ordem atual:

```bash
python ml/scripts/analisar_dataset.py
python ml/scripts/validar_dataset.py
python ml/scripts/preparar_features.py
```

Para inspecionar o dataset auxiliar:

```bash
python ml/scripts/inspecionar_dataset_auxiliar.py
```

Os caminhos são resolvidos a partir da localização dos próprios scripts, portanto os comandos também funcionam quando chamados a partir de outro diretório.

## Status do projeto

- [x] Seleção dos datasets
- [x] Inspeção dos dados
- [x] Análise exploratória
- [x] Validação dos labels
- [x] Identificação de possíveis data leakages
- [x] Feature engineering
- [x] Separação Train / Validation / Test
- [ ] Treinamento do Isolation Forest
- [ ] Ajuste de hiperparâmetros
- [ ] Definição de threshold
- [ ] Avaliação no conjunto de teste
- [ ] Salvamento do modelo
- [ ] Backend FastAPI
- [ ] Banco PostgreSQL
- [ ] Frontend React
- [ ] Integração completa
