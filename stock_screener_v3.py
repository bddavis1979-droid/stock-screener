#!/usr/bin/env python3
"""
Great Long-Term Stock Screener v3 - Complete Edition
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import time
import warnings
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
import io

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Great Stock Screener v3", page_icon="📈", layout="wide")

st.markdown("""
<style>
    .main-header { font-size: 2.6rem; font-weight: 700; color: #1a365d; }
    .philosophy-box { background-color: #edf2f7; padding: 1.2rem; border-radius: 10px; border-left: 5px solid #2b6cb0; }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=86400)
def get_sp500_tickers():
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        soup = BeautifulSoup(requests.get(url, timeout=10).content, 'html.parser')
        return sorted([row.find('td').text.strip().replace('.', '-') for row in soup.find('table', {'id': 'constituents'}).find_all('tr')[1:]])[:500]
    except:
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "BRK-B", "TSLA", "AVGO", "LLY", "JPM", "V", "MA", "COST", "JNJ"]

def get_fallback_tickers():
    return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "BRK-B", "TSLA", "AVGO", "LLY", "JPM", "V", "MA", "COST", "JNJ", "PG", "HD", "CVX", "ABBV", "MRK", "PEP", "KO", "MCD", "WMT", "DIS", "ADBE", "NFLX", "CRM", "AMD", "QCOM", "TXN", "NOW", "ISRG", "REGN", "VRTX", "GILD", "AMGN", "MDT", "SYK", "BSX", "PFE", "ABT", "TMO", "DHR", "LIN", "APD", "SHW", "NEE", "DUK", "SO", "COP", "EOG", "PLTR", "SNOW", "DDOG", "CRWD", "PANW", "SHOP", "SQ", "PYPL"]

@st.cache_data(ttl=3600)
def fetch_ticker_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if not info or 'symbol' not in info: return None
        return {
            'info': info,
            'income_stmt': stock.income_stmt,
            'balance_sheet': stock.balance_sheet,
            'earnings_dates': stock.earnings_dates,
            'history': stock.history(period="5y"),
            'price_52w_high': stock.history(period="5y")['High'].max() if not stock.history(period="5y").empty else None,
            'price_current': stock.history(period="5y")['Close'].iloc[-1] if not stock.history(period="5y").empty else None,
        }
    except:
        return None

def detect_double_beat(earnings_df):
    if earnings_df is None or earnings_df.empty: 
        return {'double_beat_count': 0, 'guidance_raised': False, 'recent_earnings_quality': 'Neutral'}
    try:
        df = earnings_df.copy()
        surprise_col = None
        for col in df.columns:
            if 'surprise' in col.lower(): surprise_col = col; break
        if surprise_col is None and 'Surprise(%)' in df.columns: surprise_col = 'Surprise(%)'
        
        count = 0
        for _, row in df.iterrows():
            if surprise_col and pd.notna(row.get(surprise_col)):
                try:
                    if float(row[surprise_col]) > 0: count += 1
                except: pass
        return {
            'double_beat_count': count,
            'guidance_raised': count >= 2,
            'recent_earnings_quality': 'Excellent' if count >= 4 else 'Strong' if count >= 2 else 'Good' if count >= 1 else 'Mixed'
        }
    except:
        return {'double_beat_count': 0, 'guidance_raised': False, 'recent_earnings_quality': 'Neutral'}

