"""One-off: ORION ETF edge check (spread vs ATR14 daily). ASCII only."""
import pandas as pd, pathlib
# spread points -> usd via point = 10^-digits
S = {"SPY":(3,70),"QQQ":(3,180),"IWM":(3,10),"IWF":(2,3),"IVW":(3,10),
     "XLK":(3,40),"XBI":(3,80),"LIT":(3,100),"SIL":(3,120),"GDX":(3,20),
     "GDXJ":(3,10),"GLD":(3,120),"SLV":(3,10),"EEM":(3,10),"FXI":(3,10),
     "EWY":(2,12),"MCHI":(3,10)}
K = 0.1495  # ATR(15m)/ATR(daily) calibration (July)
D = pathlib.Path("data")
need_yf = []
rows = []
for t,(dig,pts) in S.items():
    spread = pts * 10**-dig
    f = D / ("%s_15m_8Yea.csv" % t)
    if not f.exists():
        need_yf.append((t,spread)); continue
    df = pd.read_csv(f, dtype={"Date":str}).tail(3000)
    d = df.groupby("Date").agg(H=("High","max"),L=("Low","min"),C=("Close","last"))
    rows.append((t,spread,d))
if need_yf:
    import yfinance as yf
    for t,spread in need_yf:
        h = yf.download(t, period="3mo", interval="1d", progress=False, auto_adjust=False)
        h.columns = [c[0] if isinstance(c,tuple) else c for c in h.columns]
        d = h.rename(columns={"High":"H","Low":"L","Close":"C"})[["H","L","C"]]
        rows.append((t,spread,d))
print("%-6s %8s %8s %8s %7s %7s" % ("TICKER","PRICE","ATR14d","SPREAD","EDGE","VEREDICTO"))
for t,spread,d in sorted(rows, key=lambda r: r[0]):
    pc = d["C"].shift(1)
    tr = pd.concat([d["H"]-d["L"], (d["H"]-pc).abs(), (d["L"]-pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    price = d["C"].iloc[-1]
    edge = K * atr / spread
    v = "PASS" if edge >= 5 else ("YELLOW" if edge >= 4 else "RED")
    print("%-6s %8.2f %8.3f %8.3f %7.1f %7s" % (t, price, atr, spread, edge, v))
