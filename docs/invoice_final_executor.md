# Invoice — contrato técnico de avaliação pré-TEST

**Estado em 01–02/10/2026:** executor sintético, adaptador, gate e rota de inputs
implementados. O gate continua bloqueado sem autorização externa. A ligação real
entre inputs autorizados, scoring e publicação ainda não está implementada;
portanto não há executor real ponta a ponta pronto para congelamento. As seções
datadas abaixo preservam verificações anteriores, não resultados de QA desta
auditoria estática. Pytest, Ruff, notebooks e avaliações não foram executados aqui.

**Escopo técnico, 29/09/2026. Não é relatório de desempenho científico.**
Implementação de [invoice_final_evaluation.py](../ml/scripts/invoice_final_evaluation.py)
para testar o contrato do [protocolo acadêmico](invoice_academic_evaluation_protocol.md).
Nenhum resultado da simulação de revisão cega é entrada deste executor.

## Fronteira desta entrega

- Não existe CLI ou avaliação de dados reais. A API de avaliação aceita somente
  `synthetic_only`, com `synthetic_holdout`. O gate pré-acesso descrito adiante
  verifica documentos de autorização para a futura partição `test`, mas não
  permite lê-la nem faz inferência.
- Fixtures e saídas devem estar fora do checkout; caminhos resolvidos que escapem
  da pasta da fixture ou entrem no projeto são rejeitados. Não alterar essas
  guardas para apontar a API atual para dados reais.
- Os testes criam um Isolation Forest próprio, sobre números artificiais, com
  os nove parâmetros previstos no protocolo e as 19 features. O executor nunca
  chama `fit`, `predict` ou `decision_function` e não muda offset/parâmetros.
- O offset congelado é o do modelo **da fixture**, não uma alegação de identidade
  com o modelo legado real. Nenhum artefato real é carregado para construir testes.
- A origem sintética é garantida pelo desenho das fixtures e isolamento dos
  testes, não pelo texto de um marcador. `joblib` exige arquivo local confiável;
  hashes identificam bytes, não tornam desserialização arbitrária segura.

## Fluxo e API

1. `configuration_contract(offset)`: contrato estrito de algoritmo, nove
   parâmetros, lista/ordem de 19 features, offset, versões de schema/protocolo,
   orçamentos fixos 1%/5%/10%, regra seleção@K e ausência de autorização TEST.
2. `freeze_configuration(fixture_root, run_dir, configuration)`: cria diretório
   exclusivo e `freeze.json`; vincula o diretório absoluto da execução e registra
   código/protocolo, versões e hashes de
   modelo/metadata/IDs de desenvolvimento. **Não lê nem hasheia o holdout**, suas
   labels, valores ou splits nesta preparação.
3. `load_frozen_configuration(path, expected_sha256)`: confere hash fornecido
   externamente, schema e contrato sem coerções de tipos. JSON duplicado ou
   não finito é inválido; comparação de hash ignora caixa, sem regravar fontes.
4. `run_synthetic_evaluation(...)`: verifica código/ambiente e registra
   `execution_started.json` por criação exclusiva **antes** de ler/hashar
   arquivos do holdout. Desserializa exatamente os bytes identificados por hash,
   valida as fontes por ID e chama a avaliação pura.
5. `evaluate_frame(...)`: somente dados/modelo já fornecidos; uma chamada a
   `score_samples`, sem treinamento. Estado ajustado e offset são conferidos
   antes/depois. Reutiliza `compare_rankings`, não os carregadores/`run` históricos.
6. Publicação interna: verifica novamente inputs, código e freeze; produz
   `results.pending/evidence.json` e manifesto, verifica o conjunto e renomeia
   para `results`. Só `results` validado representa publicação concluída.
7. `verify_bundle(...)`: exige hashes externos esperados de manifesto e freeze,
   verifica conjunto exato de arquivos, conteúdo e natureza sintética.

Registros existentes bloqueiam nova preparação ou execução. Copiar um freeze
para outra pasta não cria uma nova tentativa: o caminho recebido deve coincidir
com o destino congelado, antes de acessar o holdout. Falha após o claim
preserva início, `failure.json` e eventual diretório parcial; não há retry ou
limpeza automática. O bloqueio é por diretório de execução/congelamento e não
constitui registro global de todos os caminhos possíveis ou controle de acesso
contra alguém que deliberadamente remova arquivos.

## Contratos de entrada das fixtures

Os sete arquivos são criados em `tmp_path` pelos testes; não são cópias de datasets:

| Arquivo | Contrato |
|---|---|
| holdout.parquet | `invoice_id`, `split`, `is_fraud`, `fraud_type`, depois as 19 features na ordem original |
| development_ids.parquet | IDs únicos de `train` e `val`, ambos presentes |
| splits.parquet | Cobertura exata dos IDs de desenvolvimento e holdout sintético, sem sobreposição |
| labels.parquet | IDs/labels/tipos do holdout, alinhados por chave e não por posição |
| amounts.parquet | IDs/valor original iguais ao processado; uma moeda não nula |
| model.joblib | IsolationForest sintético ajustado; 200 árvores, ordem de features, parâmetros e offset conferidos |
| model_metadata.json | Algoritmo, contagem/lista de features, nove parâmetros e offset da fixture |

Nenhuma coluna inesperada é descartada silenciosamente. Features devem ser reais,
numéricas, finitas e sem nulos; labels, inteiras binárias. Tipos ausentes são
preservados como grupo `__missing__`; NONE e divergências entre label/tipo não
são corrigidos. A frequência negativa de fornecedor é rejeitada como no
carregador histórico. Valores monetários são ordenados com seu **sinal original**,
sem impor um filtro novo de positividade ou usar valor absoluto.

## Métricas sem mudança metodológica

São exercitados os cálculos já definidos de Precision@K, captura, lift,
composição/concentração, interseção/exclusivos, Jaccard, ganho bruto/sacrificado
e líquido, sempre nos três orçamentos. Nenhum orçamento é selecionado.

A matriz adicional pedida nesta implementação tem linhas de referência `[0, 1]`
e colunas `[não selecionada, selecionada]`, na coorte inteira, para cada top-K.
**Não é uma matriz de classificação automática de fraude pelo threshold legado.**
Por `fraud_type`, usa-se a mesma máscara de seleção global; não se cria uma fila
separada dentro de cada tipo. Grupos sem seleção continuam visíveis e métricas
sem denominador recebem `null`. O score na fronteira do ranking é descritivo,
não um novo limiar operacional.

## Artefatos e reprodutibilidade técnica

Os artefatos do executor sintético desta seção ficam em diretórios temporários e declaram
`synthetic=true`, `scientific_evidence=false`, `test_used=false` e
`model_fits_in_executor=0`. Não publicar suas métricas em relatórios científicos
ou `ml/experiments/`. O estado científico anterior permanece independente.

O JSON usa representação canônica, com hashes dos bytes de entrada e código,
versões, configuração e fingerprint dos IDs. Resultados numéricos e seleção
devem ser determinísticos para o mesmo modelo/inputs. Timestamp, caminho da
fixture e hash do freeze identificam cada execução; não se promete igualdade
byte a byte entre execuções em diretórios/instantes diferentes.

Para conferir o código, usando o ambiente isolado funcional do projeto:

```powershell
python -m pytest -q tests/invoice/test_invoice_final_evaluation.py -p no:cacheprovider
python -m ruff check ml/scripts/invoice_final_evaluation.py tests/invoice/test_invoice_final_evaluation.py
git diff --check
```

O Python desta tarefa é o ambiente temporário já existente, não uma reinstalação
ou reparo da `.venv` principal. Os comandos acima não autorizam execução real.

## Verificação técnica da etapa sintética anterior

- Execução daquela etapa: **392 passed, 1 skipped in 41.79s**, incluindo os
  testes deste executor e as regressões existentes. Nenhuma métrica dos modelos
  sintéticos foi incorporada à evidência científica.
- A execução instrumentou leituras no processo Python e os carregadores de
  pandas/joblib para recusar caminhos de dados, modelos e experimentos reais:
  **zero tentativas detectadas**. Não é um sandbox de sistema operacional nem
  uma prova universal sobre processos externos.
- Ruff dos dois arquivos Python novos: **All checks passed!**
- Revisão independente: nenhum achado bloqueante após vincular congelamento e
  diretório. O teste de cópia do freeze falhou antes da correção e passou depois;
  copiar o JSON não permite uma segunda tentativa.
- O teste ignorado exige symlink, não autorizado pelo Windows neste ambiente.
  Um teste de disputa simultânea entre processos permanece como melhoria de
  robustez; criação exclusiva, repetição sequencial, cópia de freeze e publicação
  interrompida já possuem cobertura.

Na conferência daquela etapa, os 42 arquivos protegidos e os 91 arquivos preexistentes
de código/documentação/evidências não apresentaram data de modificação posterior
ao início desta implementação. Foram consultados somente metadados dos dados
protegidos, sem abrir TEST. Os valores individuais do snapshot inicial não
persistiram após a retomada: **não se afirma comparação criptográfica completa
antes/depois**. Essa limitação não foi contornada lendo os dados reais.

## Limitações e passagem para uma avaliação real

