"""
Commission schemes for different broker configurations.
Includes JPY pair P&L correction for accurate backtest results.

Replicates exactly the ForexCommission from sunrise_ogle_eurjpy_pro.py
"""
import backtrader as bt


class ForexCommission(bt.CommInfoBase):
    """
    Commission scheme for Forex pairs with fixed commission per lot.
    Supports both JPY pairs (P&L conversion) and standard pairs.
    
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
        
        lots = actual_size / 100000.0
        comm = lots * self.p.commission
        
        if not pseudoexec:
            ForexCommission.commission_calls += 1
            ForexCommission.total_commission += comm
            ForexCommission.total_lots += lots
        
        return comm

    def profitandloss(self, size, price, newprice):
        """
        Calculate P&L in USD from JPY-denominated gains/losses.
        
        Since bt_size is divided by ~150 for margin management,
        we multiply P&L by 150 to compensate and get correct USD P&L.
        This matches the ERIS strategy approach.
        """
        if self.p.is_jpy_pair:
            # Size was divided by forex_jpy_rate (~150), so we multiply back
            JPY_RATE_COMPENSATION = 150.0
            pnl_jpy = size * JPY_RATE_COMPENSATION * (newprice - price)
            if newprice > 0:
                pnl_usd = pnl_jpy / newprice
                return pnl_usd
            return pnl_jpy
        else:
            # Standard pairs
            return size * (newprice - price)

    def cashadjust(self, size, price, newprice):
        """Adjust cash for non-stocklike instruments (forex)."""
        if not self._stocklike:
            if self.p.is_jpy_pair:
                # Same compensation for cash adjustment
                JPY_RATE_COMPENSATION = 150.0
                pnl_jpy = size * JPY_RATE_COMPENSATION * (newprice - price)
                if newprice > 0:
                    return pnl_jpy / newprice
        return 0.0