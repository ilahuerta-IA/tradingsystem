"""
Technical indicators for trading strategies.
All indicators follow Backtrader conventions.

Note: Angle calculation is done inline in strategy using EMA confirm (period 1).
This matches the original sunrise_ogle_eurjpy_pro.py implementation.
"""


# No custom indicators needed - angle is calculated inline in strategy
# using the _angle() method which uses EMA confirm period 1.
# This file is kept for future indicator additions if needed.