O executor sintético acima é um contrato testado com fixtures, **não o adaptador
de dados reais**. A adaptação técnica de desenvolvimento está registrada abaixo.
O adaptador e a rota autorizada de validação de inputs já estão implementados.
Para uma avaliação real final ainda será necessário ligar essa rota ao cálculo
e publicação, verificar o vínculo aos JSONs anteriores e revisar o fluxo completo
com fixtures sintéticas. Somente depois: congelamento exclusivo e autorização
humana independente. Reconciliação de linhas não certificará a procedência do fit.
Não remover uma guarda por flag nem fazer leitura real como ensaio técnico.

As limitações da label, contexto, temporalidade e procedência do fit legado
continuam descritas no protocolo acadêmico. Testes de software não as resolvem
nem demonstram utilidade humana. TEST permanece fechado.

## Adaptador TRAIN/VALIDATION — incremento técnico

**Escopo de 29/09/2026:** adaptar o carregamento, não executar avaliação.
O módulo separado `ml/scripts/invoice_data_adapter.py` não relaxa o modo
sintético do executor acima nem modifica os avaliadores históricos.

Plano técnico delimitado (sem novo desenho metodológico):

- [x] Registrar Git e snapshot persistido antes das alterações.
- [x] Implementar/testar leitura de arquivos separados e contrato do modelo.
- [x] Implementar/testar reconciliação seletiva das fontes, somente com fixtures.
- [x] Inspecionar somente os arquivos reais separados, sem inferência.
- [x] Executar testes, Ruff, revisão independente e comparação de integridade.

### Entradas e proteção de TEST

| Entrada | Uso permitido pelo adaptador |
|---|---|
| `data/processed/train_features.parquet` | Schema completo, 19 features ordenadas, IDs e split TRAIN |
| `data/processed/val_features.parquet` | Mesmo contrato para VALIDATION; IDs disjuntos de TRAIN |
| `ml/models/isolation_forest.joblib` | Somente desserialização local confiável após SHA-256 esperado; parâmetros, features e offset, sem scoring/fit |
| `ml/models/model_metadata.json` | Formato legado real, com parâmetros no nível superior |
| `data/raw/splits.parquet` | Bloqueado no carregador real; contrato de reconciliação exercitado apenas em fixtures externas |
| `data/raw/labels.parquet` | Bloqueado no carregador real; não ler nem filtrar o raw compartilhado |
| `data/raw/invoices.parquet` | Bloqueado no carregador real; moeda/origem permanecem sem nova reconciliação |

A partição deve ser exatamente `train` ou `val`, antes de qualquer I/O.
Não há opção TEST, glob de descoberta, caminho de entrada arbitrário por arquivo,
fit, inferência, métricas ou publicação de resultados científicos.

`inspect_development_files(...)` confere somente os quatro arquivos separados;
não consulta raw e declara `source_reconciled=false`.
`load_development_data(...)` usa a mesma via segura e também mantém
`source_reconciled=false`. Ambas retornam dados/modelo e registro técnico em
memória; não escrevem datasets ou artefatos.

A antiga via completa passou a se chamar `load_synthetic_development_data(...)`.
Ela rejeita o checkout e seus descendentes resolvidos antes de procurar arquivos,
consultar stat das fontes ou desserializar entradas. Só aceita fixtures criadas
pelos testes em diretórios externos. Seu `source_reconciled=true` se refere
exclusivamente à fixture, marcada `synthetic=true`, não aos dados reais. Não há
flag para habilitar a reconciliação real. A guarda de caminhos não certifica a
origem de cópias disfarçadas: nunca copiar dados reais para satisfazer essa API.

**Limite físico:** filtros Parquet limitam linhas retornadas, mas não garantem
isolamento físico de row groups compartilhados com TEST. Por isso a reconciliação
com raw nesta entrega foi exercitada apenas em fixtures sintéticas. A inspeção
real usou somente a primeira API. Não se apresenta essa inspeção parcial como
reconciliação real completa ou autorização de TEST.

### Snapshot e rastreabilidade desta implementação

Snapshot inicial `before.json`, persistido em diretório temporário externo ao
repositório durante aquela etapa; não é dependência portátil ou fonte versionada.
Contém 98 SHA-256 (código/documentação/evidências preexistentes, TRAIN/VALIDATION
separados e modelo Invoice) e metadados de 42 arquivos protegidos.
TEST, raw compartilhados e dados Supplier não foram lidos para hashing: sua
proteção neste snapshot é por tamanho/data, não comprovação criptográfica.
O arquivo de documentação presente é a única alteração preexistente planejada;
os demais arquivos anteriores devem manter hashes/metadados.

O offset esperado deve vir da evidência VALIDATION identificada, nunca de uma
nova estimação: `invoice_validation_v1.json`, SHA-256
`1218ed395095c69dd8d3439e27b7e1416dfeba68b8f1d9d83328e2c2f27e12f9`.
Os hashes esperados dos quatro arquivos também são fornecidos explicitamente,
não aceitos a partir de valores autodeclarados no modelo carregado.

