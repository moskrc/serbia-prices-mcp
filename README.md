# serbia-prices-mcp

<!-- mcp-name: io.github.moskrc/serbia-prices-mcp -->

An MCP server for grocery prices in Serbia. It downloads the daily price lists that retail chains publish on
[data.gov.rs](https://data.gov.rs), stores them in a local DuckDB file and lets an AI assistant search, compare
and price a shopping list across chains.

Chains: Lidl, Maxi (also Mega Maxi, Shop&Go), Idea (also Mercator, Roda), Univerexport, Gomex, Aman, Metro, dm,
Aroma, Svetofor and Veropoulos — the major chains in Belgrade and Novi Sad.

It runs on your computer. There is no account, API key or hosted service.

## Why

The chains publish their prices as open data, but in a form that is hard to use directly: one CSV per chain, each
with its own column names, unit spellings and encoding problems. The portal has no search and no way to compare
chains. This server normalizes the files into one table so the assistant can answer questions like:

- Where is this product cheapest, and by how much?
- Which store is cheapest for my shopping list?
- Is this discount real, or was the regular price raised before it?
- How has the price changed over the last months?

## Example questions

You can ask in any language. The assistant translates product names to Serbian before calling the tools.

- "Price a weekly basket for two in every store: 2 l of milk, bread, 10 eggs, chicken breast, cheese, bananas,
  coffee. Which store is cheapest and how much do I save compared to the most expensive one?"
- "I'm cooking carbonara for six. Price the ingredients in Maxi, Lidl and Idea."
- "Show the 10 biggest discounts on meat and say which ones look inflated."
- "Which Lidl and Maxi promotions end tomorrow?"
- "Where is Coca-Cola 2 l cheapest, and is the two-pack promotion a better deal?"
- "Find Lurpak butter 250 g and compare that exact product across all chains."
- "How has the price of 2.8% milk changed since September in Maxi and Idea?"

## Install

You need [uv](https://docs.astral.sh/uv/getting-started/installation/). The server uses the stdio transport, so it
works in clients that start local MCP servers: Claude Code, Claude Desktop, Codex, Antigravity, Cursor, VS Code.
It does not work in web-only clients such as ChatGPT or claude.ai in the browser.

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

On the first start the server downloads about 135 MB of price lists and builds the database, which takes about
half a minute. Until then the tools return "retry in a minute". To download in advance:

```bash
uvx serbia-prices-mcp sync
```

## Tools

| Tool | Description |
|---|---|
| `search_products` | Search by name: most relevant names first, then the cheapest package. With `ean`: one exact product in all chains and store formats, with the difference from the cheapest in RSD and %. |
| `optimize_basket` | Cost of a shopping list in each store. Items are given by name or by barcode, quantity in packages. Stores that have every item come first. |
| `get_top_discounts` | Current promotions. Flags a regular price that is higher than in recent monthly snapshots, and discounts of 80% or more, which are usually clearance or data errors. |
| `get_price_history` | Monthly snapshots published by the chains plus today's price for one barcode. |
| `list_retailers_and_categories` | Chains, store formats, date of the data and the 25 product categories. |

All tools are read-only. Lists are paged with `limit` and `offset` and return `total`.

## How it works

1. For each chain the server asks the data.gov.rs API for the chain's datasets and takes the newest price list CSV.
2. It downloads all files in parallel.
3. DuckDB reads each file with one SQL query: the header is mapped to one schema, prices and dates are
   validated, invalid rows are skipped and names are prepared for search without diacritics and Cyrillic.
4. The rows go into a new DuckDB file, which then replaces the old one. If a chain fails to download or
   parse, its previous prices are kept.
5. Each tool call is one SQL query over the file, opened read-only. Queries take 30–100 ms.
6. While running, the server checks every hour and downloads again when the data is older than 20 hours.

No history is collected. The chains' files contain today's prices and monthly snapshots for recent months; price
history and the discount check use those snapshots. The database takes about 50 MB in `~/.cache/serbia-prices-mcp`.

## Settings

| Variable | Default | Description |
|---|---|---|
| `SERBIA_PRICES_MCP_DATA_DIR` | `~/.cache/serbia-prices-mcp` | Directory for `prices.duckdb` |
| `SERBIA_PRICES_MCP_TRANSPORT` | `stdio` | `http` serves Streamable HTTP at `/mcp` |
| `SERBIA_PRICES_MCP_HOST`, `SERBIA_PRICES_MCP_PORT` | `127.0.0.1`, `8000` | HTTP address |
| `SERBIA_PRICES_MCP_LOG_LEVEL` | `INFO` | Log level; logs go to stderr |

## Data

The price lists are published by the retail chains on [data.gov.rs](https://data.gov.rs) under the
[Serbian Open Data License](https://data.gov.rs/sr/terms/). The server downloads them daily; every price carries
`price_date`, the date of the chain's price list.

Changes to the data: columns are mapped to one schema, invalid rows are skipped, promotional prices not below the
regular price are dropped, text is cleaned and a search field without diacritics and Cyrillic is added. Units,
unit prices, VAT rates and promotion start dates are not loaded.

Prices are shown as published and may differ in the store. This project is not affiliated with the chains or the
portal.

## Development

```bash
uv sync
uv run pytest
uv run mypy src tests
```

## License

[MIT](LICENSE)
