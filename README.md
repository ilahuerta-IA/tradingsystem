# 🚀 Modular Algorithmic Trading System

> **Production-grade backtesting framework built with Backtrader.**  
> Designed for multi-strategy portfolios with proper risk management.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Backtrader](https://img.shields.io/badge/backtrader-1.9.78-green.svg)](https://www.backtrader.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This repository implements a **clean, scalable architecture** for backtesting trading strategies. It features centralized configuration, precise JPY pair handling, and professional reporting.

**Currently Implemented:** EURJPY (Sunset Ogle Strategy)

---

## 📂 Project Structure

```text
TradingSystem/
├── config/
│   └── settings.py         # ⚙️ Central configuration for all strategies
├── lib/
│   └── commission.py       # 💰 Forex commission with JPY P&L correction
├── strategies/
│   └── sunset_ogle.py      # 🌅 4-Phase State Machine strategy
├── docs/
│   └── sunset_ogle.md      # 📖 Strategy documentation
├── data/                   # 📊 CSV price data (not tracked in git)
├── logs/                   # 📝 Trade logs output
├── temp_reports/           # 📈 Detailed trade reports
├── originals/              # 🗄️ Legacy reference implementations
├── run_backtest.py         # 🚀 Main entry point
├── requirements.txt        # 📦 Dependencies
└── .gitignore
```

---

## ⚡ Key Features

### 🔧 Clean Architecture
- **SOLID Principles**: Single responsibility per module
- **Centralized Config**: Change parameters without touching strategy code
- **Scalable Design**: Easy to add new strategies and assets

### 💱 JPY Pair Handling (ERIS Logic)
Backtrader has known issues with JPY pairs due to different pip values. This system implements:
- **Position Size Normalization**: Divides by JPY rate (~150) for margin calculation
- **P&L Reconstruction**: Multiplies back for accurate profit/loss reporting
- **Commission Correction**: Calculates real lot size for proper fees

### 📊 Professional Reporting
- **Detailed Trade Reports**: Entry/Exit with ATR, Angle, Pips, Duration
- **Performance Metrics**: Win Rate, Profit Factor, Gross P/L
- **Terminal Summary**: Clean output with key statistics

---

## 🚀 Quick Start

### 1. Clone & Setup
```bash
git clone https://github.com/yourusername/TradingSystem.git
cd TradingSystem
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Add Your Data
Place your CSV file in the `data/` folder. Expected format (Darwinex 5m):
```csv
Date,Time,Open,High,Low,Close,Volume
20240701,00:00:00,171.234,171.250,171.200,171.210,1234
```

### 3. Configure
Edit `config/settings.py` to set your data path and parameters.

### 4. Run
```bash
python run_backtest.py
```

---

## 📈 Sample Output

```
============================================================
STRATEGY SUMMARY
============================================================
Total Trades: 38
Wins: 12 | Losses: 26
Win Rate: 31.6%
Profit Factor: 1.55
Gross Profit: $12,744.20
Gross Loss: $8,243.33
Total P&L: $4,500.01
Final Value: $104,500.01
============================================================
```

---

## 📖 Strategy Documentation

Detailed documentation for each implemented strategy:

| Strategy | Asset | Type | Docs |
|----------|-------|------|------|
| Sunset Ogle | EURJPY | Trend Following / Breakout | [📖 Read](docs/sunset_ogle.md) |

---

## 🔧 Configuration Reference

### Strategy Parameters (`config/settings.py`)

```python
'params': {
    # EMA Configuration
    'ema_fast_length': 18,
    'ema_medium_length': 18,
    'ema_slow_length': 24,
    'ema_confirm_length': 1,
    'ema_filter_price_length': 70,
    
    # Filters
    'atr_min': 0.030,
    'atr_max': 0.090,
    'angle_min': 45.0,
    'angle_max': 95.0,
    
    # Risk Management
    'sl_mult': 3.5,      # Stop Loss = ATR × 3.5
    'tp_mult': 15.0,     # Take Profit = ATR × 15.0
    'risk_percent': 0.003,  # 0.3% per trade
}
```

---

## 🧪 Testing & Validation

This system was validated against the original monolithic implementation:

| Metric | Original | Modular System | Match |
|--------|----------|----------------|-------|
| Total Trades | 38 | 38 | ✅ |
| Win Rate | 31.58% | 31.58% | ✅ |
| Total P&L | $4,500.87 | $4,500.01 | ✅ |

---

## 📚 Learning Resources

If you're learning algorithmic trading, this codebase demonstrates:

1. **State Machine Design**: How to implement complex entry logic
2. **Risk Management**: Position sizing based on ATR and account equity
3. **Forex Specifics**: Handling JPY pairs, pip values, lot sizes
4. **Clean Code**: Separation of concerns, configuration management

---

## ⚠️ Disclaimer

**This software is for educational purposes only.**

- Past performance does not guarantee future results
- Always paper trade before using real capital
- The authors are not responsible for any financial losses

---

## 📄 License

MIT License - Feel free to use, modify, and distribute.

---

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request with clear description