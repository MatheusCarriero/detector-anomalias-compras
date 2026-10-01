# Invoice — preparação da revisão humana cega

**Estado atual (28/09/2026): TESTE TÉCNICO ENCERRADO; SEM REVISÃO HUMANA VÁLIDA.**
Por decisão do responsável, os dois avaliadores artificiais da simulação não
constituem evidência científica. Suas respostas não serão analisadas, congeladas
como respostas humanas, incorporadas a JSONs/relatórios científicos ou usadas
para calcular concordância, escolher estratégia ou orçamento de investigação.
Os ZIPs preenchidos da simulação devem permanecer fora do repositório e não
foram consultados neste fechamento. A localização desses ZIPs não foi certificada.

A preparação original abaixo foi concluída em 28/09/2026 e permanece como
registro histórico, não como evidência de execução com pessoas reais. Seus
pacotes originais em branco, protocolo, guia, código e registros de coordenação
foram preservados. O estado histórico do manifesto descreve a preparação, não
valida a simulação nem comprova uma revisão humana.

Este relatório é exclusivo da coordenação; não encaminhar aos avaliadores.
Nenhuma label individual foi aberta na preparação. Não há resultados humanos
válidos a reportar. O [contrato acadêmico vigente](invoice_academic_evaluation_protocol.md)
separa o benchmark da utilidade operacional ainda não demonstrada; TEST continua
fechado. Uma revisão real futura não foi cancelada, mas exige etapa própria.

## Protocolo e amostra

[Protocolo aprovado](invoice_blind_review_protocol.md), versão invoice-blind-review-1.0.
Dois avaliadores independentes, mesmas faturas, pseudônimos e ordens próprias.

| Orçamento | Grupo | População elegível | Sorteados |
|---|---|---:|---:|
| 1% | Comuns | 189 | 25 |
| 1% | Exclusivos IF | 111 | 25 |
| 1% | Exclusivos valor | 111 | 25 |
| 1% | Controle não selecionado | 29.589 | 25 |
| 5% | Comuns | 965 | 25 |
| 5% | Exclusivos IF | 535 | 25 |
| 5% | Exclusivos valor | 535 | 25 |
| 5% | Controle não selecionado | 27.965 | 25 |
| 10% | Comuns | 1.832 | 25 |
| 10% | Exclusivos IF | 1.168 | 25 |
| 10% | Exclusivos valor | 1.168 | 25 |
| 10% | Controle não selecionado | 25.832 | 25 |

Total: **300 vínculos sorteados, 295 faturas únicas em cada pacote**.
290 faturas participam de um único estrato sorteado e 5 participam de dois.
Deduplicação apenas na apresentação: a chave preserva todos os vínculos, sem
acrescentar estratos não sorteados. O desenho previa 295 avaliações individuais
por pessoa, 590 no total, não 600 casos independentes. Isso não é contagem de
avaliações humanas realizadas.

A seed de 256 bits está registrada somente na área privada. O sorteio por
HMAC-SHA256 foi fixado previamente, sem labels ou ajuste posterior da amostra.
Todos os fingerprints de top-k foram reconciliados com a comparação anterior.

- Registro anterior ao sorteio/inferência: **2026-09-28T18:49:03.562563+00:00**.
- Pacotes concluídos: **2026-09-28T18:49:05.769797+00:00**.
- SHA-256 do congelamento: `a5ba4bd238c7639298f9749aa6198c3825a7714e1ad7ef7ec37155fd450c7cb8`.
- SHA-256 do manifesto: `24694e35aab8d2649972f7c5a4d16037cc9a41035c947f957674df806e2d7ffe`.

Não sortear novamente ou substituir casos por parecerem difíceis/inadequados.

## Entrega originalmente prevista (histórico)

Na pasta local ignorada pelo Git:
`ml/experiments/invoice_blind_review_v1/`.

Em eventual revisão real autorizada, entregar SOMENTE os pacotes originais:

- `avaliador_01.zip` à primeira pessoa: 24118 bytes;
  SHA-256 `c6f8a08702edf75200cb735a34e00b846a4762195898b38c0d1d3def8ddce90b`.
- `avaliador_02.zip` à segunda pessoa: 24156 bytes;
  SHA-256 `ed125fdb01649a8322b7097f10ed273594ab979ed6ded0f6e0126e8543e6902e`.

Cada ZIP contém exatamente:

1. LEIA_PRIMEIRO.md — guia neutro.
2. FICHAS.md — 295 casos e campos de resposta vazios.
3. DECLARACAO.md — identidade/experiência, exposição prévia, independência e conclusão.

Os arquivos Markdown podem ser abertos/editados em editor de texto. Preservar
o ZIP original; cada participante extrai e preenche somente seus próprios arquivos.
Não misturar as duas devoluções, apesar de terem os mesmos nomes de arquivo.

**Não compartilhar** a pasta coordinator, este relatório, o protocolo da
coordenação, a seed, o código, os resultados anteriores ou o repositório.
Não entregar os dois ZIPs à mesma pessoa. A separação dos arquivos não substitui
controle de acesso: Git ignorado não é criptografia nem isolamento de permissões.

## Conteúdo e qualidade do cegamento