### Uso técnico e fronteira de execução

As funções exigem os argumentos nomeados `split`, `expected_hashes` e
`expected_offset`. Retornam `AdaptedInvoice(frame, model, technical_record)`;
a matriz para eventual consumo futuro é `frame[FEATURES]`, nunca labels/IDs.
Não chamar scoring, treino ou publicação a partir desta inspeção.

`expected_hashes` deve conter exatamente os quatro caminhos separados da tabela
acima e seus SHA-256 confiáveis; hashes em maiúsculas também são aceitos.
O offset esperado registrado anteriormente é `-0.5211491197816622`.
A identidade esperada do modelo e do metadata é a do protocolo acadêmico,
não uma nova estimação. Os nove parâmetros são os já registrados nesse protocolo.

A via completa, exclusivamente sintética, valida a partição oficial da fixture antes de usar IDs para consultar labels
e valores. Seus fingerprints de tabelas representam **somente as linhas lógicas
autorizadas**, ordenadas por ID, incluindo schema/dtypes; não são hashes do arquivo
raw completo. Fontes sem cobertura exata, duplicadas, incompatíveis ou alteradas
durante a leitura interrompem o processamento, sem reparação ou exclusão de linhas.

Não existe CLI real ou chamada automática na importação. A abertura final de TEST
continua sendo uma etapa diferente; não se deve contornar esta allowlist trocando
um nome de arquivo, copiando dados de TEST ou alterando flags.

Comandos de verificação, no ambiente isolado funcional já existente:

```powershell
python -m pytest -q tests/invoice/test_invoice_data_adapter.py tests/invoice/test_invoice_final_evaluation.py tests/invoice/test_invoice_adapter_integration.py -p no:cacheprovider
python -m ruff check ml/scripts/invoice_data_adapter.py ml/scripts/invoice_final_evaluation.py tests/invoice/test_invoice_data_adapter.py tests/invoice/test_invoice_final_evaluation.py tests/invoice/test_invoice_adapter_integration.py
git diff --check
```

### Verificações técnicas do incremento anterior do adaptador

- Testes específicos do adaptador: **118 passed, 1 skipped**. Regressão completa
  posterior, com guardas de leitura dos diretórios reais: **510 passed,
  2 skipped in 57.16s**, com zero tentativas detectadas de leitura de dados/modelos
  reais. Os dois skips dependem de privilégio Windows para criar symlinks.
- Ruff dos dois arquivos novos: **All checks passed!**. Whitespace conferido
  no diff e também nos arquivos novos ainda não rastreados pelo Git.
- Revisão independente não encontrou falha de produção no escopo. Identificou
  wrappers de teste incompatíveis com `BytesIO`, que poderiam provocar falsos
  positivos; corrigidos antes da execução verde. Os testes também conferem que
  o estado do modelo carregado não muda e que os arquivos da fixture não mudam.
- Inspeção real: **210.000 linhas TRAIN e 30.000 VALIDATION**, com 19 features,
  schema/ordem válidos, valores finitos, ausência de nulos nas features, IDs
  únicos e disjuntos. Os nove parâmetros, as 200 árvores e o offset do modelo
  corresponderam à referência anterior; não houve chamada a fit ou scoring.
- Leituras reais: exclusivamente os quatro arquivos separados da tabela e o
  JSON de referência VALIDATION já existente. Guardas bloqueariam qualquer
  leitura de TEST, raw compartilhado ou escrita nos arquivos protegidos; zero
  tentativas indevidas detectadas. Nenhuma inspeção de labels raw foi feita.
- `source_reconciled=false` no registro real é intencional: essa inspeção não
  afirma reconciliação com raw. Caminhos completos e versões utilizadas estão
  em `inspection.json`, ao lado do snapshot inicial. Não há métricas de modelos
  ou interpretação científica nesse registro.

Integridade final: **97 dos 98 hashes iniciais permaneceram idênticos**; o único
arquivo preexistente alterado foi este documento técnico, conforme planejado.
Os 42 registros protegidos de tamanho/data permaneceram iguais. O snapshot final
`after.json`, no mesmo diretório externo, registra a comparação; a proteção
criptográfica não é estendida aos arquivos classificados como somente stat.
HEAD permaneceu `b624204baeaaa910719985eb10d14cecd440346d`, sem staging/commit.
Naquele incremento, os únicos arquivos novos foram o adaptador e seu arquivo de testes.
Os executores anteriores, resultados científicos, modelos/datasets e alterações
preexistentes dos notebooks Supplier não foram modificados.

### Fronteira física confirmada e contrato de integração — 30/09/2026

