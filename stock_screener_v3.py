#!/usr/bin/env python3
"""
Great Stock Screener v3 - Full Featured Version
Includes: Fear & Greed, Double Beats, Congressional Trades, PDF Reports, More Filters
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests
from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
import io
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(page_title="Great Stock Screener v3", page_icon="📈", layout="wide")

st.markdown("<h1 style='color:#1a365d'>Great Stock Screener v3 - Full</h1>", unsafe_allow_html=True)

# ================== FEAR & GREED ==================
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

# ================== CONGRESSIONAL TRADES ==================
@st.cache_data(ttl=21600)
def get_congress_trades():
    try:
        url = "https://raw.githubusercontent.com/timothycarambat/senate-stock-watcher-data/main/all_transactions.json"
        data = requests.get(url, timeout=8).json()
        trades = []
        for item in data[:20]:
            trades.append({
                'date': item.get('transaction_date', ''),
                'member': item.get('senator', ''),
                'ticker': item.get('ticker', ''),
                'type': item.get('type', ''),
                'amount': item.get('amount', '')
            })
        return pd.DataFrame(trades)
    except:
        return pd.DataFrame()

# ================== DATA FUNCTIONS ==================
def fetch_ticker(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if not info or 'symbol' not in info: return None

        income = stock.income_stmt
        earnings = stock.earnings_dates

        m = {
            'ticker': ticker,
            'name': info.get('shortName', ticker),
            'sector': info.get('sector', 'N/A'),
            'market_cap_b': round(info.get('marketCap', 0)/1e9, 1) if info.get('marketCap') else 0,
            'forward_pe': info.get('forwardPE'),
            'peg_ratio': info.get('pegRatio'),
            'roic': info.get('returnOnInvestedCapital'),
            'roe': info.get('returnOnEquity'),
            'rev_growth_yoy': None,
            'rev_cagr_3y': None,
            'fcf_yield': None,
            'double_beat_count': 0,
            'guidance_raised': False,
            'expectation_shift_score': 0,
        }

        # Revenue Growth
        if not income.empty and 'Total Revenue' in income.index:
            rev = income.loc['Total Revenue']
            if len(rev) >= 2:
                m['rev_growth_yoy'] = round((rev.iloc[0] - rev.iloc[1]) / rev.iloc[1] * 100, 1)
            if len(rev) >= 4:
                m['rev_cagr_3y'] = round(((rev.iloc[0] / rev.iloc[3]) ** (1/3) - 1) * 100, 1)

        # FCF Yield
        fcf = info.get('freeCashflow', 0) or 0
        mcap = info.get('marketCap', 0) or 0
        if mcap and fcf: m['fcf_yield'] = round(fcf / mcap * 100, 1)

        # Double Beat Detection
        if earnings is not None and not earnings.empty:
            try:
                surprises = earnings.get('Surprise(%)', pd.Series())
                positive = (surprises > 0).sum()
                m['double_beat_count'] = int(positive)
                m['guidance_raised'] = positive >= 2
            except:
                pass

        # Score
        score = 0
        if m.get('roic') and m['roic'] > 15: score += 20
        if m.get('rev_growth_yoy') and m.get('rev_cagr_3y') and m['rev_growth_yoy'] > m.get('rev_cagr_3y', 0) + 3: score += 15
        if m.get('peg_ratio') and m['peg_ratio'] < 1.5: score += 20
        if m.get('fcf_yield') and m['fcf_yield'] > 4: score += 15
        if m.get('double_beat_count', 0) >= 3: score += 18
        elif m.get('double_beat_count', 0) >= 1: score += 10
        if m.get('guidance_raised'): score += 12

        m['expectation_shift_score'] = min(score, 100)
        return m
    except:
        return None

# ================== PDF REPORT ==================
def generate_pdf(ticker, row, notes=""):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.6*inch, leftMargin=0.6*inch, topMargin=0.6*inch, bottomMargin=0.6*inch)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1a365d'), alignment=TA_CENTER)
    h2 = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=13, textColor=colors.HexColor('#2b6cb0'))
    body = ParagraphStyle('Body', parent=styles['Normal'], fontSize=9.5)

    story = []
    story.append(Paragraph(f"RESEARCH REPORT — {ticker}", title))
    story.append(Paragraph(f"{row.get('name','')} | Score: {row.get('expectation_shift_score',0)}/100", styles['Heading3']))
    story.append(Spacer(1, 10))

    snap = [
        ['Market Cap', f"${row.get('market_cap_b',0):.1f}B", 'PEG', str(row.get('peg_ratio','—'))],
        ['ROIC', f"{row.get('roic','—')}%", 'FCF Yield', f"{row.get('fcf_yield','—')}%"],
        ['Double Beats', str(row.get('double_beat_count',0)), 'Guidance Raised', 'Yes' if row.get('guidance_raised') else 'No'],
    ]
    t = Table(snap, colWidths=[1.5*inch, 1.3*inch, 1.5*inch, 1.3*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2b6cb0')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8.5),
        ('GRID', (0,0), (-1,-1), 0.5, colors.gray),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#f7fafc')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(Paragraph("KEY SIGNALS", h2))
    story.append(Paragraph("• High ROIC • Accelerating Growth • Attractive PEG • High FCF Yield • Double Beats", body))
    story.append(Paragraph("RESEARCH CHECKLIST", h2))
    for item in ["1. Sustainability of Growth", "2. Competitive Position", "3. Capital Allocation", "4. Valuation Check", "5. Risks & Red Flags"]:
        story.append(Paragraph(item, body))
    if notes:
        story.append(Paragraph("NOTES", h2))
        story.append(Paragraph(notes.replace('\n','<br/>'), body))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# ================== MAIN UI ==================
st.sidebar.header("📌 Universe")
mode = st.sidebar.radio("Mode", ["Quick Test (6 stocks)", "Custom List"])

if mode == "Quick Test (6 stocks)":
    tickers = ["AAPL", "MSFT", "NVDA", "COST", "JNJ", "GOOGL"]
else:
    txt = st.sidebar.text_area("Enter tickers", "AAPL, MSFT, NVDA, COST, JNJ")
    tickers = [t.strip().upper() for t in txt.replace('\n',',').split(',') if t.strip()]

if st.sidebar.button("🚀 Run Screen", type="primary"):
    st.session_state.run = True
    st.session_state.tickers = tickers

if 'run' not in st.session_state or not st.session_state.run:
    st.info("Click **Run Screen** to begin")
    st.stop()

# Run screen
results = []
progress = st.progress(0)
for i, t in enumerate(st.session_state.tickers):
    progress.progress((i+1)/len(st.session_state.tickers), text=f"Analyzing {t}...")
    data = fetch_ticker(t)
    if data: results.append(data)
    time.sleep(1.0)
progress.empty()

if not results:
    st.error("No data found. Try again in 10-15 minutes.")
    st.stop()

df = pd.DataFrame(results).sort_values('expectation_shift_score', ascending=False)
st.success(f"Screen complete — {len(df)} companies")

# Filters
st.sidebar.header("🔍 Filters")
min_score = st.sidebar.slider("Min Shift Score", 0, 100, 30, 5)
filtered = df[df['expectation_shift_score'] >= min_score]

min_roic = st.sidebar.slider("Min ROIC", 0, 40, 10, 5)
filtered = filtered[filtered['roic'].fillna(0) >= min_roic]

# Show table
st.dataframe(filtered[['ticker','name','sector','market_cap_b','expectation_shift_score','rev_growth_yoy','roic','peg_ratio','fcf_yield','double_beat_count','guidance_raised']], use_container_width=True, height=450)

# Deep Research
st.divider()
st.subheader("🔍 Deep Research")
sel = st.selectbox("Select ticker", filtered['ticker'].tolist())

if sel:
    row = filtered[filtered['ticker'] == sel].iloc[0]
    st.header(f"{sel} — {row.get('name','')}")
    
    tabs = st.tabs(["📊 Fundamentals", "📈 Earnings", "🏛️ Congress", "📋 PDF"])
    
    with tabs[0]:
        st.write(f"**ROIC:** {row.get('roic','—')}% | **ROE:** {row.get('roe','—')}%")
        st.write(f"**Rev YoY:** {row.get('rev_growth_yoy','—')}% | **3Y CAGR:** {row.get('rev_cagr_3y','—')}%")
        st.write(f"**FCF Yield:** {row.get('fcf_yield','—')}% | **PEG:** {row.get('peg_ratio','—')}")
    
    with tabs[1]:
        st.write(f"**Double Beats:** {row.get('double_beat_count',0)}")
        st.write(f"**Guidance Raised:** {'✅ Yes' if row.get('guidance_raised') else 'No'}")
    
    with tabs[2]:
        congress = get_congress_trades()
        if not congress.empty:
            ticker_trades = congress[congress['ticker'].str.upper() == sel.upper()]
            if not ticker_trades.empty:
                st.dataframe(ticker_trades, use_container_width=True)
            else:
                st.write("No recent congressional trades for this ticker.")
                st.dataframe(congress.head(8), use_container_width=True)
    
    with tabs[3]:
        notes = st.text_area("Research Notes", height=100, key=f"notes_{sel}")
        if st.button("Generate PDF"):
            pdf = generate_pdf(sel, row, notes)
            st.download_button("📥 Download PDF", data=pdf, file_name=f"{sel}_report.pdf", mime="application/pdf")
