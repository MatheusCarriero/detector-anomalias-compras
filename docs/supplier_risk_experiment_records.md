# Registros de evidência experimental do Supplier Risk

## 1. Finalidade e estado

**IMPLEMENTADO:** o módulo `ml/supplier_risk/scripts/experiment_artifact.py` define um contrato JSON verificável para **novos** experimentos Supplier. Ele usa somente a biblioteca padrão e não carrega datasets, modelos, pandas ou scikit-learn. Um arquivo registra um único estimador, uma única configuração e um único cenário.

**LIMITAÇÃO:** as primeiras rodadas e a validação científica exploratória não persistiram vetores individuais de predição nesse formato. Métricas agregadas, matrizes de confusão e uma reprodução diagnóstica não permitem reconstruir nem certificar o vetor histórico. Nenhum registro real foi fabricado ou retroativamente preenchido neste fechamento; o helper ainda não possui registros reais.

O registro melhora a rastreabilidade interna de execuções futuras. Ele não transforma um experimento em modelo final, não autoriza acesso a TEST e não comprova validade empresarial de `Risk_Level`.

## 2. API pública e CLI

```python
from ml.supplier_risk.scripts.experiment_artifact import (
    verify_experiment_record,
    write_experiment_record,
)

record_path = write_experiment_record(path, predictions, metadata)
envelope = verify_experiment_record(record_path)
```

- `write_experiment_record(path, predictions, metadata) -> Path` valida todo o conteúdo e a serialização antes de criar diretórios, grava um arquivo novo e recusa sobrescrever um destino existente.
- `verify_experiment_record(path) -> dict` lê e valida o envelope, o esquema, os invariantes, os fingerprints de IDs e o digest.
- O comando abaixo verifica **somente** o JSON indicado e retorna código diferente de zero quando a verificação falha:

```powershell
python ml/supplier_risk/scripts/experiment_artifact.py verify caminho\registro.json
```

O verificador rejeita chaves JSON duplicadas, números não finitos, versão ou campos desconhecidos, digest divergente, fingerprints divergentes, IDs inválidos/repetidos e splits fora da allowlist.

## 3. Predições permitidas

`predictions` é uma lista de objetos com **exatamente** estas chaves:

| Campo | Contrato |
|---|---|
| `supplier_id` | string não vazia, sem espaços nas extremidades e única em todo o arquivo |
| `split` | somente `train` ou `validation` |
| `y_true` | inteiro `0` ou `1`; `bool` não é aceito |
| `y_pred` | inteiro `0` ou `1`; `bool` não é aceito |
| `probability_class_1` | número real finito no intervalo fechado `[0, 1]` |

As linhas são ordenadas canonicamente por `split` e `supplier_id`. A API deliberadamente não aceita `test`: nesta versão, ela serve ao ciclo de desenvolvimento anterior ao congelamento final. Uma futura avaliação TEST exige autorização e protocolo próprios, não uma ampliação silenciosa da allowlist.

`probability_class_1` significa apenas probabilidade estimada de pertencimento à classe `1` do dataset. Não é probabilidade validada de fraude, falha, ruptura ou outro evento real; tampouco é necessariamente calibrada.

## 4. Metadata obrigatório

O objeto `metadata` aceita somente os campos abaixo. Todos os obrigatórios precisam estar presentes.

| Campo | Contrato |
|---|---|
| `experiment_name` | string não vazia |
| `estimator` | string não vazia |
| `scenario` | `A`, `B`, `C` ou `D` |
| `features` | lista ordenada exatamente igual ao contrato do cenário |
| `parameters` | objeto JSON estrito; números devem ser finitos |
| `seeds` | objeto não vazio de nome para inteiro; `bool` não é inteiro válido |
| `versions` | objeto não vazio de nome para string não vazia |
| `input_hashes` | objeto não vazio de nome para SHA-256 hexadecimal |
| `code_sha256` | SHA-256 hexadecimal do código de referência |
| `expected_id_hashes` | mapa dos splits presentes para o fingerprint SHA-256 dos IDs esperados |
| `notebook_sha256` | opcional; quando presente, SHA-256 hexadecimal |

### Cenários e ordem das features

O cenário A usa, nesta ordem:

1. `financial_stability_score`
2. `on_time_delivery_rate`
3. `defect_rate`
4. `geopolitical_risk_index`
5. `lead_time_days`
6. `alternative_suppliers_available`
7. `contract_length_months`
8. `environmental_compliance`
9. `previous_disruptions`
10. `supplier_record_count`

