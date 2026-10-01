# Invoice Anomaly — reformulação como triagem e diagnóstico do ranking

**Data:** 27/09/2026. **Estado:** diagnóstico concluído somente em TRAIN/VALIDATION.
**Decisão metodológica:** priorizar faturas incomuns para auditoria humana;
não classificar fraude automaticamente. Modelo, offset e 19 features preservados.

## 1. Definição final recomendada

O Invoice Anomaly é um **sistema de priorização de faturas com comportamento
tabular incomum para revisão humana**, inicialmente avaliado de forma retrospectiva
sobre um lote disponível. A unidade é a fatura; a saída é um score de anomalia
e sua posição no ranking. Não é confirmação de irregularidade, probabilidade
de fraude, autorização de bloqueio ou substituição da decisão do auditor.

Isolation Forest estima isolamento no espaço das features, sem aprender a
reproduzir is_fraud. Por isso, ranking para investigação é mais compatível
com seu objetivo do que classificação automática de fraude. Compatibilidade
conceitual não comprova eficácia operacional.

is_fraud permanece uma **referência secundária, imperfeita e não verificada**.
Precision@K neste documento é precisão relativa a essa referência, não porcentagem
de fraudes empresariais comprovadas. Um caso rotulado normal pode ser uma anomalia
útil; um positivo pode não ser estranho nas 19 dimensões observadas. A validade
prática ainda exige julgamento humano independente e contexto de negócio.

A [avaliação anterior](invoice_validation_results.md), o [protocolo anterior](invoice_validation.md)
e a [auditoria metodológica](invoice_methodological_audit.md) foram preservados.
O novo enquadramento não apaga o resultado limitado do threshold original nem
transforma retrospectivamente métricas de classificação em evidência de produção.

## 2. Método registrado antes da execução

O [protocolo de triagem](invoice_triage_protocol.md) foi gravado antes da inferência
e permaneceu inalterado. Usou-se o mesmo artefato Isolation Forest: 200 árvores,
contamination=0.22, random_state=42, n_jobs=-1, mesmas 19 features, sem fit/tuning.

- Score = negativo de score_samples; maior significa maior anomalia.
- TRAIN: 210.000 linhas, somente distribuições descritivas in-sample.
- VALIDATION: 30.000 linhas e 6.773 positivos da referência (22,5767%).
- Orçamentos fixos: 1%, 5%, 10%; K=ceil(n*percentual/100).
- Ranking por score decrescente; empates por invoice_id crescente, nunca pela label.
- Precision@K = positivos selecionados/K; captura = positivos selecionados/6.773;
  lift = Precision@K/prevalência.
- Referência aleatória analítica, sem novo estimador:
  E[positivos]=K*prevalência, E[Precision@K]=prevalência, E[captura]=K/n.
- Datas filtradas antes da materialização e associadas por invoice_id, não por posição.
- Quantis lineares fixados no protocolo; distância máxima entre CDFs empíricas
  apenas descritiva, sem p-value ou afirmação de significância estatística.
- Comparações de períodos internos usam os mesmos orçamentos, mas filas próprias;
  também se informa sua participação na fila global.

Os três orçamentos são cenários de capacidade, **não escolha de threshold**.
Os scores nas fronteiras são descritivos do lote; não foram implantados como
limiares. Não foi escolhido orçamento vencedor ou configuração nova.

## 3. Resultados observados: enriquecimento do ranking

| Orçamento | Faturas para revisão | Positivos da referência | Negativos da referência | Precision@K | Captura dos positivos | Lift sobre aleatório | Positivos esperados ao acaso |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1% | 300 | 255 | 45 | 85,00% | 3,76% | 3,76x | 67,73 |
| 5% | 1.500 | 645 | 855 | 43,00% | 9,52% | 1,90x | 338,65 |
| 10% | 3.000 | 980 | 2.020 | 32,67% | 14,47% | 1,45x | 677,30 |

Não ocorreram empates múltiplos nas três fronteiras observadas; a política de
desempate foi mesmo assim testada. Os grupos selecionados são aninhados e as
métricas não são experimentos estatisticamente independentes.

**OBSERVAÇÃO:** os três orçamentos concentram mais positivos do que a referência
aleatória. A menor fila contém 255 positivos em 300 faturas, contra 67,73 esperados
ao acaso. Entretanto, captura somente 3,76% dos 6.773 positivos disponíveis.
Na fila de 10%, a captura sobe a 14,47%, com 2.020 negativos da referência.

**INTERPRETAÇÃO:** há evidência de utilidade potencial para priorizar uma parte
dos casos desta fonte, principalmente os extremos. Isso não sustenta cobertura
global de fraude ou uma taxa garantida de acerto de auditoria. A redução de
volume frente aos 12.275 alertas do offset histórico decorre do orçamento fixado,
não de um aprimoramento do estimador. Não houve comparação otimizada de limiares.

