#!/usr/bin/env python3
"""
Great Stock Screener v3 - Stable Version
Better handling for Streamlit Cloud + Yahoo Finance
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(page_title="Great Stock Screener v3", page_icon="📈", layout="wide")

st.markdown("<h1 style='color:#1a365d'>Great Stock Screener v3</h1>", unsafe_allow_html=True)

# Fear & Greed
@st.cache_data(ttl=3600)
def get_fear_greed():
    try:
        r = requests.get("https://money.cnn.com/data/fear-and-greed/", timeout=8, headers={'User-Agent':'Mozilla/5.0'})
        if "Greed Now:" in r.text:
            val = int(''.join(filter(str.isdigit, r.text[r.text.find("Greed Now:"):r.text.find("Greed Now:")+15])))
            return val
    except: pass
    return 48

fg = get_fear_greed()
st.info(f"**CNN Fear & Greed Index:** {fg}")

# Small reliable test list
TEST_TICKERS = ["AAPL", "MSFT", "NVDA"]

def fetch_single_ticker(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if not info or 'symbol' not in info:
            return None
        
        m = {
            'ticker': ticker,
            'name': info.get('shortName', ticker),
            'sector': info.get('sector', 'N/A'),
            'market_cap_b': round(info.get('marketCap', 0)/1e9, 1) if info.get('marketCap') else 0,
            'forward_pe': info.get('forwardPE'),
            'peg_ratio': info.get('pegRatio'),
            'roic': info.get('returnOnInvestedCapital'),
            'rev_growth_yoy': None,
            'fcf_yield': None,
            'expectation_shift_score': 0,
        }
        
        # Simple growth calculation
        try:
            income = stock.income_stmt
            if not income.empty and 'Total Revenue' in income.index:
                rev = income.loc['Total Revenue']
                if len(rev) >= 2:
                    m['rev_growth_yoy'] = round((rev.iloc[0] - rev.iloc[1]) / rev.iloc[1] * 100, 1)
        except:
            pass
        
        # FCF Yield
        try:
            fcf = info.get('freeCashflow', 0) or 0
            mcap = info.get('marketCap', 0) or 0
            if mcap and fcf:
                m['fcf_yield'] = round(fcf / mcap * 100, 1)
        except:
            pass
        
        # Simple score
        score = 0
        if m.get('roic') and m['roic'] > 15: score += 25
        if m.get('rev_growth_yoy') and m['rev_growth_yoy'] > 10: score += 20
        if m.get('peg_ratio') and m['peg_ratio'] < 1.8: score += 20
        if m.get('fcf_yield') and m['fcf_yield'] > 3: score += 15
        m['expectation_shift_score'] = min(score, 100)
        
        return m
    except:
        return None

# Main UI
st.sidebar.header("Universe")
mode = st.sidebar.radio("Choose", ["Quick Test (3 stocks)", "Custom List"])

if mode == "Quick Test (3 stocks)":
    tickers = TEST_TICKERS
else:
    txt = st.sidebar.text_area("Tickers", "AAPL, MSFT, NVDA, COST")
    tickers = [t.strip().upper() for t in txt.replace('\n',',').split(',') if t.strip()]

if st.sidebar.button("🚀 Run Screen", type="primary"):
    st.session_state.run = True
    st.session_state.tickers = tickers

if 'run' not in st.session_state or not st.session_state.run:
    st.info("Click **Run Screen** to start")
    st.stop()

# Run with better rate limiting
results = []
progress = st.progress(0)
for i, t in enumerate(st.session_state.tickers):
    progress.progress((i+1)/len(st.session_state.tickers), text=f"Analyzing {t}...")
    data = fetch_single_ticker(t)
    if data:
        results.append(data)
    time.sleep(1.2)  # Important delay

progress.empty()

if not results:
    st.error("Still having trouble getting data. Try again in 10-15 minutes.")
    st.stop()

df = pd.DataFrame(results)
st.success(f"Found {len(df)} stocks")

# Show results
st.dataframe(df[['ticker','name','market_cap_b','expectation_shift_score','rev_growth_yoy','fcf_yield']], use_container_width=True)

st.caption("Note: This is a simplified stable version. Full features will be added back once data source stabilizes.")