Campos permitidos uniformes: dados tabulares da fatura, pseudônimos de fornecedor/
departamento e quatro descritores contextuais existentes. Nenhum score de anomalia,
posição, estratégia, grupo, orçamento, label, fraud_type, tag, imagem/caminho ou
ID original é mostrado. Os valores monetários preservam os centavos.

As estratégias são mascaradas, mas valores/contexto visíveis podem sugerir a
origem de um caso. Não se garante impossibilidade de inferência. Contexto limitado
e informação insuficiente são resultados possíveis, não motivo de substituição.

A rubrica inclui relevância 0–3 ou insuficiência, motivo concreto, evidência
necessária, facilidade de justificar, esforço estimado e observações. Nenhuma
resposta foi sugerida/preenchida nos pacotes originais gerados. O assistente não
atuou como avaliador humano na preparação; as respostas artificiais posteriores
não modificam esse registro nem validam a revisão.

## Validações realizadas na preparação (histórico)

- 14 testes novos sintéticos; suíte completa: **322 passed in 22.34s**.
- Testes cobrem quotas exatas, estratos, deduplicação, reprodutibilidade,
  independência das labels/ordem de entrada, pseudônimos, respostas vazias,
  projeção sem labels, filtros sem TEST, bloqueio de sobrescrita, registro antes
  do scoring e divergências com a seleção anterior.
- Defeito de apresentação monetária detectado por teste que falhou e depois
  passou: removido arredondamento que poderia suprimir centavos. Corrigido antes
  da geração real, sem mudar dados.
- Revisões independentes do protocolo/guia e do código concluídas; nenhum
  bloqueador restante.
- Ruff dos dois arquivos novos: **All checks passed!**
- Ruff global mantém três avisos preexistentes no Supplier Risk:
  I001/RUF100 em final_evaluation.py e I001 em test_final_evaluation_artifact.py.
  Não foram corrigidos por estarem fora do escopo.
- ZIPs íntegros; nomes dos três membros conferidos; hashes internos e externos
  reconciliados com o manifesto. 295 códigos únicos e respostas inteiramente
  vazias em cada pacote; códigos e ordens diferentes entre avaliadores.
- 12 quotas de 25 e os 300 vínculos conferidos sem repetir sorteio/inferência.
- Hashes de inputs/código/protocolo/guia conferidos; seed não exposta nos pacotes.
  A fase real fez somente uma inferência em VALIDATION, sem fit.
- Nenhuma leitura materializada de is_fraud/fraud_type: leitura seletiva de
  features sem labels e fonte tabular filtrada pelos IDs sorteados. Hashes de
  arquivos completos identificam os bytes; não constituem análise de labels.
  A evidência agregada anterior foi usada apenas para procedência/seleções.
- Arquivos dedicados a TEST não foram abertos. Fontes globais tiveram projeção
  e filtros lógicos; row groups físicos podem conter outros splits.

## Arquivos da preparação (histórico)

Criados: protocolo, guia do avaliador, este relatório,
ml/scripts/preparar_revisao_cega_invoice.py e
tests/invoice/test_invoice_blind_review.py.

Artefatos locais privados: dois ZIPs e coordinator/freeze.json/manifest.json.
O marcador temporário PREPARATION_INCOMPLETE foi removido pelo gerador somente
após conclusão; não restam marcadores de preparação pendente.

Única alteração de arquivo preexistente: .gitignore, acrescentando a exclusão da
pasta privada. As alterações locais anteriores, inclusive os dois notebooks
Supplier, continuam fora do escopo e preservadas. Sem staging ou commit.

## Fluxo humano futuro, não executado nem autorizado por este fechamento

O fluxo abaixo não se aplica às devoluções artificiais e não deve ser executado
com elas. Antes de eventual retomada, confirmar pessoas reais independentes,
contexto suficiente e ausência de exposição que comprometa o cegamento.

1. O responsável identifica duas pessoas e entrega individualmente os ZIPs.
2. Cada pessoa declara exposição prévia e avalia de forma independente.
3. Aguardar AMBAS as devoluções; até lá, não produzir comparações ou abrir labels.
4. Conferir completude sem descegar; preservar as respostas de cada autor.
5. Registrar cópias finais exclusivas e um manifesto de congelamento CONJUNTO,
   com hashes/datas das duas respostas e declarações.
6. Só depois desse registro, executar a análise descritiva já prevista. Qualquer
   análise com labels será uma fase complementar posterior, justificada e separada.

O congelamento original é **do sorteio/protocolo**, não das respostas: as fichas
originais foram geradas em branco. Não há congelamento de respostas humanas
válidas nem comando de análise/descegamento nesta entrega.

Para reprodução técnica independente em uma cópia controlada, o gerador é
`python -m ml.scripts.preparar_revisao_cega_invoice --split val`; nesta pasta ele
recusa nova execução porque a entrega já existe. Uma reprodução idêntica requer
a seed privada e os mesmos hashes, nunca uma seed nova para substituir a amostra.
Não apagar os artefatos existentes para repetir a geração.

O próximo passo atual é o fechamento acadêmico e os controles de acesso descritos
no [contrato vigente](invoice_academic_evaluation_protocol.md), não a importação,
comparação ou abertura de labels das respostas simuladas.

TEST permanece fechado; nenhum treino, tuning, mudança de threshold/algoritmo,
dataset, split, label, modelo, Supplier Risk, notebook ou frontend.
