from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

OUT = Path(__file__).resolve().parents[1] / "output"
DATA_END = pd.Timestamp("2026-09-30 23:04:41")  # 데이터의 마지막 이벤트 시각


@st.cache_data
def load():
    s = pd.read_csv(OUT / "sessions.csv", parse_dates=["session_start_kst"])
    ev = pd.read_csv(OUT / "events_flat.csv", parse_dates=["event_ts_kst"],
                     dtype={"user_id": str, "transaction_id": str, "session_engaged": str})
    it = pd.read_csv(OUT / "items_flat.csv", dtype={"transaction_id": str})
    # 쟁점 6: 카카오톡 채널 메시지(channel_message)는 Unassigned 대신 Kakao Message 채널로 분리
    s["channel"] = s.channel_group.where(s.session_medium != "channel_message", "Kakao Message")
    first = s[s.ga_session_number == 1].sort_values("session_start_kst").drop_duplicates("user_pseudo_id")
    s["user_channel"] = s.user_pseudo_id.map(first.set_index("user_pseudo_id").channel)
    s["session_date"] = pd.to_datetime(s.session_date)
    return s, ev, it


def sidebar_filters(s):
    st.sidebar.header("필터")
    d0, d1 = s.session_date.min().date(), s.session_date.max().date()
    rng = st.sidebar.date_input("기간", (d0, d1), min_value=d0, max_value=d1)
    if len(rng) != 2:
        st.stop()
    devs = sorted(s.device_category.unique())
    dev = st.sidebar.multiselect("기기", devs, default=devs)
    chs = sorted(s.channel.unique())
    ch = st.sidebar.multiselect("세션 채널", chs, default=chs)
    m = ((s.session_date >= pd.Timestamp(rng[0])) & (s.session_date <= pd.Timestamp(rng[1]))
         & s.device_category.isin(dev) & s.channel.isin(ch))
    return s[m], rng


def won(x):
    return "-" if pd.isna(x) else f"{x:,.0f}원"


def pct(x):
    return "-" if pd.isna(x) else f"{x:.1%}"


# ---------- 리텐션 ----------
def first_sessions(s_all):
    return (s_all[s_all.ga_session_number == 1].sort_values("session_start_kst")
            .drop_duplicates("user_pseudo_id")[["user_pseudo_id", "session_start_kst", "channel", "device_category"]]
            .rename(columns={"session_start_kst": "first_ts"}))


def nday_return_rate(firsts, s_all, n):
    """첫 방문 후 n일 안에 두 번째 이후 세션이 있는 사용자 비율. 관찰 기간이 n일 미만인 사용자는 분모에서 뺀다."""
    f = firsts[firsts.first_ts + pd.Timedelta(days=n) <= DATA_END]
    if f.empty:
        return float("nan"), 0, 0
    later = s_all[s_all.ga_session_number >= 2].merge(f[["user_pseudo_id", "first_ts"]], on="user_pseudo_id")
    ok = later[later.session_start_kst <= later.first_ts + pd.Timedelta(days=n)].user_pseudo_id.nunique()
    return ok / len(f), ok, len(f)


def day_offsets(firsts, s_all):
    """사용자 x 방문일 테이블 (첫 방문일 대비 N일 차이)"""
    v = s_all[["user_pseudo_id", "session_start_kst"]].copy()
    v["visit_date"] = v.session_start_kst.dt.normalize()
    v = v.drop_duplicates(["user_pseudo_id", "visit_date"]).merge(firsts[["user_pseudo_id", "first_ts"]], on="user_pseudo_id")
    v["cohort"] = v.first_ts.dt.normalize()
    v["n"] = (v.visit_date - v.cohort).dt.days
    return v


# ---------- 퍼널 ----------
def funnel_times(ev, stages):
    """세션별 각 단계의 최초 도달 시각. 이전 단계 이후에 발생한 이벤트만 인정한다."""
    e = ev[ev.event_name.isin(stages)][["session_key", "event_name", "event_ts_kst"]]
    cur = e[e.event_name == stages[0]].groupby("session_key").event_ts_kst.min().rename(stages[0]).to_frame()
    for prev, nxt_name in zip(stages, stages[1:]):
        nx = e[e.event_name == nxt_name][["session_key", "event_ts_kst"]].merge(
            cur[[prev]].dropna(), left_on="session_key", right_index=True)
        nx = nx[nx.event_ts_kst >= nx[prev]]
        cur[nxt_name] = nx.groupby("session_key").event_ts_kst.min()
    return cur


