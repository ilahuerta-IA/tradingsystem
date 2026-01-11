"""
Commission schemes for different brokers and instrument types.
Supports both JPY and Standard pairs with proper P&L calculation.
"""
import backtrader as bt


class DarwinexZeroCommission(bt.CommInfoBase):
    """
    Commission scheme for Darwinex Zero.
    
    For JPY pairs:
    - Position size is divided by jpy_rate (~150) for margin management
    - P&L must be multiplied back by jpy_rate to compensate
    - This matches the original sunrise_ogle_eurjpy_pro.py implementation
    
    Darwinex Zero specs:
    - Commission: $2.50 per lot per order
    - Spread: Variable per instrument (in price)
    - Margin: 3.33% (30:1 leverage)
    """
    params = (
        ('stocklike', False),
        ('commtype', bt.CommInfoBase.COMM_FIXED),
        ('percabs', True),
        ('leverage', 500.0),
        ('automargin', True),
        ('commission', 2.50),
        ('lot_size', 100000),
        ('is_jpy_pair', False),
        ('jpy_rate', 150.0),
    )
    
    # Debug counters (class-level)
    commission_calls = 0
    total_commission = 0.0
    total_lots = 0.0

    def _getcommission(self, size, price, pseudoexec):
        """
        Return commission based on lot size.
        
        JPY PAIRS: size was divided by jpy_rate (~150) for P&L calculation,
        but commission must be based on ACTUAL lot size, so we restore it.
        """
        # For JPY pairs: restore actual size before calculating lots
        actual_size = abs(size)
        if self.p.is_jpy_pair:
            actual_size = actual_size * self.p.jpy_rate  # Restore real size
        
        lots = actual_size / self.p.lot_size
        comm = lots * self.p.commission
        
        if not pseudoexec:
            DarwinexZeroCommission.commission_calls += 1
            DarwinexZeroCommission.total_commission += comm
            DarwinexZeroCommission.total_lots += lots
        
        return comm

    def profitandloss(self, size, price, newprice):
        """
        Calculate P&L in USD from JPY-denominated gains/losses.
        
        CRITICAL: Since bt_size is divided by ~150 for margin management,
        we multiply P&L by 150 to compensate and get correct USD P&L.
        
        This is an EXACT replica of the original ForexCommission class
        from sunrise_ogle_eurjpy_pro.py (lines 235-248).
        """
        if self.p.is_jpy_pair:
            # JPY pairs: compensate for size division
            pnl_jpy = size * self.p.jpy_rate * (newprice - price)
            if newprice > 0:
                pnl_usd = pnl_jpy / newprice
                return pnl_usd
            return pnl_jpy
        else:
            # Standard pairs: direct USD P&L
            return size * (newprice - price)

    def cashadjust(self, size, price, newprice):
        """Adjust cash for non-stocklike instruments (forex)."""
        if not self._stocklike:
            if self.p.is_jpy_pair:
                # Same compensation for cash adjustment
                pnl_jpy = size * self.p.jpy_rate * (newprice - price)
                if newprice > 0:
                    return pnl_jpy / newprice
                return pnl_jpy
            else:
                return size * (newprice - price)
        return 0.0

# Alias for backward compatibility
ForexCommission = DarwinexZeroCommission


# =============================================================================
# ETF COMMISSION CLASS - Darwinex Zero ($0.02/contract/order)
# =============================================================================
class ETFCommission(bt.CommInfoBase):
    """
    Generic commission scheme for ETF trading (DIA, TLT, GLD, etc.).
    Darwinex Zero specs:
    - Commission: $0.02 per contract per order
    - Margin: 20% (5:1 leverage)
    - Contract size: 1 share
    """
    params = (
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_FIXED),
        ('percabs', True),
        ('leverage', 5.0),
        ('automargin', True),
        ('commission', 0.02),
        ('margin_pct', 20.0),
    )
    
    # Debug counters (class-level)
    commission_calls = 0
    total_commission = 0.0
    total_contracts = 0.0

    def _getcommission(self, size, price, pseudoexec):
        """Return commission based on contract count ($0.02/contract)."""
        contracts = abs(size)
        comm = contracts * self.p.commission
        
        if not pseudoexec:
            ETFCommission.commission_calls += 1
            ETFCommission.total_commission += comm
            ETFCommission.total_contracts += contracts
        
        return comm

    def get_margin(self, price):
        """Return margin requirement per contract."""
        return price * (self.p.margin_pct / 100.0)


# =============================================================================
# ETF CSV DATA FEED - Fixes Date/Time separate columns issue
# =============================================================================
class ETFCSVData(bt.feeds.GenericCSVData):
    """
    Custom CSV Data Feed for ETFs that correctly handles separate Date and Time columns.
    
    The standard GenericCSVData doesn't properly combine datetime when Date and Time
    are in separate columns (always shows 23:59:59). This class fixes that by
    overriding the _loadline method to properly parse and combine the columns.
    
    CSV Format expected:
        Date,Time,Open,High,Low,Close,Volume
        20200102,14:30:00,286.30,286.70,286.30,286.56,670000
    
    NOTE: Date filtering is handled by Backtrader internally, NOT in _loadline.
    This ensures warmup bars are available for indicators.
    """
    from datetime import datetime as _datetime
    
    def _loadline(self, linetokens):
        # Parse Date (column 0) and Time (column 1) 
        dt_str = linetokens[0]  # '20200102'
        tm_str = linetokens[1]  # '14:30:00'
        
        # Combine into datetime
        try:
            dt = self._datetime.strptime(f"{dt_str} {tm_str}", '%Y%m%d %H:%M:%S')
        except ValueError:
            return False
        
        # Set datetime as float (matplotlib date number)
        # Let Backtrader handle fromdate/todate filtering internally
        self.lines.datetime[0] = bt.date2num(dt)
        
        # Set OHLCV
        self.lines.open[0] = float(linetokens[2])
        self.lines.high[0] = float(linetokens[3])
        self.lines.low[0] = float(linetokens[4])
        self.lines.close[0] = float(linetokens[5])
        self.lines.volume[0] = float(linetokens[6])
        self.lines.openinterest[0] = 0.0
        
        return True