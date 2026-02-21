"""
Position Sizing Module - Modular calculation for any currency pair.
==================================================================

Replicates EXACTLY the position sizing from original strategies:
- sunrise_ogle_eurjpy_pro.py (lines 923-959)
- sunrise_ogle_eurusd_pro.py (lines 1474-1505)
"""


def calculate_position_size(
    entry_price: float,
    stop_loss: float,
    equity: float,
    risk_percent: float,
    pair_type: str,
    lot_size: int = 100000,
    jpy_rate: float = 150.0,
    pip_value: float = 0.0001,
    margin_pct: float = 20.0,
) -> int:
    """
    Calculate position size based on pair type.
    
    Returns:
        Position size in units for Backtrader (bt_size).
    """
    if pair_type == 'ETF':
        return _calculate_etf_position(
            entry_price, stop_loss, equity, risk_percent, margin_pct
        )
    elif pair_type == 'JPY':
        return _calculate_jpy_pair(
            entry_price, stop_loss, equity, risk_percent,
            lot_size, jpy_rate, pip_value
        )
    else:
        return _calculate_standard_pair(
            entry_price, stop_loss, equity, risk_percent, lot_size
        )


def _calculate_standard_pair(
    entry_price: float,
    stop_loss: float,
    equity: float,
    risk_percent: float,
    lot_size: int,
) -> int:
    """
    Position sizing for STANDARD pairs (EURUSD, GBPUSD, AUDUSD, etc.)
    
    EXACT replica from sunrise_ogle_eurusd_pro.py lines 1474-1505:
    
        raw_risk = entry_price - self.stop_level
        risk_per_contract = raw_risk * self.p.contract_size
        contracts = max(int(risk_val / risk_per_contract), 1)
        bt_size = contracts * self.p.contract_size
    """
    raw_risk = entry_price - stop_loss
    
    if raw_risk <= 0:
        return 0
    
    risk_val = equity * risk_percent
    risk_per_contract = raw_risk * lot_size
    
    if risk_per_contract <= 0:
        return 0
    
    contracts = max(int(risk_val / risk_per_contract), 1)
    
    if contracts <= 0:
        return 0
    
    bt_size = contracts * lot_size
    
    return bt_size


def _calculate_jpy_pair(
    entry_price: float,
    stop_loss: float,
    equity: float,
    risk_percent: float,
    lot_size: int,
    jpy_rate: float,
    pip_value: float,
) -> int:
    """
    Position sizing for JPY pairs (EURJPY, USDJPY, GBPJPY, etc.)
    
    EXACT replica from sunrise_ogle_eurjpy_pro.py lines 923-959:
    
        raw_risk = entry_price - self.stop_level
        pip_risk = raw_risk / self.p.pip_value
        pip_value_jpy = self.p.contract_size * self.p.pip_value
        value_per_pip = pip_value_jpy / entry_price
        optimal_lots = risk_val / (pip_risk * value_per_pip)
        optimal_lots = max(0.01, round(optimal_lots, 2))
        real_contracts = int(optimal_lots * self.p.contract_size)
        bt_size = int(real_contracts / self.p.jpy_rate)
    """
    raw_risk = abs(entry_price - stop_loss)
    
    if raw_risk <= 0:
        return 0
    
    risk_val = equity * risk_percent
    
    # Line 930: pip_risk = raw_risk / self.p.pip_value
    pip_risk = raw_risk / pip_value
    
    # Line 933: pip_value_jpy = self.p.contract_size * self.p.pip_value
    pip_value_jpy = lot_size * pip_value
    
    # Line 936: value_per_pip = pip_value_jpy / entry_price
    value_per_pip = pip_value_jpy / entry_price
    
    # Line 939-942: optimal_lots calculation
    if pip_risk > 0 and value_per_pip > 0:
        optimal_lots = risk_val / (pip_risk * value_per_pip)
    else:
        return 0
    
    # Line 945: optimal_lots = max(0.01, round(optimal_lots, 2))
    optimal_lots = max(0.01, round(optimal_lots, 2))
    
    # Line 948: real_contracts = int(optimal_lots * self.p.contract_size)
    real_contracts = int(optimal_lots * lot_size)
    
    # Line 951: bt_size = int(real_contracts / self.p.jpy_rate)
    bt_size = int(real_contracts / jpy_rate)
    
    return max(100, bt_size)


# =============================================================================
# PAIR TYPE DETECTION
# =============================================================================

JPY_PAIRS = [
    'EURJPY', 'USDJPY', 'GBPJPY', 'AUDJPY', 'NZDJPY',
    'CADJPY', 'CHFJPY',
]

ETF_SYMBOLS = [
    'DIA', 'TLT', 'GLD', 'SPY', 'QQQ', 'IWM',
    'XLE', 'EWZ', 'XLU', 'SLV',
]


def get_pair_type(asset_name: str) -> str:
    """Determine pair type from asset name."""
    asset_upper = asset_name.upper()
    
    if asset_upper in ETF_SYMBOLS:
        return 'ETF'
    elif asset_upper in JPY_PAIRS or asset_upper.endswith('JPY'):
        return 'JPY'
    else:
        return 'STANDARD'


def _calculate_etf_position(
    entry_price: float,
    stop_loss: float,
    equity: float,
    risk_percent: float,
    margin_pct: float = 20.0,
) -> int:
    """
    Position sizing for ETFs (DIA, TLT, GLD, etc.)
    
    ETF position sizing:
    - Calculate shares based on risk amount / price risk
    - Apply margin constraint (20% for Darwinex Zero)
    - Return integer shares (minimum 1)
    """
    price_risk = abs(entry_price - stop_loss)
    
    if price_risk <= 0:
        return 0
    
    risk_amount = equity * risk_percent
    
    # shares = risk_amount / price_risk
    shares = risk_amount / price_risk
    
    # Margin check: shares * price * margin_pct <= equity
    max_shares = equity / (entry_price * (margin_pct / 100.0))
    shares = min(shares, max_shares)
    
    return int(max(1, shares))  # At least 1 share


def get_pip_value(asset_name: str) -> float:
    """Get pip value for a given asset."""
    pair_type = get_pair_type(asset_name)
    return 0.01 if pair_type == 'JPY' else 0.0001