Os rodapés estruturais dos três raw relevantes registram **um único row group
de 300.000 linhas por arquivo**. Selecionar linhas com filtros não separa os
chunks de coluna que abrangem a população inteira. Não há índice independente
de partições físicas que autorize a leitura seletiva sem alcançar TEST.

A inspeção já concluída leu exclusivamente o trailer e o rodapé, com offsets
exatos e I/O sem buffer de pré-leitura da aplicação. O parser recebeu esses
bytes em memória: não leu páginas de dados nem consultou estatísticas de valores.
Nenhum arquivo específico de TEST foi aberto. O registro temporário externo
`footer_structure.json` preservou schemas, tamanhos, offsets, row groups e hashes **dos rodapés**, não
hashes completos dos raw nem evidência científica.

Não foi encontrada fonte independente segura para toda a coorte. O manifest raw
contém contagens agregadas, não um índice de IDs por partição. TRAIN/VALIDATION
processados são separados, mas suas labels/IDs são cópias derivadas: compará-los
consigo mesmos não certifica a origem. Evidências agregadas e amostras da revisão
cega não substituem essa fonte; nenhuma resposta simulada foi utilizada.
**`source_reconciled=false` permanece como limitação de procedência.**

A ligação nesta etapa é uma verificação de contratos, não habilitação de uma
avaliação real. O adaptador e o executor compartilham as 19 features ordenadas,
os nove parâmetros e a validação do offset esperado. A integração sintética usa:

1. TRAIN e VALIDATION artificiais em Parquets separados, sem raw compartilhado.
2. IDs/splits originais desses resultados como `development_ids` do executor,
   sem renomear TRAIN/VALIDATION para holdout.
3. O modelo sintético carregado pelo adaptador, sem refit no percurso.
4. Um terceiro conjunto independente `synthetic_holdout`, em arquivo separado,
   com IDs disjuntos; somente ele pode ser avaliado pelo executor sintético.
5. Metadata legado e metadata do executor gerados na própria fixture a partir
   do mesmo modelo; não existe conversor automático de produção.

Passar o frame TRAIN/VALIDATION diretamente para `evaluate_frame` deve falhar
antes do scoring, assim como fornecer configuração TEST ou incompatível. Essa
incompatibilidade de papel é deliberada: provar o contrato de modelo/IDs não
autoriza inferência em dados reais. Testes de integração exercitam também hashes,
congelamento, reconciliação sintética, publicação e bloqueio de reexecução.

O snapshot `before.json` no mesmo diretório externo precede estas mudanças:
101 hashes de arquivos autorizados e 42 registros somente de tamanho/data.
TEST e raw compartilhados não foram hashados integralmente. A comparação final
deve preservar os protegidos sem usar seu conteúdo como atalho de verificação.

### Validação técnica da fronteira e integração

- Regressão Invoice, sem repetir a suíte Supplier: **329 passed, 6 skipped in
  65.58s**. Os 11 casos de integração também passaram isoladamente. Os seis skips
  dependem de privilégio Windows para symlinks; a recusa de alias resolvido tem
  cobertura adicional sem esse privilégio.
- A regressão instrumentou aberturas Python e carregadores pandas/joblib para
  bloquear dados, modelos e evidências reais: **zero tentativas detectadas**.
  Isso não é uma garantia universal de sandbox do sistema operacional.
- Ruff dos cinco arquivos Python envolvidos: **All checks passed!**.
  `git diff --check` passou; whitespace dos arquivos ainda não rastreados também
  foi conferido. Avisos de conversão LF/CRLF em alterações preexistentes não
  motivaram regravação desses arquivos.
- Revisão independente final: nenhum bloqueador. O carregador real permanece
  sem acesso raw; o executor continua exclusivamente sintético. A recusa de uma
  segunda execução é verificada antes de scoring, preservando a evidência.
- A invariância de estado é conferida por instância após desserialização; árvores,
  features e offset são comparados entre instâncias. Não se presume que um hash
  de objeto `joblib` seja idêntico através de serializações.

Arquivos desta etapa: alterados `invoice_data_adapter.py`, seu teste e este
documento; criado `tests/invoice/test_invoice_adapter_integration.py`.
`invoice_final_evaluation.py` foi revisado, mas não precisou ser alterado.
Nenhuma avaliação real, novo treinamento real, notebook ou commit foi executado.

### Gate de autorização pré-acesso — contrato técnico

O gate está no próprio `invoice_final_evaluation.py`; não foi adicionado um
segundo executor, servidor de autorização ou emissor automático de aprovações.
A API sintética existente continua incompatível com configuração real.

Plano desta extensão delimitada:

