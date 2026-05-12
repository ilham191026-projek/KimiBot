# SMC/ICT/CRT/MSNR Bot v3.0

A production-ready Telegram trading signal bot that performs automated multi-timeframe, multi-pair technical analysis on Forex and Metals markets using a layered Smart Money strategy.

## Overview

The bot combines four methodologies — SMC (Smart Money Concepts), ICT (Inner Circle Trader), CRT (Candle Range Theory), and MSNR (Mean Session Night Range) — into a 6-layer top-down analysis system that filters from H4 down to M1 before issuing any trade signal.

## Features

- **Multi-pair scanner**: XAUUSD, EURUSD, GBPUSD, USDJPY, GBPJPY, USDCHF, AUDUSD, USDCAD (extensible)
- **6-layer confluence analysis**: H4 → H1 → M30 → M15 → M5 → M1
- **AI reasoning layer**: Groq API (llama-3.3-70b-versatile) for signal narrative
- **Risk management**: User-configurable capital and risk percentage per trade
- **Cooldown system**: 30-minute lock per pair after each signal
- **Volatility gate**: ADX(14) H1 > 25, ATR(14) H1 between 8-35 pips
- **Session-aware scanning**: Active during London (07:00-12:00 GMT) and NY (13:00-17:00 GMT) sessions only
- **Economic calendar**: High-impact event filtering
- **Real-time Telegram signals**: HTML-formatted with AI narrative

## Project Structure

```
smc_bot_v3/
|
├── main.py                         # Entry point, scheduler loop
├── bot.py                          # Telegram bot handler, command routing
├── config.py                       # All constants, settings, pip values
├── requirements.txt                # Dependencies
├── .env.example                    # API keys template
├── README.md                       # This file
|
├── data/
│   ├── fetcher.py                  # OHLCV fetcher with fallback chain
│   ├── calendar.py                 # Economic news calendar scraper
│   └── cache.py                    # In-memory cache layer
|
├── analysis/
│   ├── layer1_h4_bias.py           # H4 market structure: HH/HL/LH/LL, BOS, CHoCH
│   ├── layer2_h1_ob_fvg.py         # H1 Order Block + FVG detection
│   ├── layer3_m30_msnr.py          # M30 MSNR wick detection + liquidity sweep
│   ├── layer4_m15_crt.py           # M15 CRT 3-step setup
│   ├── layer5_m5_mss.py            # M5 Market Structure Shift + FVG trigger
│   ├── layer6_m1_entry.py          # M1 precision entry confirmation
│   └── confluence.py               # Aggregates all 6 layers
|
├── filters/
│   ├── volatility_gate.py          # ADX/ATR volatility filter
│   ├── cooldown.py                 # 30-min per-pair cooldown tracker
│   └── spread_check.py             # Spread ≤ 2 pip filter
|
├── risk/
│   ├── sl_tp_calculator.py         # SL/TP calculation from swing points
│   ├── lot_sizer.py                # Position sizing from capital + risk %
│   └── trailing_stop.py            # 8-pip trailing stop logic
|
├── ai/
│   ├── groq_client.py              # Groq API wrapper
│   └── signal_narrator.py          # AI narrative generation
|
├── signals/
│   ├── signal_builder.py           # Signal assembly from all components
│   └── signal_formatter.py         # Telegram HTML formatting
|
└── utils/
    ├── logger.py                   # Structured logging
    ├── time_utils.py               # Session checks, GMT handling
    └── pip_calculator.py           # Instrument-specific pip calculations
```

## Setup

### 1. Clone and Install

```bash
git clone <your-repo-url>
cd smc_bot_v3
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env with your actual API keys
```

### 3. Required API Keys