### Composição: onde está o sinal

Cada célula informa **positivos da referência / faturas selecionadas daquele tipo**,
sem substituir fraud_type por is_fraud. Zeros indicam ausência do tipo na fila.

| fraud_type | Top 1% | Top 5% | Top 10% |
|---|---:|---:|---:|
| DOC_TAMPER | 5 / 5 | 13 / 13 | 29 / 29 |
| DUPLICATE | 0 / 0 | 0 / 0 | 1 / 1 |
| GHOST_SUPPLIER | 2 / 2 | 52 / 53 | 124 / 126 |
| INFLATED | 248 / 251 | 517 / 529 | 548 / 560 |
| NONE | 0 / 42 | 6 / 846 | 24 / 2025 |
| SPLIT | 0 / 0 | 57 / 59 | 254 / 259 |

**OBSERVAÇÃO:** no top 1%, 251 das 300 faturas são INFLATED; 248 dos 255
positivos também são INFLATED (**97,25% dos acertos da referência**).
No top 10%, entram 548 dos 553 positivos INFLATED, mas somente 254 dos 4.316
SPLIT e um dos oito DUPLICATE. Este último denominador é insuficiente para
conclusão robusta por mecanismo. Positivos NONE continuam explicitamente
incluídos, sem tentativa de resolver a ambiguidade da label.

As filas de 1%, 5% e 10% contêm, respectivamente, 3, 21 e 43 combinações
divergentes is_fraud/fraud_type, pela regra da auditoria anterior. Nenhuma foi
corrigida ou removida.

**HIPÓTESE:** o bom topo reflete alinhamento das representações de valor com
INFLATED. A composição observada é compatível com isso, mas não demonstra
causalidade nem que o IF acrescente valor sobre uma regra simples de valor alto.
Essa comparação não foi executada e deve ser definida previamente caso avance.

## 4. Distribuição dos scores e diferenças temporais

### TRAIN versus VALIDATION

| Quantil linear | TRAIN | VALIDATION |
|---|---:|---:|
| min | 0,436486 | 0,460485 |
| p01 | 0,455327 | 0,478160 |
| p05 | 0,464497 | 0,486686 |
| p25 | 0,482008 | 0,501935 |
| p50 | 0,497926 | 0,515757 |
| p75 | 0,517864 | 0,533723 |
| p95 | 0,559510 | 0,571894 |
| p99 | 0,605541 | 0,615575 |
| max | 0,694322 | 0,688747 |

A mediana aumenta de 0,497926 para 0,515757. A distância descritiva entre CDFs
é **0,31657**; nenhum score VALIDATION sai do intervalo mínimo/máximo TRAIN.
Portanto, permanecer na faixa de treino não implica ter a mesma distribuição.

**OBSERVAÇÃO:** há deslocamento da distribuição de scores.
**LIMITAÇÃO:** TRAIN é in-sample, e os períodos/composição/referências agregadas
diferem. A distância não isola drift temporal prejudicial, causalidade de uma
feature ou impacto econômico. Não foi executado teste de significância ou
experimento removendo calendário.

### Janelas parciais de VALIDATION

Setembro representa **14–30/09/2023**, outubro **01–20/10/2023**. Não são meses
completos nem múltiplas replicações temporais. TRAIN cobre 01/01–14/09/2023.

| Período | Faturas | Prevalência | Mediana do score | P@1% interno | P@5% interno | P@10% interno |
|---|---:|---:|---:|---:|---:|---:|
| 2023-09 | 13.970 | 22,49% | 0,516543 | 85,00% | 43,49% | 33,64% |
| 2023-10 | 16.030 | 22,65% | 0,515085 | 84,47% | 42,27% | 31,69% |

As filas internas usam K=140/699/1.397 em setembro e 161/802/1.603 em outubro,
com arredondamento para cima. Não são as mesmas seleções da fila global e não
devem ser somadas como se fossem seu resultado.

| Orçamento global | Setembro na fila | Outubro na fila | Participação de outubro na fila | Taxa selecionada de setembro | Taxa selecionada de outubro |
|---|---:|---:|---:|---:|---:|
| 1% | 136 | 164 | 54,67% | 0,97% | 1,02% |
| 5% | 729 | 771 | 51,40% | 5,22% | 4,81% |
| 10% | 1427 | 1573 | 52,43% | 10,21% | 9,81% |

**OBSERVAÇÃO:** outubro compõe 53,43% da base e aproximadamente 51,40%–54,67%
das filas globais. Suas medianas e Precision@K são próximas às de setembro.