- Registrar snapshot externo antes das alterações e preservar o checkout.
- Fixar procedência não certificada e configuração admissível no contrato real.
- Testar recusas antes de implementar; adicionar somente validação e claim.
- Exercitar autorização e repetição com documentos artificiais, sem datasets.
- Executar qualidade, revisão independente e conferência de integridade.

`real_configuration_contract()` descreve o único contrato admissível; não cria
congelamento nem autorização. Fixa modelo/metadata pelos hashes já documentados,
offset legado exato, 19 features ordenadas, nove parâmetros, preparação existente,
orçamentos 1%/5%/10%, desempate por ID, valor com sinal e os limites de procedência.

`claim_real_evaluation_authorization(freeze_path, authorization_path=None,
expected_freeze_sha256=None, expected_authorization_sha256=None)` exige hashes
como argumentos nomeados e retorna apenas o caminho de `authorization_claim.json`.
Argumentos ausentes mantêm o gate bloqueado antes de I/O. A API não recebe frame,
modelo, callback, loader ou caminho individual de TEST para abrir.

| Documento | Contrato |
|---|---|
| `freeze.json` | Schema `invoice-real-preregistration/1.1`; data com fuso, destino e raiz absolutos canônicos, configuração completa, versões, hashes do código/protocolo, adaptador e rota, quatro hashes pré-acesso, escopo de acesso físico e allowlist dos oito caminhos descritivos |
| `authorization.json` | Schema `invoice-real-authorization/1.1`; `approve_once`, responsável/referência, emissão e expiração com fuso, SHA do freeze, SHA da configuração canônica, mesmo destino, split `test`, escopo físico, finalidade acadêmica e reconhecimento das limitações |
| `authorization_claim.json` | Recibo exclusivo com hashes externos, configuração, autorização, destino e procedência; não é evidência de execução ou resultado |

Os quatro hashes pré-acesso descrevem TRAIN, VALIDATION, modelo e metadata; a
identidade modelo/metadata deve coincidir com o contrato legado. Nenhum hash de
TEST/raw é admitido nessa lista. Os caminhos incluem esses quatro arquivos,
`data/processed/test_features.parquet` e `data/raw/{splits,labels,invoices}.parquet`,
**apenas como strings**: o gate não resolve,
consulta stat, lê ou hasheia esses inputs. Registra `input_hashes_verified=false`,
pois validar a sintaxe e o vínculo dos pins não verifica os bytes atuais dos dados.
Somente documentos JSON e a allowlist fixa de código/protocolo são lidos.

Os registros do gate ficam em destino externo ao checkout, como os registros
sintéticos existentes. O freeze deve ser `run_dir/freeze.json`; outro destino ou
cópia não altera o destino vinculado. O recibo é criado com modo exclusivo `xb`.
Recibo, início, falha ou resultados preexistentes bloqueiam a tentativa, inclusive
um recibo parcial. Não existe retry/limpeza automática; a proteção depende de
preservar os registros locais, não é um controle global contra exclusão deliberada.

JSON duplicado, não finito, com campos desconhecidos, configuração divergente,
split/finalidade incompatíveis e hashes inválidos são rejeitados. Comparações de
hash ignoram maiúsculas/minúsculas sem regravar os documentos. Código/ambiente e
hashes dos dois documentos são conferidos antes de criar o recibo. Os documentos
ficam vinculados à cronologia `congelamento <= aprovação <= presente < expiração`,
com fuso explícito; datas futuras ou autorização expirada não são aceitas.

O responsável deverá fornecer a referência de aprovação e o hash esperado da
autorização por canal independente em etapa futura. SHA-256 verifica os bytes,
**não autentica a identidade humana**. Derivar automaticamente o pin do arquivo
submetido seria uma autoautorização circular; isso só ocorre nas fixtures
artificiais para testar o contrato, nunca como procedimento de aprovação real.

O recibo mantém `source_reconciled=false`,
`legacy_training_provenance_certified=false` e `raw_independence_certified=false`.
Aceitar as limitações não as remove. `test_used=false`,
`data_access_performed=false`, `real_execution_available=false`, `model_fits=0`
e `score_calls=0` tornam explícito que nenhum acesso/avaliação foi executado.
Nenhuma autorização ou congelamento real foi emitido nesta implementação.

Verificação específica, somente com contratos sintéticos:

```powershell
python -m pytest -q tests/invoice/test_invoice_authorization.py -p no:cacheprovider
python -m ruff check ml/scripts/invoice_final_evaluation.py tests/invoice/test_invoice_authorization.py
git diff --check
```

Validação histórica do gate 1.0, anterior à rota de inputs:

- **64 testes do gate aprovados**, incluindo ausência de autorização/pins antes
  de I/O, aprovação de contrato artificial, configuração/split/hash divergentes,
  Unicode/JSON inválidos, cópia de freeze, adulteração durante a validação,
  marcadores parciais, repetição e datas futuras. As fixtures usam identificadores
  explícitos `SYNTHETIC_FIXTURE_NOT_AN_APPROVER` e
  `SYNTHETIC_CONTRACT_NOT_HUMAN_APPROVAL`, não nomes ou aprovações humanas.
- Regressão completa instrumentada: **618 passed, 6 skipped in 68.98s**;
  **zero tentativas detectadas de acesso a dados/modelos/evidências reais**.
  Os skips exigem privilégio Windows para symlinks. As guardas do processo
  Python não são apresentadas como sandbox universal do sistema operacional.
- Ruff do executor e teste novo: **All checks passed!**. `ruff check .` encontrou
  três avisos preexistentes fora do escopo: I001/RUF100 em
  `ml/supplier_risk/scripts/final_evaluation.py` e I001 em
  `tests/supplier_risk/test_final_evaluation_artifact.py`. Os hashes desses dois
  arquivos permaneceram iguais ao snapshot inicial; não foram modificados.
- `git diff --check` e whitespace dos arquivos novos: aprovados.
- Revisão independente final: nenhum bloqueador. Confirmadas cronologia,
  comparação de hashes sem sensibilidade a caixa e separação entre procedência
  independente e consistência futura por ID.

O snapshot desta extensão foi mantido em diretório temporário fora do repositório,
sem garantia de retenção; seu caminho pessoal não é requisito de reprodução.
O baseline contém 102 hashes autorizados e 42 registros somente de tamanho/data;
TEST/raw compartilhado não são lidos para hashing. O registro `after.json`
preserva a conferência final e as limitações da verificação. Nenhum documento
real de aprovação ou congelamento foi criado nessa pasta ou no checkout.

### Rota técnica de consumo do recibo — sem avaliação automática

`ml/scripts/invoice_real_inputs.py` contém a API
`validate_authorized_inputs(freeze_path, authorization_path, receipt_path, *,
expected_freeze_sha256, expected_authorization_sha256, expected_receipt_sha256,
start_input_validation=False, split="test")`. Não há CLI, execução no import,
emissor de aprovação, callback de scoring ou uso de dados reais nos testes.

O contrato 1.1 substitui os descritores artificiais 1.0 para essa rota. Exige
`expires_at` e `access_scope=processed_test_and_physical_shared_raw_for_consistency_only`
nos documentos. Não há migração automática de uma autorização antiga. Nenhuma
autorização real foi criada. Essa mudança não altera as 19 features, o modelo,
o offset, os orçamentos ou qualquer decisão metodológica.

Sequência técnica:

1. Sem início explícito, documentos/pins completos ou split autorizado, rejeitar
   antes de qualquer I/O. Os pins devem vir do fluxo externo confiável; SHA-256
   não autentica a pessoa que aprovou.
2. Revalidar freeze/autorização, hashes de código e ambiente, expiração e recibo
   estrito. Reconstruir seu conteúdo esperado a partir dos documentos vinculados,
   incluindo configuração, cronologia, destino e limites de procedência.
3. Recusar tentativas/resultados existentes e criar `execution_started.json` em
   modo exclusivo antes de qualquer input. O marcador significa início da
   validação/leitura, **não** que houve scoring. Uma falha parcial também consome
   a tentativa; não apagar marcadores para repetir.
4. Verificar os quatro hashes pré-acesso antes de desserializar o modelo, validar
   TRAIN/VALIDATION, metadata, parâmetros, offset e ordem das 19 features.
   Revalidar a autorização na fronteira de acesso a TEST/raw.
5. Somente dentro da futura chamada autorizada, ler os bytes dos caminhos exatos
   de TEST e raw. Verificar schema, IDs únicos e disjuntos, pertencimento completo
   aos splits oficiais, labels por ID, igualdade dos valores com sinal e uma única
   moeda não nula. Sem reparos, exclusões silenciosas ou transformações novas.
6. Registrar hashes dos bytes efetivamente lidos e conferir integridade. Sucesso
   grava `inputs_validated.json` exclusivo e retorna frame/modelo validados em
   memória; falha registra `failure.json` e mantém o marcador de início.

`source_rows_consistent=true` significa somente igualdade atual de linhas. Os
três campos de procedência permanecem falsos, inclusive `source_reconciled=false`.
Os raw compartilhados não certificam ausência de TEST no treinamento legado.
Quando realmente chamada com autorização, a rota declara `test_used=true` e
`data_access_performed=true`, mesmo sem métricas; não mascara a abertura como
pré-acesso. Nas fixtures, esses campos descrevem apenas a partição artificial.
`final_evaluation=false`, `scientific_evidence=false`, `evaluation_started=false`,
`model_fits=0` e `score_calls=0` distinguem a validação de uma avaliação científica.