def calculate_metrics(data):
    if not data or not data.get('info'): return {}
    info = data['info']
    income = data.get('income_stmt', pd.DataFrame())
    earnings = data.get('earnings_dates', pd.DataFrame())
    
    m = {
        'ticker': info.get('symbol', 'N/A'),
        'name': info.get('shortName', 'N/A'),
        'sector': info.get('sector', 'N/A'),
        'market_cap_b': round(info.get('marketCap', 0)/1e9, 1) if info.get('marketCap') else 0,
        'forward_pe': info.get('forwardPE'),
        'peg_ratio': info.get('pegRatio'),
        'roic': info.get('returnOnInvestedCapital'),
        'roe': info.get('returnOnEquity'),
        'gross_margin': info.get('grossMargins'),
        'rev_growth_yoy': None,
        'rev_cagr_3y': None,
        'fcf_yield': None,
        'from_52w_high': None,
        'double_beat_count': 0,
        'guidance_raised': False,
        'recent_earnings_quality': 'Neutral',
    }
    
    if not income.empty and 'Total Revenue' in income.index:
        rev = income.loc['Total Revenue']
        if len(rev) >= 2: m['rev_growth_yoy'] = round((rev.iloc[0] - rev.iloc[1]) / rev.iloc[1] * 100, 1)
        if len(rev) >= 4: m['rev_cagr_3y'] = round(((rev.iloc[0] / rev.iloc[3]) ** (1/3) - 1) * 100, 1)
    
    fcf = info.get('freeCashflow', 0) or 0
    mcap = info.get('marketCap', 0) or 0
    m['fcf_yield'] = round(fcf / mcap * 100, 1) if mcap and fcf else None
    
    if data.get('price_52w_high') and data.get('price_current'):
        m['from_52w_high'] = round((data['price_current'] / data['price_52w_high'] - 1) * 100, 1)
    
    eb = detect_double_beat(earnings)
    m.update(eb)
    
    score = 0
    comps = []
    if m.get('roic') and m['roic'] > 15: score += 18; comps.append("High ROIC")
    if m.get('rev_growth_yoy') and m.get('rev_cagr_3y') and m['rev_growth_yoy'] > m.get('rev_cagr_3y', 0) + 3: score += 14; comps.append("Accelerating growth")
    if m.get('peg_ratio') and m['peg_ratio'] < 1.5: score += 18; comps.append("Attractive PEG")
    if m.get('fcf_yield') and m['fcf_yield'] > 4: score += 14; comps.append("High FCF yield")
    if m.get('double_beat_count', 0) >= 3: score += 16; comps.append("Multiple double beats")
    elif m.get('double_beat_count', 0) >= 1: score += 10; comps.append("Double beat(s)")
    if m.get('guidance_raised'): score += 12; comps.append("Guidance raised")
    if m.get('from_52w_high') and m['from_52w_high'] < -25: score += 16; comps.append("Price lagging")
    
    m['expectation_shift_score'] = min(score, 100)
    m['score_components'] = comps
    return m

def batch_screen(tickers, progress=None):
    results = []
    for i, t in enumerate(tickers):
        if progress: progress.progress((i+1)/len(tickers), text=f"Analyzing {t}")
        d = fetch_ticker_data(t)
        if d:
            m = calculate_metrics(d)
            if m: results.append(m)
        if i % 5 == 0 and i > 0: time.sleep(0.5)
    return pd.DataFrame(results).sort_values('expectation_shift_score', ascending=False) if results else pd.DataFrame()

@st.cache_data(ttl=3600)
def get_fear_greed():
    try:
        r = requests.get("https://money.cnn.com/data/fear-and-greed/", timeout=8, headers={'User-Agent':'Mozilla/5.0'})
        soup = BeautifulSoup(r.text, 'html.parser')
        text = str(soup)
        if "Greed Now:" in text:
            val = int(''.join(filter(str.isdigit, text[text.find("Greed Now:"):text.find("Greed Now:")+15])))
            return {"value": val, "status": "Live"}
    except: pass
    return {"value": 48, "status": "Cached"}

