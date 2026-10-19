import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from common import load, first_sessions, day_offsets, DATA_END

st.set_page_config(page_title="리텐션", layout="wide")
s_all, ev, it = load()
st.title("리텐션")
st.caption("첫 방문일(첫 세션 날짜)을 0일로 두고, N일째에 다시 방문한 사용자를 셉니다(N-day 리텐션, 해당 날짜 하루 기준).")

st.sidebar.header("필터")
devs = sorted(s_all.device_category.unique())
dev = st.sidebar.multiselect("첫 세션 기기", devs, default=devs)
chs = sorted(s_all.channel.unique())
ch = st.sidebar.multiselect("첫 세션 채널", chs, default=chs)
max_n = st.sidebar.slider("최대 N일", 7, 60, 30)
cohort_unit = st.sidebar.radio("코호트 단위", ["일", "주"], horizontal=True)

firsts = first_sessions(s_all)
firsts = firsts[firsts.device_category.isin(dev) & firsts.channel.isin(ch)]
v = day_offsets(firsts, s_all)
v = v[(v.n >= 0) & (v.n <= max_n)]
last_day = DATA_END.normalize()
if firsts.empty:
    st.warning("선택한 조건에 사용자가 없습니다.")
    st.stop()

# ---- 1) 리텐션 곡선 ----
st.subheader("N일 리텐션 곡선")
rows = []
fday = firsts.first_ts.dt.normalize()
for n in range(1, max_n + 1):
    observable = fday + pd.Timedelta(days=n) <= last_day  # N일째가 데이터 범위 안인 코호트만 분모에 포함
    base = int(observable.sum())
    if base == 0:
        continue
    users_n = v[(v.n == n) & v.user_pseudo_id.isin(firsts[observable].user_pseudo_id)].user_pseudo_id.nunique()
    rows.append({"n": n, "방문 사용자": users_n, "관찰 가능 사용자": base, "재방문율": users_n / base})
cur = pd.DataFrame(rows)
fig = go.Figure()
fig.add_bar(x=cur.n, y=cur["방문 사용자"], name="방문 사용자 수", marker_color="#9ecae1")
fig.add_scatter(x=cur.n, y=cur["재방문율"], name="재방문 %", yaxis="y2", mode="lines+markers", line=dict(color="#d62728"))
fig.update_layout(height=420, xaxis_title="첫 방문 후 경과일 (N일)", yaxis_title="방문 사용자 수",
                  yaxis2=dict(title="재방문 %", overlaying="y", side="right", tickformat=".0%", rangemode="tozero"),
                  legend=dict(orientation="h", y=1.1), margin=dict(t=30))
st.plotly_chart(fig, width="stretch")
st.caption("0일(첫 방문, 100%)은 다른 값이 안 보여서 그래프에서 뺐습니다. N일째가 데이터 마지막 날(2026-09-30) 이후인 사용자는 해당 N일의 분모에서 뺍니다.")
with st.expander("표로 보기"):
    st.dataframe(cur.style.format({"재방문율": "{:.1%}"}), hide_index=True, width="stretch")

# ---- 2) 코호트 히트맵 ----
st.subheader("N일 리텐션 코호트 히트맵")
v = v.copy()
if cohort_unit == "주":
    v["coh"] = v.cohort.dt.to_period("W-SUN").dt.start_time
    f2 = firsts.assign(coh=firsts.first_ts.dt.to_period("W-SUN").dt.start_time)
else:
    v["coh"] = v.cohort
    f2 = firsts.assign(coh=firsts.first_ts.dt.normalize())
size = f2.groupby("coh").size()
act = v.groupby(["coh", "n"]).user_pseudo_id.nunique().unstack(fill_value=0).reindex(size.index, fill_value=0)
act = act.reindex(columns=range(0, max_n + 1), fill_value=0)
mat = act.div(size, axis=0) * 100
# 아직 관찰할 수 없는 칸(코호트 마지막 날 + N일 > 데이터 마지막 날)은 비움
end_of_cohort = pd.Series(mat.index, index=mat.index) + (pd.Timedelta(days=6) if cohort_unit == "주" else pd.Timedelta(days=0))
for n in mat.columns:
    mat.loc[end_of_cohort + pd.Timedelta(days=n) > last_day, n] = np.nan
ylab = [d.strftime("%m-%d") for d in mat.index]
text = [[("" if pd.isna(x) else f"{x:.0f}") for x in row] for row in mat.values]
hm = go.Figure(go.Heatmap(z=mat.values, x=list(mat.columns), y=ylab, text=text, texttemplate="%{text}" if max_n <= 30 else None,
                          colorscale="Blues", colorbar=dict(title="%"), zmin=0, zmax=min(100, float(np.nanmax(mat.values[:, 1:])) if max_n else 100),
                          hovertemplate="코호트 %{y}<br>%{x}일 후: %{z:.1f}%<extra></extra>"))
hm.update_yaxes(autorange="reversed", title="첫 방문일(코호트)" if cohort_unit == "일" else "첫 방문 주(월요일)", type="category")
hm.update_xaxes(title="첫 방문 후 경과일 (N일)", dtick=1 if max_n <= 30 else 5)
hm.update_layout(height=max(500, 14 * len(mat)), margin=dict(t=10))
st.plotly_chart(hm, width="stretch")
st.caption("각 칸은 그 코호트 사용자 중 N일째에 다시 방문한 비율(%)입니다. 0일(100%)은 색 범위를 위해 제외하고 색을 맞췄습니다. 코호트가 작아(하루 20여 명) 값이 크게 흔들리면 '주' 단위로 바꿔 보세요.")