| Service | Key | Purpose |
|---------|-----|---------|
| Telegram | `TELEGRAM_BOT_TOKEN` | Bot interface |
| Polygon.io | `POLYGON_API_KEY` | OHLCV data (primary) |
| Twelve Data | `TWELVE_DATA_API_KEY` | OHLCV data (fallback) |
| Alpha Vantage | `ALPHA_VANTAGE_API_KEY` | OHLCV data (fallback 2) |
| Groq | `GROQ_API_KEY` | AI signal narrative |

### 4. Run Locally

```bash
python main.py
```

## Deployment — Railway

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit - SMC Bot v3.0"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/smc-bot-v3.git
git push -u origin main
```

### 2. Connect Railway

1. Go to [Railway](https://railway.app/) and log in
2. Click "New Project" → "Deploy from GitHub repo"
3. Select your `smc-bot-v3` repository
4. Railway will auto-detect Python and install dependencies

### 3. Set Environment Variables

In Railway Dashboard → Your Project → Variables:

```
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
POLYGON_API_KEY=your_polygon_key
TWELVE_DATA_API_KEY=your_twelve_data_key
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key
GROQ_API_KEY=your_groq_key
```

### 4. Configure Start Command

In Railway Dashboard → Settings:
- Start Command: `python main.py`
- Restart Policy: Always

### 5. Deploy

Railway will auto-deploy on every push to main. Monitor logs in the Railway dashboard.

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message + available commands |
| `/status` | Show active pairs, last scan, cooldown status |
| `/signal` | Force immediate scan (bypass timer) |
| `/risk <capital> <risk%>` | Set capital and risk per trade |
| `/pairs` | List all monitored pairs |
| `/news` | Show high-impact economic events |
| `/setpairs <pairs>` | Customize scanned pairs |

### Example Usage

```
/risk 1000 1        # $1000 capital, 1% risk per trade
/signal              # Force scan now
/setpairs EURUSD,GBPUSD,XAUUSD
```

## Signal Output Format

Each signal includes:
- **Direction**: LONG (🟢) or SHORT (🔴)
- **Entry Price**: Precise entry level
- **Stop Loss**: Based on CRT swing ± 2 pip buffer
- **Take Profits**: TP1 at 1.5x RR, TP2 at 2.5x RR
- **Risk Parameters**: Lot size, dollar risk, pip SL
- **Layer Validation**: ✅ Pass / ❌ Fail per layer
- **AI Narrative**: Human-readable trade rationale from Groq
- **Economic Calendar**: High-impact events in next 4 hours

## Architecture

### 6-Layer Analysis Flow

```
H4 (Layer 1) → Market Structure (HH/HL/LH/LL) → Bias direction
      ↓
H1 (Layer 2) → Order Blocks + Fair Value Gaps → Entry zones
      ↓
M30 (Layer 3) → MSNR Wick Detection → Liquidity sweep confirmation
      ↓
M15 (Layer 4) → CRT 3-Step Pattern → Core reversal signal
      ↓
M5 (Layer 5) → Market Structure Shift + FVG → Trend confirmation
      ↓
M1 (Layer 6) → Precision Entry → Final confirmation (≥2 signals)
```

### Signal Requirements

- Minimum **5/6 layers** must pass
- ADX(14) H1 > 25 (trending market)
- ATR(14) H1 between 8-35 pips
- Spread ≤ 2 pips
- 30-minute cooldown per pair
- Active only during London/NY sessions

## Configuration

Edit `config.py` to customize:

- `DEFAULT_PAIRS`: Monitored instruments
- `SCAN_INTERVAL_SECONDS`: Scan frequency (default: 60s)
- `MIN_CONFLUENCE_SCORE`: Minimum layers required (default: 5)
- `COOLDOWN_MINUTES`: Post-signal cooldown (default: 30)
- `ADX_THRESHOLD`: Volatility gate ADX minimum (default: 25)
- `ATR_MIN_PIPS` / `ATR_MAX_PIPS`: ATR range (default: 8-35)
- `TP1_RR` / `TP2_RR`: Risk:reward ratios (default: 1.5 / 2.5)

## License

MIT License — for educational and trading purposes.