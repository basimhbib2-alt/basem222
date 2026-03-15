
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.signal import argrelextrema
from datetime import datetime, timedelta

# --- إعداد الصفحة ---
st.set_page_config(page_title="محلل موجات الولفي - السوق السعودي", layout="wide")
st.title("🐺 محلل موجات الولفي الصاعد (Wolfe Wave)")
st.markdown("""
هذا التطبيق يقوم بتحليل الأسهم السعودية بناءً على قواعد موجة الولفي الصاعد.
يتم استخدام **زقزاق 5** لتحديد القمم والقيعان.
""")

# --- قائمة ببعض الأسهم السعودية للفحص (عينة) ---
# يمكنك إضافة المزيد من الرموز هنا
SAUDI_STOCKS = {
    "1120.SR": "الراجحي",
    "2222.SR": "أرامكو",
    "2010.SR": "سابك",
    "1180.SR": "الأهلي",
    "7010.SR": "STC",
    "1150.SR": "الإنماء",
    "1010.SR": "الرياض",
    "2350.SR": "كيان",
    "4280.SR": "المملكة",
    "5110.SR": "كهرباء السعودية",
    "4030.SR": "البحري",
    "2280.SR": "المراعي"
}

# --- دوال التحليل الفني ---

def get_data(ticker, period='1y', interval='1d'):
    """جلب بيانات السهم"""
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty:
            return None
        # تنظيف البيانات في حال كانت MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df['Date'] = df.index
        return df
    except Exception as e:
        return None

def get_zigzag_pivots(df, order=5):
    """
    تحديد القمم والقيعان (ZigZag)
    order=5 يعني مقارنة الشمعة بـ 5 شمعات قبلها و 5 بعدها لتأكيد القمة/القاع
    """
    df['min'] = df.iloc[argrelextrema(df['Low'].values, np.less_equal, order=order)[0]]['Low']
    df['max'] = df.iloc[argrelextrema(df['High'].values, np.greater_equal, order=order)[0]]['High']
    
    pivots = []
    # تجميع النقاط في قائمة واحدة مرتبة زمنياً
    for i, row in df.iterrows():
        if not np.isnan(row['min']):
            pivots.append({'date': i, 'price': row['min'], 'type': 'low', 'idx': df.index.get_loc(i)})
        if not np.isnan(row['max']):
            pivots.append({'date': i, 'price': row['max'], 'type': 'high', 'idx': df.index.get_loc(i)})
    
    # تنظيف التكرار (مثلاً قمتين متتاليتين نأخذ الأعلى، قاعين متتاليين نأخذ الأدنى)
    clean_pivots = []
    if not pivots:
        return []
        
    clean_pivots.append(pivots[0])
    for p in pivots[1:]:
        last_p = clean_pivots[-1]
        if p['type'] == last_p['type']:
            # إذا تكرر النوع، نحدث السعر للأفضل
            if p['type'] == 'high':
                if p['price'] > last_p['price']:
                    clean_pivots[-1] = p
            else: # low
                if p['price'] < last_p['price']:
                    clean_pivots[-1] = p
        else:
            clean_pivots.append(p)
            
    return clean_pivots

