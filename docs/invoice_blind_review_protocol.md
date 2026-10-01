# Invoice — protocolo de revisão humana cega

**Versão:** invoice-blind-review-1.0. Desenho aprovado pelo responsável antes do
sorteio: dois avaliadores independentes, 25 casos por grupo nos orçamentos de
1%, 5% e 10%. Documento da COORDENAÇÃO: não entregar aos avaliadores.

## Objetivo e limites

Investigar a relevância percebida para auditoria das faturas apresentadas. Não
confirmar fraude, construir nova label automática, escolher modelo, orçamento ou
threshold. Somente VALIDATION; nenhum TEST, fit, tuning ou mudança de dados.
As evidências anteriores e o Supplier Risk permanecem preservados.

## Amostragem fixada antes da geração

Nos três orçamentos originais, K=ceil(N*p/100), formar os quatro conjuntos:
interseção IF/valor, exclusivo IF, exclusivo valor, complemento da união na
VALIDATION. Ranking IF=-score_samples; valor=invoice_amount decrescente; empates
por invoice_id crescente. Reconciliar os fingerprints com a comparação anterior.
TRAIN é lido somente em invoice_id/split para verificar separação/procedência.

Sortear 25 IDs sem reposição em cada um dos 12 estratos: **300 vínculos**.
Não balancear nem filtrar por labels, valores, padrões ou julgamentos. Se algum
estrato tiver menos de 25, interromper em vez de adaptar a quota. A seed secreta
de 256 bits é gerada uma vez, registrada em freeze.json ANTES do sorteio e não
é entregue aos avaliadores. Ordenar por HMAC-SHA256(seed, JSON compacto UTF-8 de
["sample", orçamento, grupo, invoice_id]); selecionar os primeiros 25, com
invoice_id como desempate. Registro reproduzível com a mesma seed, inputs e código.

Deduplicar somente a apresentação: cada fatura única aparece uma vez em cada
pacote. Preservar TODOS os vínculos originalmente sorteados na chave privada.
Não incluir uma resposta em outro estrato apenas porque o caso também pertence
àquele universo. Os estratos/orçamentos sobrepostos não são observações independentes.
25 por estrato é escolha pragmática de piloto, não cálculo de poder estatístico.

## Campos e apresentação fixados

Cada avaliador recebe os mesmos casos, com pseudônimos e ordem próprios,
determinados por namespaces HMAC separados da seed. Pseudônimos de fornecedor e
departamento são estáveis dentro de um pacote, mas diferentes entre avaliadores.
Não mostrar IDs originais, estratégia, grupo, orçamento, posição, scores, labels,
fraud_type, tags, explicações da fonte, caminhos de imagens ou arquivos originais.

Lista fechada e uniforme de conteúdo:

- data da fatura, valor, moeda, tipo, condições de pagamento e hora de submissão;
- fornecedor e departamento pseudonimizados;
- quatro descritores já existentes: razão valor/média do fornecedor, razão
  valor/média do departamento, frequência do fornecedor e frequência conjunta
  fornecedor/departamento na base de referência de preparação (TRAIN).

Não produzir features novas. Os descritores são referências agregadas sobre todo
TRAIN, não histórico disponível no instante da fatura, norma de negócio ou prova
de irregularidade. Não mostrar z-scores, scores de anomalia ou realces de alerta.
Campos nulos são apresentados uniformemente como "Não informado". Não acrescentar
contexto conforme grupo ou estranheza observada. Sem contratos, itens, quantidades,
preços unitários ou comprovação documental, pode faltar base para julgamento.

Os valores continuam visíveis porque são contexto de auditoria. Podem sugerir a
origem de uma seleção; o mascaramento não garante impossibilidade de inferência.
Não atribuir às fichas validação independente dos fatos: parte do contexto é a
mesma informação tabular utilizada pelo estimador.

## Avaliadores e rubrica

Dois avaliadores humanos indicados pelo responsável. Registrar identificação,
experiência pertinente, exposição prévia a rankings/resultados/labels e datas.
Se houver exposição, comunicar antes do início para decidir substituição;
não ocultar comprometimento do cegamento. Nenhum assistente simula respostas.
Trabalhar separadamente, sem discutir casos ou acessar repositório/datasets.

