"""
Custom observers for trading strategies.
Observers are plotted on the main chart and can access strategy data.
"""
import backtrader as bt


class SEObserver(bt.Observer):
    """
    Spectral Entropy Observer - plots HTF SE value on 5m chart.
    
    This observer reads the SE value from the strategy's htf_se indicator
    and plots it as a line in its own subplot.
    
    Usage:
        cerebro.addobserver(SEObserver)
    """
    lines = ('se',)
    
    plotinfo = dict(
        plot=True,
        subplot=True,
        plotname='SE (HTF)',
        plotlinelabels=True,
    )
    plotlines = dict(
        se=dict(color='cyan', linewidth=1.5),
    )
    
    def next(self):
        # Access the strategy (owner of this observer)
        strat = self._owner
        se_val = float('nan')
        
        if hasattr(strat, 'htf_se') and strat.htf_se is not None:
            try:
                se_val = float(strat.htf_se.lines.se[0])
            except:
                pass
        
        self.lines.se[0] = se_val