def check_wolfe_wave(pivots):
    """
    فحص شروط موجة الولفي الصاعد
    نحتاج آخر 5 نقاط (قاع - قمة - قاع - قمة - قاع)
    """
    if len(pivots) < 5:
        return False, None

    # نأخذ آخر 5 نقاط
    # الترتيب في القائمة: [P1, P2, P3, P4, P5]
    # النمط الصاعد يجب أن ينتهي بقاع (P5)
    # التسلسل المطلوب: Low (1) -> High (2) -> Low (3) -> High (4) -> Low (5)
    
    subset = pivots[-5:]
    
    # التأكد من ترتيب الأنواع
    if not (subset[0]['type'] == 'low' and subset[1]['type'] == 'high' and 
            subset[2]['type'] == 'low' and subset[3]['type'] == 'high' and 
            subset[4]['type'] == 'low'):
        return False, None

    p1 = subset[0]
    p2 = subset[1]
    p3 = subset[2]
    p4 = subset[3]
    p5 = subset[4]

    # --- تطبيق القواعد المذكورة في الصورة ---
    
    # 1. القاع الثالث (P3) أقل من القاع الأول (P1)
    rule1 = p3['price'] < p1['price']
    
    # 2. القمة الثانية (P4) أقل من القمة الأولى (P2)
    rule2 = p4['price'] < p2['price']
    
    # 3. القمة الثانية (P4) أعلى من القاع الأول (P1) لضمان التداخل
    rule3 = p4['price'] > p1['price'] 
    
    # 4. القاع الخامس (P5) هو أقل القيعان (أقل من P3 وبالتالي أقل من P1)
    rule4 = p5['price'] < p3['price']

    # يمكنك إضافة شروط إضافية للتماثل إذا رغبت، لكن هذه هي القواعد الأساسية
    
    if rule1 and rule2 and rule3 and rule4:
        return True, subset
    
    return False, None

def plot_wolfe(df, pivots, ticker_name):
    """رسم الشارت مع الموجة"""
    fig = go.Figure(data=[go.Candlestick(x=df.index,
                open=df['Open'], high=df['High'],
                low=df['Low'], close=df['Close'], name='السعر')])

    # رسم خطوط الزقزاق للمساعدة في الرؤية
    zz_dates = [p['date'] for p in pivots]
    zz_prices = [p['price'] for p in pivots]
    fig.add_trace(go.Scatter(x=zz_dates, y=zz_prices, mode='lines', 
                             line=dict(color='gray', width=1, dash='dot'), name='ZigZag'))

    # استخراج نقاط الولفي
    is_wolfe, wave_points = check_wolfe_wave(pivots)
    
    if is_wolfe:
        p1, p2, p3, p4, p5 = wave_points
        
        # رسم الخطوط المكونة للموجة
        # خط 1-3-5 (الدعم المكسور الذي أصبح منطقة دخول)
        fig.add_trace(go.Scatter(x=[p1['date'], p3['date'], p5['date']], 
                                 y=[p1['price'], p3['price'], p5['price']],
                                 mode='lines+markers', marker=dict(size=10, color='blue'),
                                 line=dict(color='green', width=2), name='Wave 1-3-5'))
        
        # خط 2-4
        fig.add_trace(go.Scatter(x=[p2['date'], p4['date']], 
                                 y=[p2['price'], p4['price']],
                                 mode='lines+markers', marker=dict(size=10, color='red'),
                                 line=dict(color='red', width=2), name='Wave 2-4'))

        # --- رسم خط الهدف (EPA Line) من 1 إلى 4 ممتد للمستقبل ---
        # حساب المعادلة الخطية بين P1 و P4
        x1_num = p1['idx']
        x4_num = p4['idx']
        y1 = p1['price']
        y4 = p4['price']
        
        slope = (y4 - y1) / (x4_num - x1_num)
        
        # تمديد الخط لليمين (مثلاً 20 شمعة بعد النقطة 5)
        last_idx = len(df) + 20
        start_y = y1
        end_y = y1 + slope * (last_idx - x1_num)
        
        # نحتاج تواريخ للرسم (تقريبية للمستقبل)
        last_date = df.index[-1]
        future_date = last_date + timedelta(days=30) # تقريبي للرسم
        
        fig.add_trace(go.Scatter(x=[p1['date'], future_date], 
                                 y=[y1, end_y],
                                 mode='lines', line=dict(color='gold', width=3, dash='dash'), 
                                 name='Target Line (1-4)'))
        
        # كتابة الأرقام على النقاط
        for i, p in enumerate(wave_points):
            fig.add_annotation(x=p['date'], y=p['price'], text=str(i+1), 
                               showarrow=True, arrowhead=1, yshift=10 if p['type']=='high' else -10,
                               font=dict(size=14, color="white", family="Arial Black"), bgcolor="black")

    fig.update_layout(title=f'تحليل الولفي: {ticker_name}', xaxis_rangeslider_visible=False, height=600)
    return fig