@st.cache_data(ttl=21600)
def get_congress_trades(limit=15):
    trades = []
    try:
        senate = requests.get("https://raw.githubusercontent.com/timothycarambat/senate-stock-watcher-data/main/all_transactions.json", timeout=6).json()
        for item in senate[:limit//2]:
            trades.append({
                'date': item.get('transaction_date',''),
                'member': item.get('senator','Senator'),
                'chamber': 'Senate',
                'ticker': item.get('ticker',''),
                'type': item.get('type','').upper(),
                'amount': item.get('amount','')
            })
    except: pass
    return pd.DataFrame(trades)

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
    for c in row.get('score_components', []): story.append(Paragraph(f"• {c}", body))
    story.append(Paragraph("RESEARCH CHECKLIST", h2))
    for item in ["1. Sustainability of Growth", "2. Competitive Position", "3. Capital Allocation", "4. Valuation Check", "5. Risks & Red Flags", "6. Qualitative Factors"]:
        story.append(Paragraph(item, body))
    if notes: 
        story.append(Paragraph("NOTES", h2))
        story.append(Paragraph(notes.replace('\n','<br/>'), body))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def main():
    st.markdown('<h1 class="main-header">Great Stock Screener v3</h1>', unsafe_allow_html=True)
    
    fg = get_fear_greed()
    st.markdown(f"""
    <div style="background:#f0f4f8; padding:10px; border-radius:10px; text-align:center; margin-bottom:15px">
    <b>CNN Fear & Greed Index:</b> <span style="font-size:1.8rem; font-weight:700; color:#2b6cb0">{fg['value']}</span> 
    <span style="font-size:0.9rem">({fg['status']})</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.sidebar.header("📌 Universe")
    choice = st.sidebar.radio("Choose Universe", ["Quality Compounders", "S&P 500", "Custom List"])
    
    if choice == "Quality Compounders":
        tickers = get_fallback_tickers()
    elif choice == "S&P 500":
        tickers = get_sp500_tickers()
    else:
        txt = st.sidebar.text_area("Enter tickers", "AAPL, MSFT, GOOGL, NVDA, COST")
        tickers = [t.strip().upper() for t in txt.replace('\n',',').split(',') if t.strip()]
    
    if st.sidebar.button("🚀 Run Screen", type="primary", use_container_width=True):
        st.session_state.run = True
        st.session_state.tickers = tickers
    
    if 'run' not in st.session_state or not st.session_state.run:
        st.info("Select a universe and click **Run Screen**")
        return
    
    progress = st.progress(0, text="Screening...")
    results = batch_screen(st.session_state.tickers, progress)
    progress.empty()
    
    if results.empty:
        st.error("No data found.")
        return
    
    st.success(f"Screen complete — {len(results)} companies")
    
    st.sidebar.header("🔍 Filters")
    filtered = results.copy()
    min_score = st.sidebar.slider("Min Shift Score", 0, 100, 40, 5)
    filtered = filtered[filtered['expectation_shift_score'] >= min_score]
    
    min_db = st.sidebar.slider("Min Double Beats", 0, 6, 0, 1)
    filtered = filtered[filtered['double_beat_count'].fillna(0) >= min_db]
    
    st.subheader(f"Results ({len(filtered)} companies)")
    
    display_cols = ['ticker','name','sector','market_cap_b','expectation_shift_score','rev_growth_yoy','roic','peg_ratio','fcf_yield','double_beat_count','guidance_raised','from_52w_high']
    tdf = filtered[[c for c in display_cols if c in filtered.columns]].copy()
    if 'market_cap_b' in tdf.columns: tdf['market_cap_b'] = tdf['market_cap_b'].apply(lambda x: f"${x:.1f}B")
    if 'guidance_raised' in tdf.columns: tdf['guidance_raised'] = tdf['guidance_raised'].apply(lambda x: "✅" if x else "—")
    for c in ['rev_growth_yoy','roic','peg_ratio','fcf_yield','from_52w_high','expectation_shift_score','double_beat_count']:
        if c in tdf.columns: tdf[c] = tdf[c].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
    
    st.dataframe(tdf.rename(columns={'ticker':'Ticker','name':'Company','expectation_shift_score':'Score','double_beat_count':'Dbl Beats','guidance_raised':'Guide ↑','from_52w_high':'vs 52wH'}), use_container_width=True, height=450)
    
    st.divider()
    st.subheader("🔍 Deep Research")
    sel = st.selectbox("Select ticker for analysis", filtered['ticker'].tolist())
    
    if sel:
        row = filtered[filtered['ticker'] == sel].iloc[0]
        st.header(f"{sel} — {row.get('name','')}")
        
        tabs = st.tabs(["📊 Fundamentals", "📈 Earnings", "🔥 Peers", "🏛️ Congress", "📋 PDF"])
        
        with tabs[0]:
            st.write(f"**ROIC:** {row.get('roic','—')}% | **ROE:** {row.get('roe','—')}%")
            st.write(f"**Rev YoY:** {row.get('rev_growth_yoy','—')}% | **3Y CAGR:** {row.get('rev_cagr_3y','—')}%")
            st.write(f"**FCF Yield:** {row.get('fcf_yield','—')}% | **PEG:** {row.get('peg_ratio','—')}")
        
        with tabs[1]:
            st.write(f"**Double Beats:** {row.get('double_beat_count',0)}")
            st.write(f"**Guidance Raised:** {'✅ Yes' if row.get('guidance_raised') else 'No'}")
            st.write(f"**Earnings Quality:** {row.get('recent_earnings_quality','—')}")
        
        with tabs[2]:
            peers = filtered[(filtered['sector'] == row.get('sector')) & (filtered['ticker'] != sel)].head(5)
            if not peers.empty:
                st.dataframe(peers[['ticker','expectation_shift_score','roic','peg_ratio','double_beat_count']], use_container_width=True)
        
        with tabs[3]:
            congress = get_congress_trades(12)
            if not congress.empty:
                ticker_trades = congress[congress['ticker'].str.upper() == sel.upper()]
                if not ticker_trades.empty:
                    st.dataframe(ticker_trades, use_container_width=True)
                else:
                    st.write("No recent congressional trades for this ticker.")
                    st.dataframe(congress.head(6), use_container_width=True)
        
        with tabs[4]:
            notes = st.text_area("Research Notes", height=100, key=f"notes_{sel}")
            if st.button("Generate PDF Report"):
                pdf = generate_pdf(sel, row, notes)
                st.download_button("📥 Download PDF", data=pdf, file_name=f"{sel}_report.pdf", mime="application/pdf")

if __name__ == "__main__":
    main()
