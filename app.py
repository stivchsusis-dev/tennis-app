import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json # ←★これを追加しました

st.set_page_config(page_title="Elite Tennis Profiler", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { background-color: #F8F9FA; color: #212529; font-family: -apple-system, sans-serif; }
    h1 { color: #1A73E8 !important; font-weight: 700 !important; letter-spacing: 1px; border-bottom: 3px solid #1A73E8; padding-bottom: 10px; margin-bottom: 25px; }
    h2, h3 { color: #343A40 !important; font-weight: 600 !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; background-color: transparent; }
    .stTabs [data-baseweb="tab"] { height: 45px; background-color: #E9ECEF; border-radius: 6px 6px 0 0; padding: 10px 20px; color: #495057; font-weight: 500; border: 1px solid #DEE2E6; border-bottom: none; }
    .stTabs [aria-selected="true"] { background-color: #FFFFFF !important; color: #1A73E8 !important; font-weight: bold; border-top: 3px solid #1A73E8; }
    .stNumberInput>div>div>input, .stTextInput>div>div>input, .stDateInput>div>div>input { background-color: #FFFFFF; color: #212529; border: 1px solid #CED4DA; border-radius: 4px; padding: 8px; }
    .stButton>button { background-color: #1A73E8; color: #FFFFFF; font-weight: bold; border-radius: 6px; border: none; padding: 10px 20px; width: 100%; transition: background-color 0.2s; }
    .stButton>button:hover { background-color: #1557B0; color: #FFFFFF; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🔒 セキュリティ：パスワード認証機能
# ==========================================
APP_PASSWORD = st.secrets["APP_PASSWORD"]
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("<h1 style='text-align: center;'>🔒 チーム専用ログイン</h1>", unsafe_allow_html=True)
    st.write("<p style='text-align: center;'>チーム内で共有されたパスワードを入力してください。</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("パスワード", type="password")
        if st.button("ログイン"):
            if pwd == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ パスワードが違います")
    st.stop() # パスワードが合わないとこれ以降の処理（データ表示など）は絶対に実行されません

# ==========================================
# ☁️ Googleスプレッドシート連携機能
# ==========================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/12oDwZEioRUxIJ6ntGqX9iQc2z76Pu8sukRizvBS6Jb0/edit?gid=0#gid=0"

# --- ★ここから書き換えました（Secrets対応） ---
@st.cache_resource
def init_connection():
    # StreamlitのSecrets（金庫）から合鍵を取り出して辞書型（JSON）に変換
    creds_dict = json.loads(st.secrets["gcp_service_account"])
    
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    # 鍵と権限を使って認証情報を生成
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    
    return gspread.authorize(creds)
# --- ★ここまで書き換えました ---

gc = init_connection()

test_metrics = {
    'アジリティ (Tテスト: 秒)':     {'min_val': 11.0, 'max_val': 9.5,   'lower_is_better': True, 'default': 10.5},
    'スプリント (10m: 秒)':        {'min_val': 1.85, 'max_val': 1.60,  'lower_is_better': True, 'default': 1.75},
    '下肢パワー (垂直跳び: cm)':   {'min_val': 50,   'max_val': 70,    'lower_is_better': False, 'default': 60.0},
    '体幹パワー (MBスロー: m)':    {'min_val': 8.0,  'max_val': 12.0,  'lower_is_better': False, 'default': 9.5},
    '持久力 (Yo-Yo: レベル)':      {'min_val': 16.0, 'max_val': 20.0,  'lower_is_better': False, 'default': 18.0}
}
categories = list(test_metrics.keys())

def calculate_score(val, metric_info):
    min_v, max_v = metric_info['min_val'], metric_info['max_val']
    if metric_info['lower_is_better']:
        if val >= min_v: return 0
        if val <= max_v: return 100
        return max(0, min(100, int(100 * (min_v - val) / (min_v - max_v))))
    else:
        if val <= min_v: return 0
        if val >= max_v: return 100
        return max(0, min(100, int(100 * (val - min_v) / (max_v - min_v))))

def load_data():
    try:
        sh = gc.open_by_url(SHEET_URL)
        worksheet = sh.sheet1
        data = worksheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            df['測定日'] = pd.to_datetime(df['測定日']).dt.strftime('%Y-%m-%d')
            df = df.sort_values(by=['選手名', '測定日']).reset_index(drop=True)
            return df
    except Exception as e:
        pass # URLが未設定だったり、データが空の場合は下に進む
    cols = ['ID', '測定日', '選手名'] + categories
    return pd.DataFrame(columns=cols)

def save_data(df):
    sh = gc.open_by_url(SHEET_URL)
    worksheet = sh.sheet1
    worksheet.clear()
    
    # エラーを防ぐためにデータ型を整える
    for col in df.columns:
        if df[col].dtype == 'int64':
            df[col] = df[col].astype(int)
        elif df[col].dtype == 'float64':
            df[col] = df[col].astype(float)
            
    list_data = [df.columns.values.tolist()] + df.values.tolist()
    worksheet.update(values=list_data, range_name='A1')

df = load_data()

st.title("🎾 チーム・フィジカル管理システム")
st.caption("テニス部専用 データ蓄積＆分析ダッシュボード")

tab1, tab2, tab3 = st.tabs(["📝 データ入力", "📊 個人分析 (成長推移)", "🏆 チーム全体・管理"])

# ==========================================
# タブ1: データ入力
# ==========================================
with tab1:
    st.markdown("### 📊 測定データの登録")
    st.info("既に登録済みの「選手名」と全く同じ名前で入力すると、その選手の過去データに紐づいて成長比較ができます。")
    
    c1, c2 = st.columns(2)
    date_input = c1.date_input("測定日")
    name_input = c2.text_input("選手名 (例: 山田太郎)")
    st.markdown("---")
    
    input_values = {}
    cols1 = st.columns(3)
    for i in range(3):
        cat = categories[i]
        with cols1[i]:
            input_values[cat] = st.number_input(cat, value=test_metrics[cat]['default'], format="%.2f")
            
    cols2 = st.columns(2)
    for i in range(3, 5):
        cat = categories[i]
        with cols2[i-3]:
            input_values[cat] = st.number_input(cat, value=test_metrics[cat]['default'], format="%.2f")
            
    st.markdown("<br>", unsafe_allow_html=True)
    
    if st.button("💾 このデータを保存する"):
        if SHEET_URL == "ここにURLを貼り付けます":
            st.error("🚨 エラー：コード内の `SHEET_URL` が設定されていません！")
        elif not name_input.strip():
            st.error("選手名を入力してください！")
        else:
            clean_name = name_input.strip()
            new_id = 1 if (df.empty or 'ID' not in df.columns) else int(df['ID'].max() + 1)
                
            new_data = {'ID': new_id, '測定日': date_input.strftime('%Y-%m-%d'), '選手名': clean_name}
            new_data.update(input_values)
            
            new_df = pd.DataFrame([new_data])
            df = new_df if df.empty else pd.concat([df, new_df], ignore_index=True)
                
            df['測定日'] = pd.to_datetime(df['測定日'])
            df = df.sort_values(by=['選手名', '測定日']).reset_index(drop=True)
            df['測定日'] = df['測定日'].dt.strftime('%Y-%m-%d')
            
            save_data(df) # スプレッドシートに保存
            st.success(f"✔️ {clean_name} 選手のデータを保存しました！スプレッドシートを確認してください。")
            st.rerun()

# ==========================================
# タブ2: 個人分析（レーダー ＋ 成長推移）
# ==========================================
with tab2:
    if df.empty:
        st.warning("データがまだ1件もありません。📝タブでデータを入力して保存してください。")
    else:
        players = df['選手名'].dropna().unique()
        if len(players) > 0:
            selected_player = st.selectbox("分析する選手を選択してください", players)
            player_history = df[df['選手名'] == selected_player]
            
            if not player_history.empty:
                latest_data = player_history.iloc[-1]
                player_scores = [calculate_score(latest_data[cat], test_metrics[cat]) for cat in categories]
                    
                latest_team_df = df.drop_duplicates(subset=['選手名'], keep='last')
                team_avg_scores = [calculate_score(latest_team_df[cat].mean(), test_metrics[cat]) for cat in categories]

                st.markdown(f"### {selected_player} 選手の最新プロファイル (測定日: {latest_data['測定日']})")
                
                fig = go.Figure()
                def close_poly(data): return list(data) + [data[0]]
                cat_closed = close_poly(categories)
                
                fig.add_trace(go.Scatterpolar(
                      r=close_poly(team_avg_scores), theta=cat_closed, fill='toself',
                      name='チーム平均', line_color='rgba(108, 117, 125, 0.6)', fillcolor='rgba(108, 117, 125, 0.2)'
                ))
                fig.add_trace(go.Scatterpolar(
                      r=close_poly(player_scores), theta=cat_closed, fill='toself',
                      name='最新記録', line_color='#1A73E8', fillcolor='rgba(26, 115, 232, 0.4)', line=dict(width=3)
                ))
                if len(player_history) > 1:
                    prev_data = player_history.iloc[-2]
                    prev_scores = [calculate_score(prev_data[cat], test_metrics[cat]) for cat in categories]
                    fig.add_trace(go.Scatterpolar(
                        r=close_poly(prev_scores), theta=cat_closed, fill='none',
                        name=f'前回 ({prev_data["測定日"]})', line_color='#28A745', line=dict(width=2, dash='dot')
                    ))
                if len(player_history) > 2:
                    first_data = player_history.iloc[0]
                    first_scores = [calculate_score(first_data[cat], test_metrics[cat]) for cat in categories]
                    fig.add_trace(go.Scatterpolar(
                        r=close_poly(first_scores), theta=cat_closed, fill='none',
                        name=f'初回 ({first_data["測定日"]})', line_color='#FF8C00', line=dict(width=2, dash='dash')
                    ))
                
                if len(player_history) > 2:
                    st.success("💡 緑の点線が「前回」、オレンジの破線が「初回」のスコアです。")
                elif len(player_history) == 2:
                    st.success("💡 緑の点線が「前回（初回）」のスコアです。")
                
                fig.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100], gridcolor='#DEE2E6', linecolor='#DEE2E6')),
                    paper_bgcolor='#FFFFFF', plot_bgcolor='#FFFFFF', font=dict(color='#212529'),
                    height=550, margin=dict(t=40, b=40)
                )
                
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.plotly_chart(fig, use_container_width=True)
                with c2:
                    st.markdown("#### 最新の実数値記録")
                    st.write("---")
                    for cat in categories:
                        val_str = "{:.2f}".format(latest_data[cat]) if '10m' in cat or 'Tテスト' in cat else "{:.1f}".format(latest_data[cat])
                        score = player_scores[categories.index(cat)]
                        
                        diff_str = ""
                        if len(player_history) > 1:
                            diff_val = latest_data[cat] - prev_data[cat]
                            if test_metrics[cat]['lower_is_better']:
                                if diff_val < 0: diff_str = f" <span style='color:#28A745; font-size:0.8em;'>(▼ {abs(diff_val):.2f})</span>"
                                elif diff_val > 0: diff_str = f" <span style='color:#DC3545; font-size:0.8em;'>(▲ {abs(diff_val):.2f})</span>"
                            else:
                                if diff_val > 0: diff_str = f" <span style='color:#28A745; font-size:0.8em;'>(▲ {abs(diff_val):.1f})</span>"
                                elif diff_val < 0: diff_str = f" <span style='color:#DC3545; font-size:0.8em;'>(▼ {abs(diff_val):.1f})</span>"
                        st.markdown(f"**{cat.split(' ')[0]}**<br><span style='color:#1A73E8; font-size:1.4em; font-weight:bold;'>{val_str}</span>{diff_str} <span style='color:#6C757D; font-size:0.8em;'>(換算: {score})</span>", unsafe_allow_html=True)

# ==========================================
# タブ3: データ管理 (編集・削除機能)
# ==========================================
with tab3:
    if df.empty:
        st.warning("データがまだ1件もありません。")
    else:
        st.markdown("### 📝 データの直接編集・削除")
        df_display = df.copy()
        df_display.insert(0, "Delete", False)
        
        edited_df = st.data_editor(
            df_display, hide_index=True, use_container_width=True,
            disabled=["ID"], key="data_editor"
        )
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 変更を保存する (UPDATE)"):
                updated_df = edited_df.drop(columns=["Delete"])
                updated_df['測定日'] = pd.to_datetime(updated_df['測定日']).dt.strftime('%Y-%m-%d')
                updated_df = updated_df.sort_values(by=['選手名', '測定日']).reset_index(drop=True)
                save_data(updated_df)
                st.success("✅ スプレッドシートに変更を保存しました！")
                st.rerun()

        with col_btn2:
            if st.button("🚨 チェックを入れたデータを削除 (DELETE)"):
                rows_to_delete = edited_df[edited_df['Delete'] == True]
                if not rows_to_delete.empty:
                    ids_to_delete = rows_to_delete['ID'].tolist()
                    df = df[~df['ID'].isin(ids_to_delete)]
                    save_data(df)
                    st.success(f"{len(ids_to_delete)} 件のデータを削除しました。")
                    st.rerun()
                else:
                    st.warning("削除するデータにチェックが入っていません。")
        
        st.markdown("---")
        st.markdown("### 🏆 チーム内ランキング (最新記録)")
        selected_category = st.selectbox("比較する種目を選択:", categories)
        latest_team_df = df.drop_duplicates(subset=['選手名'], keep='last')
        
        if not latest_team_df.empty:
            is_ascending = test_metrics[selected_category]['lower_is_better']
            latest_team_df = latest_team_df.sort_values(selected_category, ascending=is_ascending)
            bar_fig = go.Figure(go.Bar(
                x=latest_team_df['選手名'], y=latest_team_df[selected_category], marker_color='#1A73E8',
                text=latest_team_df[selected_category].apply(lambda x: f"{x:.2f}" if '10m' in selected_category or 'Tテスト' in selected_category else f"{x:.1f}"), textposition='auto'
            ))
            if is_ascending:
                bar_fig.update_layout(yaxis=dict(autorange="reversed"))
            bar_fig.update_layout(paper_bgcolor='#FFFFFF', plot_bgcolor='#FFFFFF', font=dict(color='#212529'), yaxis=dict(gridcolor='#DEE2E6'), height=400)
            st.plotly_chart(bar_fig, use_container_width=True)