A etapa de autorização termina no recibo; a validação exige outra chamada; a
avaliação/publicação não é chamada por nenhuma delas. A API sintética de métricas
continua recusando configuração real. Não existe autoexecução depois de um recibo
ou retorno válido. O controle local impede repetição acidental, não exclusão
deliberada dos registros nem substitui o canal independente de autorização humana.

Antes de qualquer uso real, deve ser concluída a ligação real até scoring e
publicação, com revisão sintética do fluxo completo. O responsável deverá então
registrar o congelamento exclusivo e fornecer autorização verificável. Não fazer um ensaio
real da rota: ler TEST para validar inputs já é uma abertura que consome a
tentativa. Não houve ajuste de threshold, tuning, retreinamento ou uso de respostas
simuladas de revisão cega. Os resultados das fixtures não são evidência científica.

### Verificação da rota — 01/10/2026

- Gate 1.1: **90 testes aprovados**. Rota: **82 testes aprovados**. Execução
  conjunta instrumentada: **172 passed in 28.68s**, sem acesso a inputs reais.
- Regressão completa instrumentada: **726 passed, 6 skipped in 91.56s**. Os seis
  skips são testes de symlink sem privilégio Windows. Zero tentativas detectadas
  de abrir dados/modelos/evidências reais; guardas Python não são sandbox universal.
- A revisão independente identificou expiração entre validação demorada e uma
  releitura. Os testes reproduziram as duas fronteiras (após resolução de caminho
  e após consistência de linhas); a correção exige autorização vigente antes de
  cada leitura/releitura protegida. Revisão final: nenhum bloqueador restante.
- Ruff dos arquivos envolvidos e `git diff --check`: aprovados. Whitespace dos
  arquivos ainda não rastreados também conferido separadamente.
- O runtime temporário anterior perdeu pacotes; a verificação final utilizou
  ambiente temporário separado, com pandas 2.3.3 e pytest 9.1.1, sem modificar
  requirements nem o ambiente principal.

O snapshot desta rota foi mantido em diretório temporário externo ao repositório.
`before.json`/`after.json` registram hashes permitidos e conferência de tamanho/data
dos arquivos que não podem ser abertos. Não foi calculado hash de conteúdo de
TEST/raw compartilhados nesta etapa. `verify_synthetic.py`, nesse diretório
temporário, adicionou as guardas de acesso aos comandos de QA.

Não foi criado congelamento real, aprovação humana, inferência ou relatório
científico. A rota foi tecnicamente verificada no seu escopo de validação de inputs,
não como execução real ponta a ponta. A validade empresarial da referência e a procedência do treinamento
continuam limitações, não falhas sanadas pelos testes de software.

### Auditoria estática pré-TEST — 01–02/10/2026

- Corrigido acesso pelos comandos históricos: `avaliar_invoice`,
  `diagnosticar_triagem_invoice`, `comparar_triagem_invoice` e
  `preparar_revisao_cega_invoice` recusam checkout/descendentes e redirecionamento
  de inputs antes de leitura/hash. Somente fixtures externas são admitidas nesses
  percursos. Não copiar dados reais para contorná-los; o guard não certifica a
  origem de cópias externas nem é sandbox contra manipulação deliberada.
- O cálculo puro das métricas, as features e os resultados históricos não mudaram.
  Testes de fronteira foram acrescentados, mas não executados nesta auditoria.
- Gate e rota mantêm configuração estrita, pins externos, expiração, destino
  exclusivo e marcador antes do acesso. Hash não autentica aprovador. Nenhuma
  aprovação ou congelamento real foi produzido.
- **Pendência técnica 1:** consumir o retorno/recibo de inputs em um fluxo real
  único até métricas e publicação, mantendo guards e estado de tentativa. Hoje
  `validate_authorized_inputs` termina em `inputs_validated.json`; `evaluate_frame`
  aceita apenas `synthetic_holdout`. Não abrir TEST com esse handoff incompleto.
- **Pendência técnica 2:** conferir bytes dos três JSONs históricos contra pins
  e vinculá-los ao freeze. O gate atual confere código/protocolo/adaptador/rota;
  o hash do protocolo fixa os hashes escritos nele, mas não verifica os arquivos
  de evidência correspondentes. O item 7 do protocolo exige essa ligação antes
  da abertura. Não alegar que ela já está implementada.
- A revisão independente foi estática. Permanecem pendentes a validação manual
  dos patches desta auditoria e, para o incremento seguinte, testes exclusivamente
  sintéticos da ligação real e do vínculo de evidências. Nenhum conteúdo de TEST
  foi lido nem seu hash recalculado; `source_reconciled=false` permanece obrigatório.
