# Invoice Anomaly — resultado da baseline em VALIDATION

## 1. Decisão de prioridade e escopo concluído

Em 24/09/2026, a revisão do checkout `b624204` confirmou:
Invoice tem preparação de 19 features e Isolation Forest salvo; Purchase possui
apenas auditoria/documentação e pastas vazias; backend/frontend são placeholders.
Supplier concluiu sua avaliação acadêmica e ficou fora desta execução.

Foi priorizada a fase 6 do roadmap: medir a baseline Invoice já existente.
Purchase exige antes decidir anomalia vs desfecho, target/horizonte quando
aplicáveis, disponibilidade pré-aprovação, política de moedas e avaliação.
Não foi criado modelo, feature, frontend, serviço ou mecanismo de score combinado.

**Executado:** uma inferência em 30.000 faturas de VALIDATION, zero fits reais,
sem tuning ou alteração de threshold. Invoice TEST e Supplier TEST não foram
carregados. Modelo, metadata, features e datasets existentes foram preservados.
A implementação está em `ml/scripts/avaliar_invoice.py`; o
[protocolo prévio](invoice_validation.md) permaneceu inalterado após a inferência.

## 2. Configuração e evidência

- Isolation Forest existente: 200 árvores, contamination=0.22, seed 42, n_jobs=-1.
- Mesmas 19 features ordenadas; IDs, labels e fraud_type excluídos da entrada.
- Score: negativo de score_samples, maior indica maior anomalia.
- Offset original: `-0.5211491197816622`; limiar equivalente do score:
  `0.5211491197816622`.
- Classificação: decision_function < 0; igualdade é normal.
- Execução registrada em `2026-09-24T13:04:00.697102+00:00`.
- Resultado: [invoice_validation_v1.json](../ml/experiments/invoice_validation_v1.json).
- Python 3.14.3, pandas 2.3.3, numpy 2.5.2, scikit-learn 1.9.0,
  joblib 1.6.0 e pyarrow 25.0.1, sem mudanças nos pins do projeto.

SHA-256 do resultado completo:

```text
1218ed395095c69dd8d3439e27b7e1416dfeba68b8f1d9d83328e2c2f27e12f9
```

SHA-256 do protocolo anterior à inferência:

```text
16176cf0ec2a2754b65fc8fb658f1a67791110e65291d66124c1317f014708a6
```

SHA-256 do modelo, preservado antes/depois:

```text
c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b
```

O JSON registra hashes de fonte, features, modelo, metadata, script e contrato
de features, fingerprint dos IDs, versões, parâmetros e regra de score.
Esses hashes identificam os arquivos atuais, mas o metadata antigo não contém
hash dos inputs/ambiente do fit original; não certificam retroativamente sua origem.

## 3. Resultados observados

Valores arredondados a cinco casas; precisão completa no JSON, sem recalcular
métricas para produzir este documento. Fraude positiva = is_fraud=1.

| Métrica | Isolation Forest existente | Referência nunca alertar |
|---|---:|---:|
| Average Precision (principal) | 0,31607 | 0,22577 |
| ROC-AUC | 0,57976 | 0,50000 |
| F1-macro | 0,52434 | 0,43638 |
| Balanced accuracy | 0,55423 | 0,50000 |
| Precision fraude | 0,27210 | 0,00000 |
| Recall fraude | 0,49313 | 0,00000 |
| F1 fraude | 0,35069 | 0,00000 |
| Accuracy (complementar) | 0,58773 | 0,77423 |
| Proporção de alertas | 0,40917 | 0,00000 |

Average Precision usa `average_precision_score`, não área trapezoidal da curva PR.
A referência não discrimina as classes: sua AP é a prevalência de fraude
(6.773/30.000). Accuracy sozinha favorece a previsão de normalidade.

Matriz de confusão: linhas reais, colunas previstas, ordem [0, 1].

| | Previsto normal | Previsto anomalia |
|---|---:|---:|
| Real normal | 14292 | 8935 |
| Real fraude | 3433 | 3340 |

O modelo emite 12.275 alertas; 3.340 correspondem às fraudes rotuladas e 8.935
a normais. O FPR sobre normais é 0,38468.
A taxa de alertas em VALIDATION não precisa ser 22%: contamination define o
offset usando TRAIN, não um orçamento fixo de alertas em dados novos.

### Resultado por tipo informado pela fonte

| fraud_type | Faturas | Fraudes rotuladas | TP | FN | Recall entre fraudes | Normais rotulados | FP |
|---|---:|---:|---:|---:|---:|---:|---:|
| DOC_TAMPER | 230 | 226 | 110 | 116 | 0,48673 | 4 | 0 |
| DUPLICATE | 8 | 8 | 2 | 6 | 0,25000 | 0 | 0 |
| GHOST_SUPPLIER | 1254 | 1224 | 493 | 731 | 0,40278 | 30 | 9 |
| INFLATED | 565 | 553 | 553 | 0 | 1,00000 | 12 | 12 |
| NONE | 23533 | 446 | 159 | 287 | 0,35650 | 23087 | 8873 |
| SPLIT | 4410 | 4316 | 2023 | 2293 | 0,46872 | 94 | 41 |

Recall por tipo usa somente is_fraud=1 daquele grupo; não é precision de
classificação multiclasse. A categoria DUPLICATE contém apenas oito casos;
não sustenta uma conclusão robusta de generalização. INFLATED teve recall 1
nesta amostra, mas também sinalizou seus 12 normais; não significa perfeição
de um detector específico dessa fraude.

### Fornecedores observados/não observados

