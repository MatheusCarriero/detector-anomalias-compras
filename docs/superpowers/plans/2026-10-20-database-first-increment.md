# Primeiro incremento PostgreSQL/Prisma — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans para execução nativa, ou superpowers:subagent-driven-development se esse método for escolhido na revisão. Os passos abaixo não autorizam conexão, criação de banco ou aplicação de migration em um alvo ainda não identificado.

**Goal:** Implementar as 11 tabelas operacionais aprovadas e suas garantias de identidade, histórico, snapshots e auditoria, sem importar dados acadêmicos.

**Architecture:** Um banco PostgreSQL 18, schema lógico `app`, Prisma ORM 7 para a representação suportada e migrations SQL para as invariantes restantes. Escritas de estado versionado e selagem passam por rotinas transacionais do banco; o papel da aplicação não pode contornar essas rotinas com DML direto. Nenhuma tabela ou execução ML pertence ao incremento.

**Tech Stack:** PostgreSQL 18; Prisma, client e adapter-pg 7.10.0; pg 8.16.3; Node.js 24; testes `node:test` com fixtures artificiais. As versões npm exatas foram consultadas no registro público, sem instalação.

**Spec:** Especificação física aprovada na conversa, seguida do pedido de implementação do primeiro incremento e da retomada em 20/10/2026. Este plano operacionaliza esse escopo; não substitui os protocolos científicos existentes.

**Estado:** aprovado para execução nativa em 20/10/2026. Artefatos offline do primeiro incremento criados; validação/geração Prisma e testes estáticos executados. Migration não aplicada e testes SQL não executados: banco alvo e papéis ainda não identificados. O incremento não está validado para uso.

## Global Constraints

- Exatamente 11 tabelas de domínio: `currencies`, `departments`, `users`, `suppliers`, `purchase_order_lines`, `source_identities`, `source_references`, `record_versions`, `decision_snapshots`, `snapshot_members`, `audit_events`.
- A tabela técnica de controle de migrations do Prisma, se criada, não é uma entidade de domínio. Declarar sua localização antes da aplicação e separá-la da contagem das 11 tabelas.
- Schema lógico `app`; UUID v4 com `gen_random_uuid()`; DATE para datas civis; TIMESTAMPTZ(3) para instantes.
- NUMERIC(24,6) para montantes, NUMERIC(24,8) para preços unitários e NUMERIC(20,6) para quantidades. Não passar dinheiro por Number/float.
- Nenhuma instalação global, PostgreSQL novo, serviço Windows, Docker, backend, frontend ou API de negócio.
- Não abrir datasets, Excel, TEST/raw, modelos ou resultados científicos para esta implementação. Não executar notebooks ou scripts ML.
- Não criar cabeçalhos de pedido, contratos, aprovações, entregas, faturamento, pagamentos ou tabelas ML. Não introduzir `source_reconciled` no banco operacional.
- Preservar todas as mudanças locais. Não fazer staging, commit, push, reset, restore, stash, clean ou limpeza de diretórios do usuário.
- Não instalar nem conectar antes dos gates correspondentes. Não procurar senhas em arquivos ou imprimir URLs com credenciais.
- Não tomar uma decisão estrutural nova durante a execução: registrar a questão e interromper o componente afetado.
- A migration única permanece não aplicada durante sua elaboração. Concluir e revisar tabelas, rotinas, permissões e invariantes antes da primeira aplicação; nunca editar uma migration já aplicada. Correções posteriores exigem nova migration ou uma decisão explícita sobre um ambiente descartável, sem reset automático.

## Inspeção já realizada

- HEAD: `f220740`; staging vazio.
- Alterações preexistentes: README.md, docs/data_strategy.md, docs/implementation_roadmap.md, docs/purchase_risk_model.md e notebooks Supplier 01/02.
- Não foram encontrados package.json, infraestrutura Prisma, migrations SQL, NestJS ou compose no repositório. backend/ e frontend/ contêm apenas .gitkeep.
- PostgreSQL 18.6 instalado; serviço `postgresql-x64-18` ativo e processo ouvindo TCP 5432. Nenhuma conexão SQL foi feita; bancos, usuários e credenciais não foram inspecionados.
- Node.js 24.13.1 e npm 11.14.0 disponíveis. Nenhum pacote instalado nesta preparação.
- README e documentos científicos continuam descrevendo um projeto acadêmico; a implementação de banco foi autorizada separadamente, sem liberar modelagem Purchase.