Para CADA caso, responder:

1. Relevância: 0=nenhum motivo observável; 1=indício genérico insuficiente para
   investigação dirigida; 2=motivo específico e verificável; 3=múltiplos indícios
   convergentes. "Informação insuficiente" é resposta separada, não zero.
2. Motivo concreto: citar campo/fato e a pergunta que justificaria verificação.
3. Evidência adicional necessária: qual documento/contexto resolveria a dúvida.
4. Facilidade de justificar: fácil/moderada/difícil/informação insuficiente.
5. Esforço estimado: baixo/médio/alto/impossível estimar. Considerar, respectivamente,
   conferência simples; cruzamento de registros; múltiplos contatos/fontes.
   Não é tempo real medido. Registrar a hipótese usada na estimativa.
6. Observações qualitativas; não emitir classificação de fraude.

Um valor elevado ou horário incomum isolado não obriga relevância alta. É
necessário explicar a questão verificável; não inventar políticas ou limites.

## Separação dos artefatos e congelamento das respostas

Saída local ignorada pelo Git: ml/experiments/invoice_blind_review_v1/.
Somente avaliador_01.zip e avaliador_02.zip são entregáveis, um para cada pessoa.
Não compartilhar a pasta inteira, chave, seed, protocolo da coordenação, código,
relatórios anteriores ou pacotes cruzados. Separação por arquivos não é ACL nem
criptografia: a coordenação é responsável pelo acesso efetivo.

freeze.json registra seed, código, protocolo, guia, hashes dos inputs e instante
anterior ao sorteio. manifest.json registra os 300 vínculos, pseudônimos, hashes
dos pacotes e inventário. Criação exclusiva; marcador de preparação incompleta
impede confundir falha com entrega pronta. Não sobrescrever nem sortear de novo
porque os casos parecem inadequados. A fonte de respostas permanece em branco.

Após devolução dos DOIS avaliadores, uma etapa futura deverá:

1. Confirmar declaração de conclusão, cegamento e independência de ambos.
2. Conferir somente completude/esquema: cada código esperado exatamente uma vez,
   categorias válidas e campos obrigatórios preenchidos. Insuficiência justificada
   é válida; não substituir respostas nem excluir casos para melhorar resultados.
3. Resolver somente omissões/formatação com o próprio autor, ainda cego. Não
   comunicar resultados agregados ou respostas do outro avaliador.
4. Guardar cópias exclusivas das duas respostas finais e declarações, com SHA-256,
   datas e ligação aos hashes dos pacotes originais. Registrar um manifesto único
   de congelamento conjunto. Não permitir edições silenciosas posteriores.
5. SOMENTE depois desse congelamento conjunto, associar grupos e analisar respostas.
6. Eventual abertura de labels exige justificativa e registro próprios, depois
   da análise cega; relatório complementar separado. Não substituir o julgamento
   por is_fraud nem modificar os dados originais.

Nesta entrega não há comando de análise/descegamento ou congelamento fictício.
Sem as duas respostas concluídas e congeladas, o estado é AGUARDANDO AVALIADORES.

## Análise futura pré-especificada — não executar agora

Apresentar, por orçamento/grupo/avaliador, N sorteado, N respondido, N avaliável,
insuficiências e distribuição 0/1/2/3. Descrever proporção 2 ou 3 entre avaliáveis
sempre com cobertura; não esconder insuficiências nem tratá-las como zero.
Apresentar distribuições de facilidade/esforço, justificativas recorrentes e
concordâncias/divergências entre pessoas, sem substituir respostas por consenso.
Não agregar estratos como amostra independente nem estimar prevalência a partir
das quotas iguais. Sem testes de significância ou vencedores pós-hoc.

Separar observação tabular, julgamento humano e interpretação/limitação.
Relevância percebida não comprova fraude, retorno financeiro, custo efetivo,
generalização, causalidade ou prontidão de produção.