As 30.000 faturas possuem supplier_frequency > 0 segundo as estatísticas do
TRAIN geradas pelo pipeline existente. O grupo não observado possui zero casos;
seu recall/FPR são null. Não há evidência de desempenho para fornecedores novos.
Essa classificação depende da semântica da feature, não de uma nova fonte de IDs.

## 4. Interpretação e pendências metodológicas

**OBSERVADO:** há ganho de ordenação sobre a referência trivial, mas discriminação
modesta (ROC-AUC 0,57976), recall de fraude 0,49313 e precision de alerta 0,27210.
O volume de falsos positivos é elevado. A configuração não está demonstrada
como útil operacionalmente, e não deve ser apresentada como detector de fraude
pronto. Não se tentou melhorar o resultado nesta execução.

**OBSERVADO — referência de avaliação:** há 446 linhas is_fraud=1 com
fraud_type=NONE; outras 140 têm is_fraud=0 com tipo diferente de NONE.
Esses valores reconciliam exatamente com labels.parquet por invoice_id:
não foram introduzidos pelo join do avaliador. O manifest disponível só
informa versão, data e contagens; não explica a regra de rotulagem.
O script histórico validar_dataset.py já contém verificações dessas combinações;
ele não foi executado, pois carrega a fonte global e não restringe holdouts.

**HIPÓTESES, não conclusões:** a diferença entre tipos pode refletir alinhamento
das features a determinadas anomalias, particularidades de geração ou ruído da
fonte. Não há evidência suficiente para atribuir causalidade, explicar a regra
de labels ou afirmar que trocar o algoritmo resolverá o problema.

**LIMITAÇÕES:** anomalia não é probabilidade de fraude; dados e label não provam
fraude empresarial real; agregações de todo TRAIN não são ponto-a-ponto
temporais; fornecedores já conhecidos dominam a avaliação; não há evidência
externa/temporal, custos de erro definidos ou intervalos de confiança novos.
O artefato legado não identifica por hash seu treinamento original.

## 5. Implementação, validação e integridade

**Nota técnica de 06/10/2026:** os itens abaixo descrevem a execução histórica.
Filtrar IDs não garante isolamento físico dos raw compartilhados; não certifica
ausência de leitura física de TEST. A rota histórica atualmente recusa o checkout
real e é exercitada apenas com fixtures. Não reexecutar nem copiar fontes reais
para contornar a guarda. O [contrato vigente](invoice_final_executor.md) mantém
`source_reconciled=false`; os resultados e JSON históricos não foram alterados.

- Avaliador importa o contrato seguro de features sem acionar treino.
- Recusa qualquer split diferente de val antes de I/O.
- Confere schema, tipos, nulos/infinitos, IDs e disjunção train/val, IDs frente ao
  split oficial e labels/fraud_type por ID; não associa linhas por posição.
- Lê labels somente para IDs val e atribuições oficiais somente train/val.
- Valida tipo, parâmetros, número de árvores e features do modelo; divergência
  de versão sklearn interrompe em vez de retreinar.
- Mantém offset original, verifica direção de score e regra de predict;
  gera métricas agregadas, grupos com denominadores explícitos e saída exclusiva.
- Testes novos passaram pelo ciclo RED→GREEN. Validação final de código:
  **38 testes Invoice aprovados em 8,30s**, Ruff dos dois arquivos novos
  `All checks passed!`, pip check sem conflitos. Nenhum teste/experimento
  Supplier foi repetido. A revisão independente não apontou bloqueadores.
- Conferência pós-execução preservou os **51 arquivos protegidos monitorados**,
  incluindo modelo Invoice, artefatos/notebooks Supplier e notebook EDA.
  Arquivos TEST foram excluídos dessa leitura de hashes e não foram abertos.
- Inputs/code/protocolo do JSON conferidos; contagens dos grupos reconciliadas
  com o agregado. Verificação de integridade não executa inferência novamente.

A venv temporária anterior estava incompleta e a principal não conseguia
importar pandas por dependências ausentes. Foi criada uma venv nova separada
com exatamente requirements-dev.txt, sem upgrade/downgrade ou alteração da
venv principal. O ambiente usado naquela etapa era temporário e externo ao
repositório; seu caminho pessoal não é requisito de reprodução.

Ambientes temporários podem ser removidos pelo sistema. Para continuidade técnica,
criar ambiente isolado com os pins do README quando necessário;
não presumir que a venv principal esteja funcional.

## 6. Encerramento e próximo passo exato

Entregue: avaliador funcional e testado, protocolo prévio, resultado agregado
verificável e documentação do desempenho real. Não há novo modelo nem mudança
de metodologia de treinamento. O JSON não é um modelo serializado de produção.

**Próximo incremento recomendado:** auditoria restrita a TRAIN/VALIDATION da
referência is_fraud versus fraud_type e da procedência do artefato Invoice.
Registrar explicitamente o significado dessas divergências, ou sua ausência
de explicação; verificar limites das transformações e documentar o uso pretendido
antes de definir qualquer experimento de threshold. Não corrigir labels por
suposição, não abrir TEST e não trocar algoritmo para compensar métricas.

Somente depois desse diagnóstico definir antecipadamente objetivo operacional,
métricas/custos, orçamento de comparação em validação e eventual congelamento
para avaliação final autorizada. A baseline atual permanece preservada.
Purchase continua pendente de contrato de problema. Supplier permanece encerrado.

Para validação de código, usar o Python do ambiente isolado:

```powershell
python -I -B -m pytest -q -p no:cacheprovider tests/invoice
python -I -m ruff check ml/scripts/avaliar_invoice.py tests/invoice/test_evaluate_invoice.py --no-cache
git diff --check
```

Para consulta, ler o JSON existente. Não apagar a saída para repetir o comando
de avaliação. Nenhum commit foi criado nesta tarefa.