## Gate operacional do PostgreSQL

Antes da primeira conexão, identificar host, porta, banco exclusivo, usuário de migração, usuário/papel de aplicação, schema e operação. Não assumir que a instância detectada seja um alvo descartável.

O alvo e os papéis ainda não foram fornecidos. `localhost:5432` é uma possibilidade local, não uma conexão aprovada nem confirmação de banco seguro. Não criar banco, papel ou credencial por inferência.

Publicar o comando exato sob **AGORA É NO POSTGRESQL** antes de executá-lo, sem revelar senha. Usar credenciais fornecidas por configuração local segura, não registradas em Git. A mesma regra vale para consultas diagnósticas, migrations e testes de integração.

Sem alvo seguro, concluir somente os artefatos offline e as verificações que não conectam. Não declarar SQL, isolamento, concorrência ou permissões validados.

## Review Focus

1. Constraints diferidas só são testadas quando verificadas: casos negativos devem forçar `SET CONSTRAINTS ALL IMMEDIATE` ou alcançar COMMIT, não apenas ROLLBACK.
2. DML fora das rotinas: testar UPDATE da projeção/head, alteração de histórico, DELETE, TRUNCATE e acesso a funções internas com o papel real da aplicação.
3. Corridas de versionamento e selagem: duas conexões reais, barreiras observáveis e timeouts; não substituir concorrência por chamadas sequenciais ou sleeps arbitrários.
4. Precisão antes do cast: valores monetários e timestamps com fração excessiva devem ser recusados a partir da representação original, não depois do arredondamento do PostgreSQL.
5. Isolamento do teste: URL específica de teste, banco exclusivo, nenhum fallback para DATABASE_URL, fixtures identificáveis, sem DROP/TRUNCATE automático ou acesso ao filesystem científico.

## Arquivos previstos

| Arquivo | Responsabilidade |
|---|---|
| package.json / package-lock.json | Dependências locais fixadas e comandos explícitos de infraestrutura |
| prisma.config.ts | Configuração Prisma 7; conexão somente por variável fornecida explicitamente |
| prisma/schema.prisma | Modelos das 11 tabelas, tipos, relações, mapeamentos e índices suportados |
| prisma/migrations/migration_lock.toml | Provider PostgreSQL |
| prisma/migrations/20261020000100_first_increment/migration.sql | Schema, tabelas, constraints, índices e SQL transacional customizado |
| prisma/README.md | Operação segura, papéis, invariantes SQL e limites do que foi validado |
| tests/database/contract.test.mjs | Inspeção estática de escopo e configuração, sem conexão |
| tests/database/helpers.mjs | Conexões explícitas de teste, fixtures sintéticas e utilitários de transação |
| tests/database/catalog.integration.test.mjs | Estrutura física real após migration |
| tests/database/versioning.integration.test.mjs | Identidade, cadeia, projeção, precisão e rollback |
| tests/database/snapshots.integration.test.mjs | Composição, selagem, imutabilidade e corridas |
| tests/database/permissions.integration.test.mjs | Papel da aplicação e bloqueio de bypass |

Não alterar README, docs científicos, requirements Python, workflows ML ou notebooks. Se a geração Prisma exigir saída ignorada, acrescentar somente essa entrada à .gitignore após conferir seu diff; node_modules já está ignorado. Não criar wrappers Python ou dependências de lint apenas para esta tarefa.

## Contratos de implementação a preservar

### Identidade e observações

- `source_identities`: UNIQUE(namespace, entity_kind, source_id); os três campos formam a identidade canônica e não podem ser reinterpretados a cada importação.
- Proprietários tipados para supplier, department e purchase_order_line. Não resolvida = zero proprietários; resolvida = exatamente um, compatível com o tipo.
- Resolução deve ser registrada; uma identidade resolvida não pode ser redirecionada silenciosamente. Não implementar merge/remapeamento nesta fase.
- `source_references`: observação imutável, com identidade opcional, versão/chave/localização da fonte, conteúdo original necessário, hashes disponíveis e timestamps de registro/disponibilidade explicitamente distintos.
- Não repetir source_id como segunda chave canônica. Namespace/tipo repetidos para observações sem identidade devem concordar por FK composta quando a identidade existir.
- Hash não prova disponibilidade histórica, validade empresarial ou origem de treinamento. Identificação ausente permanece ausente.

### Versões e projeções

