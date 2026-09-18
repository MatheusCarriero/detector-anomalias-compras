# Fechamento de engenharia — desenho e limites

Data: 2026-09-17. Estado: aprovado para execução autônoma conforme solicitação do usuário.

## Objetivo

Fechar lacunas de engenharia verificáveis antes de avançar a avaliação final do
Supplier Risk, preservando os três domínios independentes. Esta entrega não
conclui o produto inteiro nem transforma experimentos em modelos de produção.

## Diagnóstico inicial — antes da implementação

- Supplier possui preparação, split, ML-ready, EDA TRAIN, baselines e validação
  científica documentadas. As predições individuais não foram persistidas como
  evidência histórica verificável. Não é possível reconstruí-las a partir de
  métricas agregadas sem reexecutar experimentos.
- O script Invoice de treinamento executa leitura, fit e escrita ao ser
  importado. Falta uma fronteira explícita entre biblioteca e comando.
- Parte da documentação ainda descreve EDA/treinamento Supplier como não
  realizados. A ausência de um modelo final não significa ausência de
  experimentos.
- Purchase ainda exige definição de objetivo, unidade operacional e contrato
  pré-evento. Backend, frontend e composição de scores dependem desses contratos.
- A suíte sintética inicial passou: 113 testes; Ruff sem avisos no worktree.

## Alternativas e decisão

1. **Escolhida: fechamento pequeno de engenharia e roadmap completo.** Corrigir
   importação insegura, oferecer registro/verificação de evidência experimental
   futura e reconciliar documentação.
2. Somente documentação deixaria riscos executáveis sem cobertura de testes.
3. Implementar novos modelos e a aplicação inteira agora exigiria inventar
   decisões metodológicas ainda abertas e poderia violar o congelamento de TEST.

## Invariantes

- Sem commit, push, treinamento real, execução de notebook ou novo experimento.
- Atualização de 2026-09-18: integração e staging seletivo dos 12 arquivos de
  engenharia estão autorizados; criar commit requer nova autorização explícita.
- TEST permanece fechado. Nenhum dataset, split, target, ML-ready, modelo,
  score ou resultado histórico será modificado.
- A metodologia Invoice permanece igual: 19 features, TRAIN, IsolationForest
  com 200 árvores, contamination=0.22, random_state=42 e n_jobs=-1.
- Supplier estima pertencimento a Risk_Level do dataset; não risco empresarial
  validado nem probabilidade real de falha.
- Purchase e KPI permanecem sem nova implementação de modelagem.
- Sem alteração de dependências, versão Python ou arquitetura de pastas.
- Alterações anteriores do usuário são preservadas.
- Exceção de estado autorizada no encerramento: a alteração já existente em
  `ml/supplier_risk/notebooks/01_supplier_risk_eda.ipynb` permanece integralmente
  no checkout principal, fora da integração e do staging de engenharia.

## Componente 1 — comando Invoice seguro

Separar validação e execução em funções; adicionar main guard. Importar o módulo
não poderá ler datasets, ajustar estimador nem escrever artefatos. A execução
explícita do comando conserva caminhos, leitura seletiva e metadata existentes.
Validação deve rejeitar vazio, esquema diferente das 19 features ordenadas,
tipos não numéricos reais, nulos e infinitos antes do fit.
Os testes usarão dados sintéticos e dublês de I/O/estimador; não executarão
treinamento com dados reais.

## Componente 2 — contrato de evidência Supplier

Novo módulo de biblioteca padrão, sem pandas/sklearn, sem carregamento de dados
ou modelos. APIs públicas:

- write_experiment_record(path, predictions, metadata): valida e grava JSON novo;
- verify_experiment_record(path): valida estrutura, invariantes e digest;
- CLI: experiment_artifact.py verify caminho.json.

Um arquivo representa um estimador/configuração/cenário. predictions é uma lista
de objetos com exatamente supplier_id, split, y_true, y_pred e
probability_class_1. IDs são strings não vazias, sem espaços nas extremidades,
únicas em todo o artefato. split aceita somente train e validation. Classes são
inteiros 0/1, não bool; probabilidades são reais finitas entre 0 e 1.
Linhas são ordenadas canonicamente por split e supplier_id.