def prior_counts(ev, times, stages):
    """다음 단계에 도달한 세션에서, 그 시점까지 직전 단계 이벤트를 몇 번 수행했는지"""
    res = {}
    for prev, nxt_name in zip(stages, stages[1:]):
        t = times[nxt_name].dropna().rename("t")
        e = ev[ev.event_name == prev][["session_key", "event_ts_kst"]].merge(t, left_on="session_key", right_index=True)
        c = e[e.event_ts_kst <= e.t].groupby("session_key").size()
        res[nxt_name] = c.reindex(t.index).fillna(0).astype(int)
    return res


def render_funnel(title, stages, labels, ev, s_f, note):
    st.title(title)
    st.caption(note)
    ev_f = ev[ev.session_key.isin(s_f.session_key)]
    times = funnel_times(ev_f, stages)
    counts = [int(times[c].notna().sum()) for c in stages]
    n0 = max(counts[0], 1)
    st.subheader("퍼널")
    fig = go.Figure(go.Funnel(y=[labels[c] for c in stages], x=counts,
                              textinfo="value+percent initial+percent previous"))
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width="stretch")
    drop = pd.DataFrame({
        "단계": [labels[c] for c in stages], "세션 수": counts,
        "첫 단계 대비": [c / n0 for c in counts],
        "이전 단계 대비": [1] + [counts[i] / counts[i - 1] if counts[i - 1] else float("nan") for i in range(1, len(counts))],
        "이탈 세션 수": [0] + [counts[i - 1] - counts[i] for i in range(1, len(counts))]})
    st.dataframe(drop.style.format({"세션 수": "{:,}", "첫 단계 대비": "{:.1%}", "이전 단계 대비": "{:.1%}", "이탈 세션 수": "{:,}"}),
                 hide_index=True, width="stretch")

    st.subheader("추가 분석 1. 다음 단계로 가기 전에 이전 단계를 몇 번 수행했는가")
    st.caption("다음 단계에 도달한 세션에서, 그 시점까지 직전 단계 이벤트가 몇 번 발생했는지입니다.")
    pc = prior_counts(ev_f, times, stages)
    rows = []
    for c, ser in pc.items():
        if len(ser):
            rows.append({"다음 단계": labels[c], "직전 단계": labels[stages[stages.index(c) - 1]], "도달 세션": len(ser),
                         "평균 횟수": ser.mean(), "중앙값": ser.median(), "1회": (ser == 1).mean(),
                         "2~3회": ser.between(2, 3).mean(), "4회 이상": (ser >= 4).mean()})
    if rows:
        st.dataframe(pd.DataFrame(rows).style.format(
            {"평균 횟수": "{:.2f}", "중앙값": "{:.0f}", "1회": "{:.1%}", "2~3회": "{:.1%}", "4회 이상": "{:.1%}"}),
            hide_index=True, width="stretch")
        pick = st.selectbox("분포를 볼 단계", [r["다음 단계"] for r in rows])
        key = [c for c in pc if labels[c] == pick][0]
        vc = pc[key].clip(upper=10).value_counts().sort_index()
        f = go.Figure(go.Bar(x=[str(i) if i < 10 else "10+" for i in vc.index], y=vc.values))
        f.update_layout(height=300, xaxis_title=f"'{labels[stages[stages.index(key) - 1]]}' 수행 횟수",
                        yaxis_title="세션 수", margin=dict(t=10))
        st.plotly_chart(f, width="stretch")
    else:
        st.info("선택한 조건에서 다음 단계에 도달한 세션이 없습니다.")

    st.subheader("추가 분석 2. 각 단계에서 다음 단계까지 걸린 시간")
    rows, dists = [], {}
    for prev, nxt_name in zip(stages, stages[1:]):
        d = (times[nxt_name] - times[prev]).dt.total_seconds().dropna()
        name = f"{labels[prev]} → {labels[nxt_name]}"
        dists[name] = d
        if len(d):
            rows.append({"구간": name, "세션 수": len(d), "평균(초)": d.mean(), "중앙값(초)": d.median(),
                         "75%(초)": d.quantile(.75), "최대(초)": d.max()})
    if rows:
        st.dataframe(pd.DataFrame(rows).style.format(
            {"세션 수": "{:,}", "평균(초)": "{:,.0f}", "중앙값(초)": "{:,.0f}", "75%(초)": "{:,.0f}", "최대(초)": "{:,.0f}"}),
            hide_index=True, width="stretch")
        f = go.Figure()
        for k, d in dists.items():
            f.add_trace(go.Box(y=d.clip(lower=0.5), name=k, boxmean=True))
        f.update_yaxes(type="log", title="걸린 시간(초, 로그 축)")
        f.update_layout(height=380, showlegend=False, margin=dict(t=10))
        st.plotly_chart(f, width="stretch")
        st.caption("같은 세션 안에서 이전 단계 최초 발생 시각과 다음 단계 최초 발생 시각의 차이입니다. 0초는 그래프에서 0.5초로 표시됩니다.")
