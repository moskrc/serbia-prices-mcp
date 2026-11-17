# serbia-prices-mcp

Ask Claude, Cursor, VS Code or any MCP client that runs local servers about grocery prices in Serbia and get
answers from today's official price lists of the major chains of Belgrade and Novi Sad: Lidl, Maxi, Mega Maxi,
Shop&Go, Idea, Mercator, Roda, Univerexport, Gomex, Aman, Metro, dm, Aroma, Svetofor and Veropoulos.

Runs on your computer. No account, no API key, no server to trust: the data comes straight from the open data portal
of the Republic of Serbia, [data.gov.rs](https://data.gov.rs).

## Why

Serbian retail chains publish their price lists every day as open data on data.gov.rs. The data is there, but it is
not usable by a person:

- a separate CSV file per chain, each with its own column names, unit spellings, encodings and broken bytes;
- no search, no comparison between chains, no way to see if a "discount" is real;
- the portal itself is a file catalog, not a price comparison site.

This server turns those files into answers inside the assistant you already use:

- **Where is it cheaper** — one product across all chains and store formats, with the difference in RSD and %.
- **What does my basket cost** — a shopping list priced in every store, cheapest complete basket first.
- **Is this discount honest** — flags promotions where the regular price was raised in recent months, and 80%+
  "discounts" that are usually clearance or data errors.
- **How did the price change** — monthly snapshots the chains publish, plus today's price.
- **Any language** — ask in Serbian, Russian, English or anything else; the assistant translates product names to
  Serbian, search ignores diacritics and accepts Cyrillic.

## Example questions

Ask the way you would ask a friend who knows every price list in town. The assistant combines the tools by itself.

**Plan the shopping**

> Собери корзину на неделю для двоих: молоко 2 л, хлеб, 10 яиц, куриное филе, сыр, бананы, кофе.
> В каком магазине дешевле всего и сколько я сэкономлю по сравнению с самым дорогим? Таблицей.

> I'm cooking carbonara for 6 tonight. Price the ingredients in Maxi, Lidl and Idea and tell me where to go.

> Napravi spisak za roštilj za 10 ljudi i nađi najjeftiniju prodavnicu.

**Catch the real deals**

> Show the 10 biggest discounts on meat right now and tell me which ones look inflated.

> Какие акции в Lidl и Maxi заканчиваются завтра? Что стоит купить сегодня?

> Is the 40% discount on coffee at Maxi real, or was the regular price raised before the promotion?

**Compare and track**

> Где сейчас дешевле всего Coca-Cola 2 л — и выгоднее ли взять две по акции?

> Find Lurpak butter 250 g, then compare that exact barcode across every chain.

> Koliko je poskupelo mleko 2.8% od septembra u Maxiju i Idei?

> Which chain is cheapest for my usual list on average: milk, bread, eggs, bananas, coffee, cheese?

## Install

Needs [uv](https://docs.astral.sh/uv/getting-started/installation/). The server runs locally, so use a client that
starts local (stdio) MCP servers: Claude Code, Claude Desktop, Codex, Antigravity, Cursor, VS Code.

**Claude Code**

```bash
claude mcp add --scope user serbia-prices -- uvx serbia-prices-mcp
```

**Codex**

```bash
codex mcp add serbia-prices -- uvx serbia-prices-mcp
```

or in `~/.codex/config.toml`:

```toml
[mcp_servers.serbia-prices]
command = "uvx"
args = ["serbia-prices-mcp"]
```

**Antigravity**

```bash
agy mcp add serbia-prices uvx serbia-prices-mcp
```

**Claude Desktop** (`claude_desktop_config.json`), **Cursor** (`~/.cursor/mcp.json`)

```json
{ "mcpServers": { "serbia-prices": { "command": "uvx", "args": ["serbia-prices-mcp"] } } }
```

**VS Code** (`.vscode/mcp.json`)

```json
{ "servers": { "serbia-prices": { "type": "stdio", "command": "uvx", "args": ["serbia-prices-mcp"] } } }
```

The first start downloads today's price lists (about 135 MB, under a minute on a normal connection). Until it is done,
tools answer "retry in a minute". To download before connecting the assistant:

```bash
uvx serbia-prices-mcp sync
```

## How it works

```
data.gov.rs API ──► 11 price list CSVs ──► normalize ──► prices.duckdb ──► MCP tools ──► your assistant
```

1. **Find the files.** For each chain the server asks the data.gov.rs API for the organization's datasets and picks
   the newest price list CSV.
2. **Download** all chains in parallel into a temporary folder.
3. **Normalize.** Every row goes through one parser: column names mapped to one schema, units unified
   (`kom`, `kom.`, `KOM` → piece), prices and dates validated, zero barcodes and invalid rows skipped, diacritics
   folded for search. A chain whose file has an unknown format is reported and skipped.
4. **Build the database.** Rows are loaded into a new DuckDB file next to the old one, which is then replaced in one
   step, so the assistant never sees half-loaded data. A chain that failed to download or parse keeps its previous
   prices.
5. **Answer.** Each tool is one SQL query over the local file (tens of milliseconds); the file is opened read-only, so
   several assistants on the same computer can use it at once.
6. **Refresh.** While the server runs it checks every hour and downloads again when the data is older than 20 hours.

Nothing is collected over time. The chains' files carry today's prices and monthly snapshots of recent months, which is
enough for price history and for checking discounts. The database is about 50 MB in `~/.cache/serbia-prices-mcp`.

## Tools

| Tool | What it does |
|---|---|
| `search_products` | find products; most relevant names first, then the cheapest package |
| `compare_by_barcode` | the same product (EAN) in all chains with the price difference |
| `optimize_basket` | basket cost per store; items by name or by exact barcode, quantity in packages |
| `get_top_discounts` | current promotions; flags a regular price raised before the promotion and discounts of 80% or more |
| `get_price_history` | monthly snapshots published by the chains plus today's price |
| `list_retailers_and_categories` | chains, store formats, data dates and categories |

All tools only read data. Lists are paged (`limit`, `offset`, `total`).

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `SERBIA_PRICES_MCP_DATA_DIR` | `~/.cache/serbia-prices-mcp` | where `prices.duckdb` lives |
| `SERBIA_PRICES_MCP_TRANSPORT` | `stdio` | `http` to serve Streamable HTTP at `/mcp` |
| `SERBIA_PRICES_MCP_HOST`, `SERBIA_PRICES_MCP_PORT` | `127.0.0.1`, `8000` | HTTP address |
| `SERBIA_PRICES_MCP_LOG_LEVEL` | `INFO` | log level; logs go to stderr |

## Data

Price lists are published by the retail chains on [data.gov.rs](https://data.gov.rs) under the Open Data License
of the Republic of Serbia. Prices are shown as published and may differ in the store. This project is not affiliated
with the chains or the portal.

## Development

```bash
uv sync
uv run pytest
uv run mypy src tests
```

## License

[MIT](LICENSE)