Metadata obrigatório:

- experiment_name, estimator: strings não vazias;
- scenario: A, B, C ou D;
- features: lista ordenada exata do cenário (contrato atual de 10 features,
  B sem índice geopolítico, C sem contagem, D sem ambos);
- parameters: objeto JSON estrito com valores finitos;
- seeds: objeto não vazio de nome para inteiro, sem bool;
- versions: objeto não vazio de nome para string não vazia;
- input_hashes: objeto não vazio de nome para SHA-256 hexadecimal;
- code_sha256: SHA-256 hexadecimal;
- expected_id_hashes: mapa dos splits presentes para SHA-256 da lista ordenada
  de IDs, calculado com JSON canônico UTF-8.

Metadata opcional: notebook_sha256, também validado. Campos inesperados falham.
A lista ordenada de IDs é serializada com ensure_ascii=False, sort_keys=True,
separadores compactos e allow_nan=False para calcular os fingerprints.

Envelope: schema_version, created_at UTC, artifact_id e payload. Payload contém
domain=supplier_risk, target=Risk_Level, probability_semantics, metadata,
predictions, record_count e id_hashes. artifact_id é SHA-256 do payload canônico;
não inclui timestamp e é estável sob reordenação das linhas fornecidas.
O verificador recusa chaves duplicadas, números não finitos, esquema desconhecido,
digest ou IDs divergentes e qualquer split fora da allowlist.

Validar e serializar antes de criar diretórios. Escrita exclusiva, sem
sobrescrever destino existente. Não prometer transação entre múltiplos arquivos.
O CLI verifica apenas o JSON indicado e retorna código não zero em falhas.

O checksum detecta inconsistência interna; não é assinatura nem atestado de
procedência. Hashes de origem e listas esperadas são fornecidos pelo chamador:
não provam que TEST nunca foi lido. A API não permite armazenar resultados TEST
nesta versão. Nenhum registro histórico real será fabricado nesta entrega.

## Componente 3 — documentação e caminho até finalizar

Atualizar README, data_strategy, model_strategy e supplier_risk_model sem apagar
informações úteis. Acrescentar guia do contrato experimental e roadmap com
implementado / planejado / limitação, responsabilidades e critérios de saída.
Não selecionar vencedor A/D, threshold ou objetivo Purchase.

## Validação e integração

Implementação em worktree detached isolado, sem copiar dados reais. Agentes
trabalham em arquivos disjuntos; revisão independente de cada tarefa e do conjunto.
TDD sintético, Ruff, pytest e git diff --check. Integrar somente arquivos
autorizados após comparar estado original; conferir hashes dos artefatos protegidos
e atributos dos arquivos TEST sem abri-los. Nenhum commit.

Para o encerramento, o usuário confirmou 196 testes aprovados e Ruff limpo na
validação manual. Essa evidência é anterior à integração: não repetir testes ou
Ruff nesta etapa. Encerrar por revisão documental, conferência do diff, comparação
do conteúdo integrado com o aprovado e preservação dos arquivos protegidos.

## Decisões autônomas e consequências

- O escopo executado é engenharia; decisões de negócio/modelagem permanecem no
  roadmap, portanto o produto ainda não estará pronto para produção.
- A autorização para execução sem perguntas substitui pausas de aprovação das
  skills; revisões independentes continuam obrigatórias.
- Tarefas disjuntas podem ser paralelas, por solicitação do usuário. A integração
  deve verificar conflitos e preservar alterações anteriores.
- Notebooks históricos não serão refatorados ou reexecutados. A lacuna histórica
  de predições individuais permanece explicitamente documentada.

## Riscos residuais prioritários

Procedência de Risk_Level e geopolitical_risk_index; semântica de
supplier_record_count; escala de environmental_compliance; lead time zero;
ausência de validação externa/temporal; publicação sequencial de artefatos de
preparação que pode deixar saídas antigas/mistas após falhas; lógica experimental
em notebooks ainda não extraída para módulos testáveis. Documentar sem inventar
correções estatísticas ou alterar dados.