- Versionar somente suppliers, departments e purchase_order_lines. Propriedade da versão por três FKs tipadas e CHECK XOR, nunca apenas texto entity_type/entity_id.
- Entidades possuem current_version_id; revision_no existe somente em record_versions. Versionamento inicial 1; predecessor obrigatório depois; mesmo proprietário, incremento exato e predecessor não compartilhado.
- FK composta diferida do head garante pertencimento; validação transacional também exige head terminal da cadeia.
- Estado autoritativo = atributos escalares do payload com schema versionado + FKs reais de contexto. Toda coluna operacional precisa de mapeamento explícito; campos técnicos não são duplicados como estado de negócio.
- A migration deve documentar o mapa completo coluna operacional → versão antes de aceitar escrita. Se o detalhamento exigir atributo ou regra de negócio não sustentado pela especificação, parar e solicitar a decisão; não preencher lacunas com campos do Excel.
- Rotinas SQL tipadas de criação/revisão recebem estado, referência de origem opcional, ator e expected_current_version_id; retornam entity_id, version_id e revision_no. Assinaturas finais devem constar do guia técnico e dos testes.
- Escrita bloqueia o proprietário, confere expected head e atualiza versão, projeção, head e auditoria atomicamente. A proteção deve cobrir alteração SQL direta, não apenas o caminho feliz da rotina.
- Revisões e observações registradas são imutáveis. Correção por nova revisão, não por fechamento silencioso de effective_to na versão antiga.

### Captura e selagem

- Único purpose: record_capture. Raiz única de tipo purchase_order_line. Sem reconstrução histórica, aprovação ou scoring.
- Após adquirir os locks, raiz e contextos correspondem às versões correntes da linha, fornecedor e departamento; não utilizar heads consultados antes dos locks como autoridade.
- Adquirir locks de entidades em ordem determinística, revalidar vínculos e rejeitar/reiniciar a captura se mudarem durante a aquisição.
- Toda mutação de membros/raiz e selagem compartilha o lock do pai. A rotina exige READ COMMITTED e consulta membros após obter o lock.
- UNIQUE(snapshot, versão) e UNIQUE parcial(snapshot, proprietário). FKs compostas dos membros validam correspondência de proprietário; a raiz referencia um membro do mesmo snapshot por FK diferida.
- Selagem valida raiz, fechamento dos contextos existentes, roles, ausência de conflito e conteúdo antes de fixar hash e sealed_at na mesma transação.
- Hash tem formato determinístico/versionado, com ordem explícita de membros, representação decimal textual e instantes normalizados; não depender da ordem de objetos fornecida pelo cliente.
- Após selagem, root, members, conteúdo e hash são imutáveis; não permitir reabrir. Um snapshot contemporâneo não prova disponibilidade pré-aprovação passada.

### Permissões e tipos

- Prisma deve usar FKs reais do PostgreSQL, não emulação de relações. NO ACTION DEFERRABLE somente nas relações cíclicas que exigem isso; RESTRICT nos vínculos históricos restantes.
- CHECK XOR, finitude, nulidade coerente, revisão e intervalos; regras entre linhas em validações transacionais, não subqueries em CHECK.
- Parser recebe representação original textual de dinheiro e tempo e valida representabilidade antes de NUMERIC(p,s)/TIMESTAMPTZ(3). Preservar origem quando não for normalizável; não inventar moeda, timezone ou valor zero.
- Papel da aplicação não é proprietário, superuser nem migrador. Revogar execução pública das funções e DML que permitiria bypass. Se SECURITY DEFINER for necessário, proprietário e search_path são controlados; não usar flag de sessão editável como autorização.
- Não há CASCADE DELETE de evidência, SET NULL de autoria nem limpeza ampla de dados de teste. A implantação de papéis existentes requer identificação prévia, não CREATE ROLE silencioso.

---

### Task 1: Configuração local e contrato estático

**Files:** package.json, package-lock.json, prisma.config.ts, prisma/schema.prisma, tests/database/contract.test.mjs.

**Interfaces:** scripts npm separados para validate, generate, verificação estática e integração. Nenhum script postinstall/pretest aplica migrations ou conecta ao banco.