**INTERPRETAÇÃO:** o diagnóstico não confirma a hipótese simplista de que a fila
seja dominada desproporcionalmente por outubro apenas porque esse mês não foi
visto. Isso não exclui efeito do calendário, efeito comum aos dois períodos ou
interações com outras features. Duas janelas parciais não provam estabilidade
sazonal ou ausência de drift.

### Mudança das features existentes

Não foram criadas features de modelo. O diagnóstico mede somente as 19 colunas
persistidas; máscaras de período/novidade são auxiliares, nunca entradas do IF.

| Feature | Distância CDF TRAIN/VALIDATION | Linhas VALIDATION fora da faixa TRAIN |
|---|---:|---:|
| invoice_amount | 0,00614 | 1 |
| log_invoice_amount | 0,00614 | 1 |
| supplier_age_days | 0,00348 | 0 |
| supplier_frequency | 0,04607 | 0 |
| country_frequency | 0,00570 | 0 |
| amount_vs_supplier_mean | 0,00640 | 0 |
| supplier_amount_zscore | 0,00734 | 6 |
| department_frequency | 0,00388 | 0 |
| amount_vs_department_mean | 0,00689 | 1 |
| supplier_department_frequency | 0,26978 | 3.659 |
| payment_terms_days | 0,00400 | 0 |
| invoice_type_encoded | 0,00237 | 0 |
| submission_hour_sin | 0,00527 | 0 |
| submission_hour_cos | 0,00546 | 0 |
| day_of_week_sin | 0,01147 | 0 |
| day_of_week_cos | 0,02317 | 0 |
| month_sin | 0,94771 | 16.030 |
| month_cos | 0,46637 | 0 |
| is_weekend | 0,00635 | 0 |

As maiores diferenças estão em calendário e frequência fornecedor/departamento.
A distância de month_sin é 0,94771; os 16.030 registros de outubro estão abaixo
do mínimo dessa feature no TRAIN. A codificação cíclica continua matematicamente
coerente, mas não elimina mudanças de suporte. Os quantis completos constam do JSON.

As 3.659 faturas com relação fornecedor/departamento ausente do TRAIN representam
12,20% de VALIDATION. Sua mediana de score é 0,520724; elas somam 41/205/422
faturas nas filas globais de 1%/5%/10% — participação de 13,67%/13,67%/14,07%.
Há sobrerrepresentação descritiva, não explicação causal de falsos positivos.

## 5. Suficiência das features e limites restantes

O diagnóstico reforça a necessidade de distinguir **incomum no espaço atual**
de **suspeito segundo o processo de compras**.

| Mecanismo | Cobertura atual | Limitação não resolvida |
|---|---|---|
| Valor inflado | Valor, log, razões e z-score | Sem preço unitário, quantidade, contrato ou referência de preço comparável |
| Duplicação | Perfil individual tabular | Sem comparação documental/pagamentos entre faturas |
| Fracionamento | Valor e frequência de relacionamento | Sem janelas de operações relacionadas e limites de aprovação |
| Fornecedor fantasma | Idade/frequência/cadastro indireto | Sem evidência de existência, vínculo bancário ou prestação efetiva |
| Adulteração | Sinais tabulares indiretos | Sem evidência documental independente avaliada |

Não há autorização para introduzir essas informações automaticamente. Origem,
chaves, disponibilidade antes da decisão e risco de leakage precisariam ser
confirmados. As fontes Supplier/Purchase não possuem integração real comprovada.

Permanecem: 4.847 divergências de labels em TRAIN/VALIDATION; procedência parcial
do fit legado; agregações autorreferentes que usam todo TRAIN; idade cadastral
sem referência temporal comprovada; fornecedores conhecidos nas duas partições;
ausência de ciclo anual completo e de julgamento humano/custos de investigação.
Nenhum desses problemas foi ocultado, corrigido manualmente ou declarado resolvido.

## 6. Evidência, qualidade e integridade

Execução registrada em **2026-09-27T16:03:53.267667+00:00**. Nova evidência:
[invoice_triage_validation_v1.json](../ml/experiments/invoice_triage_validation_v1.json).
Contém agregados, parâmetros, versões, hashes, quantis, composição e fingerprints
dos IDs selecionados. Não é um modelo ou dataset de features; não expõe fila
individual de produção.

SHA-256 do protocolo anterior à inferência:

```text
4ebeb61eca2133ac27bfd0c810cee7aaa125d9f36ac485f9b884263a4a4d21eb
```

SHA-256 do resultado:

```text
ff218d45c54c2376d43b0be46bfda93ba8eb438c8ebd72c395e67fe7cfbdfb3d
```

Modelo preservado:

```text
c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b
```

