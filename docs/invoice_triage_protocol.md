# Invoice Anomaly — protocolo de triagem em VALIDATION

**Versão:** invoice-triage-1.0. **Data:** 27/09/2026.
Registrado antes da nova inferência diagnóstica; resultados em documento separado.
A avaliação classificatória anterior permanece como histórico, sem alteração.

## Objetivo e interpretação

Priorizar faturas de comportamento incomum para auditoria humana. A saída é
um ranking de anomalia, não decisão automática de fraude, probabilidade de fraude,
bloqueio de pagamento ou modelo supervisionado de is_fraud. Isolation Forest é
compatível com esse objetivo porque aprende isolamento no espaço de atributos,
sem otimizar a reprodução das labels. Isso não garante utilidade para auditores.

is_fraud é referência secundária não verificada: mede enriquecimento de fraudes
rotuladas no ranking. fraud_type descreve a composição, sem corrigir qualquer
campo. Faturas rotuladas normais também podem conter anomalias relevantes;
a utilidade real exige avaliação humana independente, ainda não disponível.

## Configuração e fronteira

- Modelo e metadata existentes, mesmos hashes da avaliação anterior.
- Isolation Forest, 200 árvores, contamination=0.22, seed=42, n_jobs=-1;
  19 features existentes, na mesma ordem, sem fit, tuning ou transformação nova.
- Score = -score_samples: maior significa maior anomalia, não probabilidade.
- TRAIN: somente distribuição descritiva de scores e features, in-sample.
- VALIDATION: ranking e análise da referência. TEST nunca materializado.
- Datas de invoices somente para IDs TRAIN/VALIDATION, alinhadas por chave.
- Nenhum arquivo separado de TEST aberto, inclusive para hash. Fontes globais
  compartilhadas usam filtros antes da materialização; row groups podem conter
  outras partições, sem análise desses registros.
- Nenhum comando histórico de treinamento/preparação ou notebook executado.
- Supplier Risk e Purchase fora do escopo.

## Ranking pré-definido

Três orçamentos: 1%, 5%, 10%, todos reportados, sem selecionar o melhor.
K = ceil(n * percentual / 100), limitado a n. No lote VALIDATION esperado,
isso corresponde a 300, 1.500 e 3.000 faturas. A fila substitui apenas a
interpretação operacional, não altera o offset do modelo ou as métricas antigas.

Ordenação: score decrescente; empates por invoice_id crescente, nunca pela label.
Registrar tamanho do empate na fronteira e quantos empatados entraram. O ID
somente desempata e rastreia, não entra como feature. Reportar K e fração efetiva.

Para cada orçamento:

- positivos selecionados / K = Precision@K da referência is_fraud;
- positivos selecionados / total de positivos = captura da referência;
- Precision@K / prevalência = lift;
- composição por fraud_type, positivos e divergências is_fraud/fraud_type;
- referência aleatória analítica: E[positivos]=K*prevalência,
  E[Precision@K]=prevalência, E[captura]=K/n e E[lift]=1, se houver positivos.
  Não há amostragem aleatória executada nem novo estimador.

Denominadores inexistentes produzem null, não ganho fabricado. Não se fará
relabeling, tuning de orçamento, seleção de threshold ou filtragem de casos
difíceis. O menor score selecionado descreve o lote, não um limiar implantável.

## Diagnóstico temporal e atributos

Fixar quantis min, 1%, 5%, 25%, 50%, 75%, 95%, 99%, max, método linear.
Comparar TRAIN/VALIDATION para scores e cada uma das 19 features existentes,
incluindo proporção fora da faixa TRAIN e distância máxima entre CDFs empíricas
(estatística KS descritiva, sem p-value ou teste de significância).

VALIDATION será desagregada por ano-mês de invoice_date, mostrando datas reais:
setembro e outubro são períodos parciais. Para cada grupo:

- tamanho, prevalência, quantis de score e ranking interno nos mesmos percentuais;
- participação do período no top-K global (denominador K);
- taxa de seleção global dentro do período (denominador tamanho do período).

Registrar também relação fornecedor/departamento não vista
(supplier_department_frequency=0) e mês ausente de TRAIN, com scores descritivos
e participação nas filas globais. Não atribuir diferenças causalmente à feature:
tempo, população, representação, agregações e avaliação in-sample são confundidos.
Não calcular novas features para o modelo; máscaras de auditoria ficam fora dele.

Este ranking é retrospectivo sobre um lote disponível. Não demonstra seleção
online nem disponibilidade ponto-a-ponto das features. Não define capacidade de
trabalho, custos, orçamento de produção ou valor econômico. A referência
aleatória é mínima e não substitui comparação futura com regras de auditoria.

## Evidência e validação

Implementar diagnóstico separado, reutilizando o carregador seguro de VALIDATION.
Publicar exclusivamente ml/experiments/invoice_triage_validation_v1.json,
sem sobrescrever resultados existentes. Registrar hashes de inputs permitidos,
modelo, metadata, avaliação anterior, código, contrato e deste protocolo;
fingerprints das linhas de datas autorizadas e dos IDs selecionados; versões,
parâmetros, quantis e fórmulas. Não exportar modelo ou dataset de features novo.
A procedência do fit legado permanece parcialmente desconhecida.

Antes da inferência real: testes sintéticos de ranking, empates, denominadores,
alinhamento de datas, bloqueio de TEST, ausência de fit e sobrescrita; revisão
independente. Depois: conferir resultados, hashes, qualidade do código e escopo.
Próxima decisão dependerá de utilidade e limitações, sem liberação automática
de TEST ou produção.