- [x] Criar os testes estáticos antes do schema: exigir PostgreSQL, app, conjunto exato de modelos, versões 7 fixadas, ausência de seed/importador/ML, ausência de credenciais e de fallback de conexão em testes.
- [x] Executar `node --test tests/database/contract.test.mjs` e registrar falha esperada pela ausência da infraestrutura; não confundir erro de sintaxe do teste com RED válido.
- [x] Criar configuração mínima e modelos Prisma sem tentar representar DEFERRABLE/triggers como funcionalidades nativas do schema.
- [x] Instalar somente as versões locais confirmadas, após revisar scripts de instalação; gerar lockfile e registrar a resolução. Não usar latest ou instalação global.
- [x] Executar o teste estático novamente, `npm run db:validate`, `npm run db:generate` e `npm ls --all`. Os comandos offline não devem conectar nem requerer credenciais reais.
- [x] Revisar o diff, incluindo arquivos não rastreados. Não fazer commit.

### Task 2: Migration física e identidade

**Files:** migration_lock.toml, migration.sql, helpers.mjs, catalog.integration.test.mjs, versioning.integration.test.mjs.

**Interfaces:** schema app com 11 tabelas de domínio; nomes físicos aprovados; SourceIdentity separada de SourceReference; papéis de migração/aplicação fornecidos externamente.

- [ ] Escrever testes de catálogo para schema, tipos/precisões, defaults UUID, PK/UNIQUE/FKs, deferrabilidade e ausência das tabelas posteriores. Escrever testes de identidade duplicada, owner XOR e origem incompatível.
- [ ] Se houver alvo explicitamente identificado, anunciar comando e executar RED em banco exclusivo ainda sem o incremento. Sem alvo, registrar que os testes não foram executados e continuar somente a elaboração offline permitida.
- [ ] Criar migration versionada com schema, tabelas, índices justificados e constraints simples/compostas. Não criar roles ou banco implicitamente; não usar IF NOT EXISTS para esconder estrutura incompatível.
- [ ] Manter a migration ainda não aplicada; as tarefas 3 e 4 completam o mesmo arquivo. Não usar migrate reset ou db push como substituto da migration revisada.
- [ ] Reservar a aplicação e a conferência real de catálogo para a tarefa 5, depois da revisão do arquivo completo.

### Task 3: Cadeia, projeção, precisão e auditoria

**Files:** migration.sql, versioning.integration.test.mjs, permissions.integration.test.mjs.

**Interfaces:** rotinas de criação/revisão tipadas; cada alteração confirmada produz exatamente uma versão e o evento correspondente; expected_current_version_id impede perda silenciosa de atualização.

- [ ] Antes das rotinas, criar casos RED: revisão inicial inválida, predecessor indevido/alheio, salto, repetição, bifurcação, head alheio/não terminal, projeção divergente, UPDATE/DELETE do histórico e auditoria.
- [ ] Se o alvo exclusivo estiver disponível, executar os casos antes da implementação e registrar falha por funcionalidade ausente. Não considerar falta de tabela/função uma aprovação dos casos negativos; após implementar, exigir o SQLSTATE da invariante esperada. Sem alvo, registrar que RED comportamental não pôde ser executado.
- [ ] Incluir dinheiro fora da escala/faixa, NaN/infinito, timestamp submilissegundo, instante sem timezone, pares valor/moeda e nulidades. Verificar a representação original antes do cast.
- [ ] Implementar cadeia, projection/head e audit na mesma transação, mais proteção das escritas diretas. Comparar cada campo tipado, inclusive NULL; não comparar apenas dois JSONs fornecidos pelo cliente.
- [ ] Preparar testes que forcem constraints diferidas, COMMIT válido no ciclo entidade/primeira versão e rollback total quando auditoria ou validação falhar; executar GREEN após a aplicação completa na tarefa 5.
- [ ] Preparar testes de duas conexões criando sucessores do mesmo predecessor e mutações em proprietários distintos; exigir serialização/conflito sem lost update na tarefa 5.
- [ ] Preparar verificações com papel da aplicação para UPDATE, DELETE, TRUNCATE, ALTER e funções internas. Não apresentar testes apenas como proprietário como prova de permissões.

### Task 4: Captura contemporânea e selagem

**Files:** migration.sql, snapshots.integration.test.mjs, helpers.mjs.

**Interfaces:** operação de captura da linha corrente e contexto; selagem transacional; draft e sealed explícitos; hash reproduzível sobre membros e versões imutáveis.