- 20 testes novos, sintéticos: ranking, ceil, empates sem labels, ausência de
  positivos, scores inválidos, CDF, fontes filtradas, datas por ID, ausência de
  fit, modelo incompatível, mudança dos inputs e recusa de sobrescrita.
- Revisões metodológica e de código independentes concluídas antes da execução.
- Suíte final: **283 passed in 14.61s**, usando fixtures temporárias, sem Kaggle,
  treinamento real ou acesso a TEST real.
- Ruff dos dois arquivos novos: **All checks passed!**.
- Ruff completo: **três avisos preexistentes**, não corrigidos por estarem fora
  do escopo Supplier: I001 e RUF100 em ml/supplier_risk/scripts/final_evaluation.py;
  I001 em tests/supplier_risk/test_final_evaluation_artifact.py. Os dois arquivos
  coincidem com HEAD; não foram alterados para fazer a checagem parecer limpa.
- 31 hashes de arquivos protegidos e 36 registros de tamanho/mtime de dados/modelos
  preservados. Entre os hashes: modelo Invoice, evidências históricas, código
  existente e arquivos Supplier, inclusive o notebook EDA protegido.
- Arquivos de dados TEST foram verificados somente por tamanho/mtime, não abertos
  para hash. Fontes globais têm filtros lógicos: não se promete isolamento físico
  dos bytes de row groups compartilhados nem hash completo dessas fontes.
- Agregados, filas por período e hashes registrados reconciliados sem nova inferência.
- git diff --check e verificação de whitespace dos cinco arquivos novos sem erros;
  links locais conferidos. Avisos informativos de conversão LF/CRLF do Git não
  representam alteração dos datasets ou falha de whitespace.
- Nenhum dataset, split, ML-Ready, modelo, label ou feature existente foi alterado.

Python 3.14.3, pandas 2.3.3, numpy 2.5.2, pyarrow 25.0.1, scikit-learn 1.9.0,
joblib 1.6.0; ambiente isolado preexistente, sem instalação ou mudança de pins.
Foi executada uma chamada de score_samples em TRAIN e uma em VALIDATION;
zero fits reais, zero tuning, zero seleção de threshold, zero leitura analítica
de TEST. Supplier Risk/Purchase não foram executados com dados reais.
Não houve notebook, frontend, staging ou commit.

## 7. Entrega e execução

Criados nesta etapa:

- docs/invoice_triage_protocol.md — contrato anterior à inferência;
- docs/invoice_triage_results.md — este relatório;
- ml/scripts/diagnosticar_triagem_invoice.py — diagnóstico somente leitura;
- tests/invoice/test_invoice_triage.py — testes sintéticos;
- ml/experiments/invoice_triage_validation_v1.json — resultado exclusivo.

README, roadmap e somente a seção Invoice da estratégia de modelos foram
atualizados para refletir triagem; mudanças locais anteriores foram preservadas.

Comando do diagnóstico, **já executado**:

```powershell
python -m ml.scripts.diagnosticar_triagem_invoice --split val
```

A saída já existe: a reexecução é recusada antes de ler dados. Para consulta,
ler o JSON; não apagar evidência para repetir. Comandos de qualidade:

```powershell
python -I -B -m pytest -q -p no:cacheprovider
python -I -m ruff check ml/scripts/diagnosticar_triagem_invoice.py tests/invoice/test_invoice_triage.py --no-cache
git diff --check
```

Usar ambiente isolado funcional com os pins atuais; não presumir que a venv
principal esteja funcional. A venv temporária usada pode ser removida pelo sistema.

## 8. Próximo passo recomendado

**Conclusão:** há sinal promissor de enriquecimento do topo, concentrado em
INFLATED, mas utilidade de triagem ampla e operacional ainda não está validada.
Nenhum dos três orçamentos foi escolhido para implantação; TEST continua fechado.

O menor avanço útil é definir um **protocolo de utilidade da triagem**, ainda
somente em TRAIN/VALIDATION:

1. Definir quem revisaria faturas, quais evidências sustentam uma anomalia útil,
   instante de uso e capacidade/custo de investigação.
2. Planejar comparação prévia com uma regra simples de priorização por valor,
   para verificar se o IF acrescenta sinal além dos extremos monetários. Não
   escolher regra/orçamento retrospectivamente para maximizar a métrica.
3. Quando houver documentação/evidência de negócio suficiente, revisar amostras
   do topo e uma referência aleatória, com critérios independentes de is_fraud
   e sem revelar o score ao revisor quando viável; distinguir achado útil de fraude.
4. Se esses insumos não existirem, limitar a conclusão acadêmica ao enriquecimento
   observado na referência não verificada. Não simular validação humana ou empresarial.

Depois, e não nesta etapa, decidir se uma comparação controlada de representação
é justificada. Produção e TEST exigem contrato final e autorização próprios.
