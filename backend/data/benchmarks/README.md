# Benchmark Dataset

O diretório contém conjuntos versionados de perguntas para avaliar o Research
Discovery Agent. Cada arquivo JSON representa uma versão independente, como
`v1.0.json`.

## Formato

O arquivo possui `version`, `created_at` em ISO 8601 e uma lista `questions`.
Cada pergunta contém:

- `id`: identificador estável e único;
- `question`: pergunta de pesquisa;
- `objective`: objetivo do caso;
- `language`: idioma da pergunta;
- `depth`: `superficial`, `medium` ou `deep`;
- `expected_sources`: fontes comprovadamente esperadas, ou `null` quando não há uma lista validada;
- `evaluation_criteria`: critérios objetivos e reproduzíveis.

## Como adicionar perguntas

Adicione um objeto a `questions`, preserve IDs existentes e inclua critérios
observáveis. Não liste DOI, título ou autor como fonte esperada sem uma base
documental verificável. Casos devem cobrir áreas, profundidades e tipos de
pergunta diferentes.

## Versionamento

Não altere semanticamente uma versão já usada em avaliações. Crie `v1.1.json`
para adições compatíveis ou uma nova versão maior para mudanças incompatíveis.
O carregador usa `load_benchmark("v1.0")`.