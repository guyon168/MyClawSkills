---
name: binance-token-analysis
description: >
  Analyze Binance Alpha tokens and Futures contract tokens to find overlapping symbols,
  generate market reports with statistics. Use this skill whenever the user mentions
  Binance Alpha tokens, Binance Futures analysis, finding common tokens between Alpha
  and Futures, crypto token overlap analysis, or wants to compare Binance Alpha list
  with Futures trading pairs. Also trigger when the user asks about which Alpha tokens
  have futures contracts, market cap distribution of Binance tokens, or wants a
  report on Binance token data. Keywords: Binance, Alpha, Futures, token analysis,
  crypto analysis, common tokens, market cap, 合约, 代币分析.
---

# Binance Token Analysis

This skill fetches live data from Binance's public APIs, cross-references the Alpha token list with Futures contract listings, and produces a structured report of overlapping tokens sorted by market cap.

## Workflow

1. **Fetch data** from two Binance endpoints
2. **Filter & cross-reference** Alpha (online only) tokens with Futures (TRADING status, USDT pairs only)
3. **Generate reports** in JSON, CSV, and a summary with market cap distribution and top movers

## How to run

Execute the analysis script:

```bash
cd /home/claude && python /path/to/skill/scripts/analyze.py
```

Replace `/path/to/skill` with the actual skill location (check the `scripts/` directory adjacent to this SKILL.md).

The script will:
- Create a `data/` directory in the current working directory
- Save raw API responses with timestamps
- Save analysis results as JSON and CSV
- Print a formatted summary to stdout

## Understanding the output

### Filtering logic

- **Alpha tokens**: Only tokens where `offline` is `false` are included. Offline tokens are excluded.
- **Futures tokens**: Only symbols with `status == "TRADING"` and ending in `USDT` are included. The base asset is extracted by stripping the `USDT` suffix.
- **Common tokens**: The intersection of Alpha token symbols and Futures base assets.

### Report contents

Results are sorted by market cap ascending (smallest first). Each token entry includes:

| Field | Description |
|---|---|
| symbol | Token ticker (e.g., DOGE) |
| name | Full token name |
| price | Current price in USD |
| percent_change_24h | 24-hour price change percentage |
| volume_24h | 24-hour trading volume in USD |
| market_cap | Market capitalization in USD |
| chain | Blockchain network |
| contract_address | Token contract address |

### Statistics provided

- Market cap distribution (Micro/Small/Mid/Large/Mega)
- Gainer vs loser count
- Average 24h change
- Top 5 by market cap, top 5 gainers, top 5 losers

## Customization

To modify the analysis, edit `scripts/analyze.py`. Common changes:
- Change sorting order (currently market cap ascending)
- Adjust market cap tier thresholds
- Add additional filters (e.g., by chain, by volume)
- Change how many tokens display in the summary (currently top 20)

## Network requirements

The script needs outbound HTTPS access to:
- `www.binance.com` (Alpha token list API)
- `www.binance.com` (Futures exchange info API)

If running in a restricted network, ensure these domains are allowed.

## Output files

All files are saved to `data/` in the working directory:

- `Alpha_list_{timestamp}.json` — Raw Alpha API response
- `future_list_{timestamp}.json` — Raw Futures API response
- `analysis_result_{timestamp}.json` — Structured analysis with metadata
- `analysis_result_{timestamp}.csv` — Spreadsheet-friendly results