# --- واجهة التطبيق ---

tab1, tab2 = st.tabs(["📊 تحليل سهم محدد", "🔍 فحص السوق (Scanner)"])

# === التبويب الأول: تحليل سهم ===
with tab1:
    col1, col2, col3 = st.columns(3)
    with col1:
        ticker_input = st.text_input("أدخل رمز السهم (مثال: 1120.SR)", value="1120.SR")
    with col2:
        tf_option = st.selectbox("الفاصل الزمني", ["يومي (1d)", "أسبوعي (1wk)"], index=0)
    with col3:
        zigzag_window = st.number_input("زقزاق (عدد الشموع)", min_value=3, max_value=20, value=5)

    if st.button("حلل السهم"):
        interval = "1d" if "1d" in tf_option else "1wk"
        period = "2y" if interval == "1wk" else "1y"
        
        with st.spinner('جاري جلب البيانات...'):
            df = get_data(ticker_input, period=period, interval=interval)
        
        if df is not None:
            pivots = get_zigzag_pivots(df, order=zigzag_window)
            is_wolfe, wave_data = check_wolfe_wave(pivots)
            
            if is_wolfe:
                st.success(f"✅ تم اكتشاف نموذج ولفي صاعد محتمل على {ticker_input}")
            else:
                st.warning("❌ لم يكتمل النموذج على آخر البيانات (أو الشروط غير منطبقة بدقة).")
            
            # رسم الشارت سواء اكتمل النموذج أم لا ليرى المستخدم الزقزاق
            fig = plot_wolfe(df, pivots, ticker_input)
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.error("لم يتم العثور على بيانات لهذا الرمز.")

# === التبويب الثاني: الفاحص الآلي ===
with tab2:
    st.header("فحص قائمة الأسهم")
    st.write("سيقوم هذا الفاحص بالمرور على قائمة الأسهم المختارة والبحث عن نموذج مكتمل.")
    
    scan_tf = st.radio("فاصل الفحص", ["يومي", "أسبوعي"], horizontal=True)
    scan_interval = "1d" if scan_tf == "يومي" else "1wk"
    scan_period = "1y" if scan_tf == "يومي" else "2y"
    
    if st.button("ابدأ الفحص"):
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total = len(SAUDI_STOCKS)
        
        for i, (symbol, name) in enumerate(SAUDI_STOCKS.items()):
            status_text.text(f"جاري فحص: {name} ({symbol})...")
            
            df = get_data(symbol, period=scan_period, interval=scan_interval)
            
            if df is not None and len(df) > 50:
                pivots = get_zigzag_pivots(df, order=5)
                is_wolfe, wave_data = check_wolfe_wave(pivots)
                
                if is_wolfe:
                    last_price = df['Close'].iloc[-1]
                    # الحصول على سعر النقطة 5
                    p5_price = wave_data[4]['price']
                    
                    # هل السعر الحالي قريب من النقطة 5؟ (منطقة الدخول)
                    # هنا نفترض أننا لا زلنا في منطقة الدخول إذا لم يبتعد السعر كثيراً عن القاع
                    dist_from_p5 = (last_price - p5_price) / p5_price * 100
                    
                    results.append({
                        "الرمز": symbol,
                        "الاسم": name,
                        "السعر الحالي": round(last_price, 2),
                        "سعر القاع 5": round(p5_price, 2),
                        "الارتفاع عن القاع %": round(dist_from_p5, 2)
                    })
            
            progress_bar.progress((i + 1) / total)
            
        status_text.text("انتهى الفحص.")
        
        if results:
            st.success(f"تم العثور على {len(results)} أسهم يتوفر فيها الشرط!")
            res_df = pd.DataFrame(results)
            st.dataframe(res_df)
        else:
            st.info("لم يتم العثور على نماذج ولفي صاعدة مكتملة في القائمة الحالية.")
