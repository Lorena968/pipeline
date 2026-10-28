# Do pacote bruto ao dado útil — pipeline Meshtastic

Atividade individual da disciplina do prof. [@siriani](https://github.com/siriani).
Lê `pacotes_brutos` (MongoDB, somente leitura) e escreve em três destinos com prefixo `lorena`:

```
pacotes_brutos -> decodificar -> deduplicar -> validar -> quarentena (lorena_quarentena)
                                                     \-> série limpa (lorena_serie, MariaDB)
                                                     \-> agregados  (lorena_agregado, MariaDB)
                                                     \-> último valor (lorena:ultimo:*, Redis)
```

## Como rodar
```bash
cp .env.example .env   # preencha as credenciais
mysql ... < sql/schema.sql
docker compose up -d --build
docker compose logs -f
```

## Contínuo e reiniciável
- Lê por `recebido_em` a partir de um **checkpoint** salvo no MariaDB.
- Série, contadores e checkpoint são gravados **na mesma transação** — ou tudo entra, ou nada.
- Ao reiniciar, relê com janela de segurança de 5 min; a chave primária `(no_origem, pacote_id, metrica)` + `INSERT IGNORE` descarta o que já existe. Resultado: **não duplica nem perde**.
- `restart: unless-stopped` no Docker e reconexão automática em erro de banco.

## Os quatro problemas e seus contadores (`lorena_contadores`)
| Problema | Tratamento | Contador |
|---|---|---|
| Duplicatas | dedup por (nó de origem, id do pacote), nunca por conteúdo | `duplicatas` |
| Relógio errado | `instante` = recebimento; relógio do nó vai em `instante_no`; inválido se < 2020 ou > 24h de diferença | `timestamp_invalido` |
| Buracos e atrasos | silêncio > 60 min vira linha em `lorena_silencios`; sem interpolação | `buracos`, `fora_de_ordem` |
| Esquema que muda | separação por tipo, aliases camelCase/snake_case, faixas físicas | `quarentena` por `motivo` |

## Modelo
- **Série em formato longo** (métrica é linha): tipos de pacote têm campos diferentes e o firmware muda; métrica nova não exige `ALTER TABLE`.
- **Agregar por hora e dia**: a telemetria padrão sai a cada ~30 min; janelas de 15 min teriam 0–1 amostra.
- **Redis** `lorena:ultimo:<nó>:<métrica>` (hash `valor`, `instante`) e `lorena:visto:<nó>`: "e agora?" é leitura O(1) para painel, sem `ORDER BY ... LIMIT 1` no MariaDB a cada atualização.

Esquema completo: [`sql/schema.sql`](sql/schema.sql). Consultas: [`sql/consultas.sql`](sql/consultas.sql).

## Resultados (após 72 h)
> Preencher com a saída real das consultas e dos contadores ao fim do período.

| contador | valor |
|---|---|
| lidos | |
| aceitos | |
| duplicatas | |
| timestamp_invalido | |
| quarentena | |
| buracos | |