- [ ] Escrever RED para raiz incorreta/ausente, versão duplicada, duas versões do mesmo owner, role/contexto divergente, fornecedor/departamento omitido indevidamente e tentativa de operar fora de READ COMMITTED.
- [ ] Implementar bloqueios e composição contemporânea. Não aceitar timestamp retroativo do chamador como prova de disponibilidade nem inferir campos ausentes.
- [ ] Implementar seal e proteção posterior da raiz, membros e conteúdo. Qualquer falha deve preservar ausência de selagem parcial.
- [ ] Preparar testes de captura completa com e sem relações opcionais, igualdade determinística do hash, recusa de alteração/reabertura e rollback; executar após a aplicação completa na tarefa 5.
- [ ] Preparar testes com duas conexões para seal versus INSERT/UPDATE/DELETE de membro, alteração da raiz e nova versão operacional. Sincronizar por bloqueio/barreira verificável, com timeout limitado e liberação em finally.
- [ ] Documentar os resultados reais de concorrência; se não executados, deixar essa garantia como não validada, mesmo com inspeção estática aprovada.

### Task 5: Guia operacional e fechamento

**Files:** prisma/README.md e somente ajustes necessários nos arquivos novos.

**Interfaces:** instruções de execução com alvo explícito, tabela Prisma versus SQL customizado, estado verificável das validações e limites conhecidos.

- [ ] Documentar comando por comando, distinguindo operações offline e PostgreSQL. Não registrar senha, URL autenticada, dados científicos ou comandos destrutivos de limpeza.
- [ ] Revisar a migration inteira antes de sua primeira aplicação. Com alvo e papéis identificados e comando anunciado, aplicar o arquivo completo uma única vez e conferir catálogo e checksums. Sem essas condições, parar antes da conexão.
- [ ] Executar os testes direcionados de infraestrutura permitidos. Não executar pytest, Ruff, notebooks ou suites científicas sem mudança correspondente e inspeção própria; este incremento não depende delas.
- [ ] Conferir que cada caso negativo falhou pela invariante/SQLSTATE esperados, e não por funcionalidade ausente ou erro de acesso incidental. Executar os casos positivos, diferidos, de rollback, privilégios e concorrência previstos nas tarefas 2 a 4. Uma correção após aplicar não pode modificar a migration registrada.
- [ ] Executar `git diff --check`; verificar whitespace dos arquivos novos sem staging; conferir integridade dos seis arquivos preexistentes e git status/diff --stat.
- [ ] Solicitar revisão independente do schema, migration, permissões e testes, procurando bypass, efeitos de NULL, coerção antes de CHECK, isolamento e deferrabilidade.
- [ ] Relatar o que existe no repositório, o que foi aplicado no banco e o que foi efetivamente testado como três estados distintos. Não declarar conclusão quando houver invariantes relevantes sem implementação ou teste necessário.

## Estratégia de testes e descarte

### Ponto de parada desta execução

As tarefas 2–4 possuem schema, migration customizada e testes sintéticos preparados,
mas não têm RED/GREEN comportamental no PostgreSQL. Na tarefa 5, o guia operacional
foi criado e a revisão independente produziu achados parciais; o revisor atingiu
o limite de uso antes do parecer final. Foram corrigidos o bootstrap/search_path e
as lacunas apontadas nos testes de rollback, permissões e concorrência. A validação
SQL e o encerramento da revisão permanecem pendentes. Não aplicar a migration nem
conectar antes da identificação explícita do banco exclusivo e dos papéis.

Os testes de integração usam variável própria para um banco exclusivo, sem fallback para o banco normal da aplicação. Exigem marcador explícito de execução sintética e recusam alvos não identificados. Não criam/apagam bancos automaticamente.

Fixtures usam nomes/IDs artificiais próprios da execução. Casos com COMMIT e concorrência deixam apenas fixtures no banco descartável dedicado; não usar DELETE/TRUNCATE que contorne imutabilidade para "limpar" testes. Descarte do banco será uma operação posterior, explícita, sobre o alvo exato, nunca um teardown genérico.

Asserções não podem passar por um erro incidental. Constraints diferidas devem ser efetivamente verificadas. Timeouts e sessões devem ser encerrados de modo seguro, sem encerrar processos PostgreSQL ou sessões alheias.

## Revisão e autorização do plano

Método recomendado: execução nativa pelo agente principal, tarefas sequenciais devido ao acoplamento das FKs/rotinas, com revisão independente final. A implementação física geral está autorizada pelo usuário; a skill writing-plans exige revisão deste plano antes de iniciar os arquivos executáveis.

Após revisão do plano, a parte offline pode começar. A parte conectada permanece condicionada à identificação do banco e papéis, com anúncio da operação/comando antes de executar. A detecção de PostgreSQL instalado não substitui esse gate.