B remove somente `geopolitical_risk_index`; C remove somente `supplier_record_count`; D remove ambos. A ordem relativa restante é preservada. O contrato valida a lista, mas não declara um cenário vencedor nem uma lista final de produção.

### Fingerprints dos IDs

Para cada split presente, `expected_id_hashes` deve ser calculado sobre a lista de `supplier_id` ordenada. A lista é serializada em JSON canônico UTF-8 com `ensure_ascii=False`, `sort_keys=True`, separadores compactos e `allow_nan=False`; o SHA-256 hexadecimal dessa sequência é o fingerprint esperado.

Os fingerprints ajudam a detectar troca, falta ou acréscimo de IDs. Como os valores esperados são fornecidos pelo chamador, eles não provam por si só qual fonte foi lida ou que TEST nunca foi consultado.

## 5. Envelope e integridade

O arquivo contém:

```text
schema_version = 1.0.0
created_at
artifact_id
payload
  domain = supplier_risk
  target = Risk_Level
  probability_semantics = estimated_probability_of_Risk_Level_1
  metadata
  predictions
  record_count
  id_hashes
```

`created_at` é UTC. `artifact_id` é o SHA-256 do `payload` canônico e não inclui o timestamp; por isso permanece estável quando as mesmas linhas válidas são fornecidas em outra ordem. `id_hashes` é recalculado a partir das predições e confrontado com `expected_id_hashes`.

Comparações de SHA-256 ignoram diferenças entre letras hexadecimais maiúsculas e minúsculas. O verificador não reescreve essa representação: preserva os valores armazenados e calcula o digest canônico sobre o payload exatamente representado. Assim, mudar a caixa dentro do payload sem recalcular `artifact_id` continua sendo detectado como adulteração.

Texto Unicode que não pode ser codificado como UTF-8 é erro de contrato. Na escrita, a validação e a serialização falham antes da criação do diretório ou arquivo; na API e no CLI, o diagnóstico permanece imprimível de forma segura mesmo quando o valor inválido contém um surrogate isolado.

**LIMITAÇÃO:** checksum é controle de consistência, não assinatura digital, identidade do executor, selo de procedência ou prova de correção científica. `input_hashes`, `code_sha256`, `notebook_sha256` e fingerprints são declarações do chamador verificadas quanto ao formato/coerência interna; o helper não abre as fontes para atestar sua origem.

## 6. Uso no próximo experimento

Antes de executar um novo experimento real:

1. extrair dos notebooks os helpers experimentais reutilizáveis e o carregador com allowlist explícita de splits;
2. testar esses módulos com dados sintéticos, incluindo recusa de TEST no caminho de desenvolvimento;
3. tornar os notebooks consumidores finos desses módulos, sem duplicar regras de features, splits ou métricas;
4. registrar previamente objetivo, orçamento, cenários, parâmetros, seeds, versões e hashes;
5. gerar um registro por estimador/configuração/cenário, sem sobrescrever arquivos;
6. verificar cada JSON pela API ou CLI antes de usá-lo em análises agregadas.

**PLANEJADO:** essa extração e o afinamento dos notebooks. Os notebooks históricos não foram refatorados ou reexecutados neste fechamento.

## 7. Publicação e retenção

A escrita exclusiva protege um arquivo individual contra sobrescrita acidental, mas não oferece transação entre vários registros ou entre registros, métricas, modelos e metadata.

**PLANEJADO:** publicar conjuntos de artefatos futuros em diretório temporário exclusivo, validar manifest e hashes completos e somente então promover atomicamente o conjunto para um destino versionado. Até essa implementação, uma falha no meio de uma sequência deve ser tratada como execução incompleta; arquivos novos e antigos não podem ser misturados como se formassem uma execução coerente.

Os JSONs experimentais não devem conter dados além do contrato, segredos, caminhos com credenciais ou atributos pessoais adicionais. Política de retenção, controle de acesso, assinatura e armazenamento externo ainda precisam ser definidos antes de uso operacional.

## 8. Relação com o protocolo científico

O fluxo metodológico permanece:

```text
TRAIN: explorar, ajustar e treinar
VALIDATION: comparar e selecionar
congelamento explícito: features, transformações, modelo, parâmetros e threshold
TEST: uma única avaliação final autorizada
```

Não haverá refit em `TRAIN + VALIDATION` no protocolo atual. O resultado de TEST será apenas avaliação da configuração já congelada e não poderá realimentar a seleção. O [roadmap de implementação](implementation_roadmap.md) descreve os gates até essa etapa.
