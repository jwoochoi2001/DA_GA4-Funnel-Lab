import pandas as pd
import plotly.express as px
import streamlit as st
from common import load, sidebar_filters, first_sessions, nday_return_rate, won, pct

st.set_page_config(page_title="AARRR", layout="wide")
s_all, ev, it = load()
s, rng = sidebar_filters(s_all)
st.title("AARRR 지표")
st.caption("정의는 '몰메이트 AARRR 지표 정의서' 제안 기준입니다. 세션 지표는 세션 채널, 새 사용자·재방문은 사용자 채널(첫 세션 채널)로 나눕니다.")
if s.empty:
    st.warning("선택한 조건에 세션이 없습니다.")
    st.stop()

new_s = s[s.ga_session_number == 1]
tab_a, tab_ac, tab_rt, tab_rv, tab_rf = st.tabs(["Acquisition", "Activation", "Retention", "Revenue", "Referral"])

# ---------------- Acquisition ----------------
with tab_a:
    c = st.columns(3)
    c[0].metric("세션 수", f"{len(s):,}")
    c[1].metric("사용자 수", f"{s.user_pseudo_id.nunique():,}")
    c[2].metric("새 사용자 수", f"{new_s.user_pseudo_id.nunique():,}")
    by = s.groupby("channel").agg(세션=("session_key", "count"), 참여세션=("engaged_session", "sum")).reset_index()
    by["세션 비중"] = by.세션 / by.세션.sum()
    by["참여 세션 비율"] = by.참여세션 / by.세션
    nu = new_s.groupby("user_channel").user_pseudo_id.nunique().rename("새 사용자").reset_index().rename(columns={"user_channel": "channel"})
    by = by.merge(nu, on="channel", how="outer").fillna(0).sort_values("세션", ascending=False)
    l, r = st.columns(2)
    l.subheader("채널별 새 사용자 수")
    l.plotly_chart(px.bar(by, x="channel", y="새 사용자", labels={"channel": "사용자 채널"}), width="stretch")
    r.subheader("채널별 세션 수·비중")
    r.plotly_chart(px.pie(by, names="channel", values="세션", hole=.4), width="stretch")
    st.subheader("유입 품질: 채널별 참여 세션 비율")
    st.plotly_chart(px.bar(by.sort_values("참여 세션 비율"), x="참여 세션 비율", y="channel", orientation="h",
                           text=by.sort_values("참여 세션 비율")["참여 세션 비율"].map(pct)), width="stretch")
    st.dataframe(by.rename(columns={"channel": "채널"})[["채널", "새 사용자", "세션", "세션 비중", "참여 세션 비율"]].style.format(
        {"새 사용자": "{:,.0f}", "세션": "{:,.0f}", "세션 비중": "{:.1%}", "참여 세션 비율": "{:.1%}"}), hide_index=True, width="stretch")
    st.subheader("캠페인별 유입")
    show_all = st.checkbox("(organic)·(direct)·(referral) 포함", value=False)
    camp = s if show_all else s[~s.session_campaign.isin(["(organic)", "(direct)", "(referral)", "(not set)"])]
    cg = camp.groupby(["session_campaign", "session_source", "session_medium"]).agg(
        세션=("session_key", "count"), 새사용자=("is_new_user", "sum"), 참여세션비율=("engaged_session", "mean"),
        구매세션=("purchase", "sum"), 매출=("session_revenue", "sum")).reset_index().sort_values("세션", ascending=False)
    st.dataframe(cg.rename(columns={"session_campaign": "캠페인", "session_source": "소스", "session_medium": "매체",
                                    "새사용자": "새 사용자(세션 기준)", "참여세션비율": "참여 세션 비율", "구매세션": "구매 세션", "매출": "매출(원)"}
                           ).style.format({"참여 세션 비율": "{:.1%}", "매출(원)": "{:,.0f}"}), hide_index=True, width="stretch")

# ---------------- Activation ----------------
with tab_ac:
    n_new = max(new_s.user_pseudo_id.nunique(), 1)
    ev_s = ev[ev.session_key.isin(s.session_key)]
    eng = ev_s.groupby("session_key").engagement_time_msec.sum().reindex(s.session_key).fillna(0) / 1000
    c = st.columns(4)
    c[0].metric("신규 사용자 활성화율(첫 세션 상품 조회)", pct(new_s[new_s.view_item == 1].user_pseudo_id.nunique() / n_new))
    c[1].metric("첫 세션 장바구니 담기율", pct(new_s[new_s.add_to_cart == 1].user_pseudo_id.nunique() / n_new))
    c[2].metric("세션당 페이지뷰", f"{s.pageviews.mean():.2f}")
    c[3].metric("세션당 평균 참여 시간", f"{eng.mean():.1f}초")
    st.caption("활성화 기준 행동은 상품 상세 조회(제안). 참여 시간이 없는 세션은 0초로 평균에 포함합니다.")
    g = new_s.groupby("channel").agg(새사용자=("user_pseudo_id", "nunique"), 상품조회=("view_item", "mean"),
                                    장바구니=("add_to_cart", "mean")).reset_index()
    l, r = st.columns(2)
    l.subheader("채널별 첫 세션 활성화")
    l.plotly_chart(px.bar(g.melt("channel", ["상품조회", "장바구니"]), x="channel", y="value", color="variable", barmode="group",
                          labels={"value": "비율", "variable": "행동", "channel": "채널"}), width="stretch")
    r.subheader("기기별 세션당 페이지뷰")
    r.plotly_chart(px.bar(s.groupby("device_category").pageviews.mean().reset_index(), x="device_category", y="pageviews"),
                   width="stretch")

# ---------------- Retention ----------------
with tab_rt:
    firsts = first_sessions(s_all)
    fsel = firsts[firsts.user_pseudo_id.isin(s.user_pseudo_id) &
                  firsts.first_ts.between(pd.Timestamp(rng[0]), pd.Timestamp(rng[1]) + pd.Timedelta(days=1))]
    n = st.radio("재방문 기간 N일", [7, 14, 30], index=2, horizontal=True)
    rate, ok, base = nday_return_rate(fsel, s_all, n)
    c = st.columns(3)
    c[0].metric(f"{n}일 재방문율", pct(rate))
    c[1].metric("재방문 사용자", f"{ok:,}")
    c[2].metric("관찰 가능한 새 사용자", f"{base:,}")
    st.caption("첫 방문 + N일이 데이터 마지막 시각(2026-09-30) 이전인 사용자만 분모에 넣습니다. 재방문 세션은 필터와 상관없이 모든 세션에서 찾습니다.")
    rows = []
    for ch, f in fsel.groupby("channel"):
        r_, o_, b_ = nday_return_rate(f, s_all, n)
        rows.append({"채널": ch, "재방문율": r_, "재방문 사용자": o_, "관찰 가능 새 사용자": b_})
    rt = pd.DataFrame(rows).sort_values("재방문율", ascending=False)
    st.subheader("채널별 재방문율")
    st.plotly_chart(px.bar(rt, x="채널", y="재방문율", text=rt.재방문율.map(pct)), width="stretch")
    st.dataframe(rt.style.format({"재방문율": "{:.1%}"}), hide_index=True, width="stretch")

# ---------------- Revenue ----------------
with tab_rv:
    ords = ev[(ev.event_name == "purchase") & ev.session_key.isin(s.session_key)].drop_duplicates("transaction_id")
    revenue = ords.purchase_revenue.sum()
    n_orders = len(ords)
    buyers = s[s.purchase == 1].user_pseudo_id.nunique()
    users = s.user_pseudo_id.nunique()
    c = st.columns(4)
    c[0].metric("매출", won(revenue))
    c[1].metric("주문 수", f"{n_orders:,}")
    c[2].metric("AOV", won(revenue / n_orders if n_orders else float("nan")))
    c[3].metric("구매 전환율(세션)", pct(s.purchase.mean()))
    c = st.columns(4)
    c[0].metric("구매 전환율(사용자)", pct(buyers / users))
    c[1].metric("ARPU(전체 사용자당)", won(revenue / users))
    c[2].metric("ARPPU(구매자당)", won(revenue / buyers if buyers else float("nan")))
    c[3].metric("매출 기준", "배송비 제외·환불 미차감")

    st.subheader("채널별 매출·전환율·세션당 매출")
    cg = s.groupby("channel").agg(세션=("session_key", "count"), 구매세션=("purchase", "sum"), 매출=("session_revenue", "sum")).reset_index()
    cg["구매 전환율"] = cg.구매세션 / cg.세션
    cg["세션당 매출"] = cg.매출 / cg.세션
    l, r = st.columns(2)
    l.plotly_chart(px.bar(cg, x="channel", y="매출", title="채널별 매출(원)"), width="stretch")
    r.plotly_chart(px.bar(cg, x="channel", y="구매 전환율", title="채널별 구매 전환율"), width="stretch")
    st.dataframe(cg.rename(columns={"channel": "채널"}).style.format(
        {"매출": "{:,.0f}", "구매 전환율": "{:.1%}", "세션당 매출": "{:,.0f}"}), hide_index=True, width="stretch")

    st.subheader("결제수단별 전환율 (같은 세션 안 구매, 세션의 마지막 선택 수단 기준)")
    pay = (ev[(ev.event_name == "add_payment_info") & ev.session_key.isin(s.session_key)].dropna(subset=["payment_type"])
           .sort_values("event_ts_kst").drop_duplicates("session_key", keep="last")[["session_key", "payment_type", "event_ts_kst"]]
           .merge(s[["session_key", "purchase", "device_category"]], on="session_key"))
    pay["시기"] = pay.event_ts_kst.dt.normalize().lt(pd.Timestamp("2026-08-20")).map({True: "간편결제 도입 전", False: "도입 후"})
    pay["기기"] = pay.device_category.where(pay.device_category == "mobile", "그 외").replace({"mobile": "모바일"})
    pg = pay.groupby(["payment_type", "시기", "기기"]).agg(결제정보입력=("session_key", "count"), 구매=("purchase", "sum")).reset_index()
    pg["전환율"] = pg.구매 / pg.결제정보입력
    pp = pay.groupby("payment_type").agg(결제정보입력=("session_key", "count"), 구매=("purchase", "sum")).reset_index()
    pp["전환율"] = pp.구매 / pp.결제정보입력
    if len(pp):
        st.plotly_chart(px.bar(pp, x="payment_type", y="전환율", text=pp.전환율.map(pct), labels={"payment_type": "결제수단"}), width="stretch")
        with st.expander("도입일(8/20) 전후·기기별 상세"):
            st.dataframe(pg.rename(columns={"payment_type": "결제수단"}).style.format({"전환율": "{:.1%}"}), hide_index=True, width="stretch")
    else:
        st.info("결제정보 입력 세션이 없습니다.")

    st.subheader("쿠폰·할인")
    ip = it[(it.event_name == "purchase") & it.session_key.isin(s.session_key)].copy()
    ip["discount"] = ip.price * ip.quantity - ip.item_revenue
    ip["has_coupon"] = ip.coupon.notna() & ip.coupon.astype(str).str.strip().ne("") & ip.coupon.ne("(not set)")
    coupon_orders = ip[ip.has_coupon].transaction_id.nunique()
    c = st.columns(3)
    c[0].metric("쿠폰 사용률(주문)", pct(coupon_orders / n_orders if n_orders else float("nan")))
    c[1].metric("할인액 합계", won(ip.discount.sum()))
    c[2].metric("쿠폰 주문 수", f"{coupon_orders:,}")

    st.subheader("카테고리·상품별 매출")
    l, r = st.columns(2)
    cat = ip.groupby(["item_category", "item_category2"]).item_revenue.sum().reset_index()
    if len(cat):
        l.plotly_chart(px.sunburst(cat, path=["item_category", "item_category2"], values="item_revenue", title="카테고리 매출"), width="stretch")
    prod = ip.groupby("item_name").agg(매출=("item_revenue", "sum"), 수량=("quantity", "sum"), 주문수=("transaction_id", "nunique")).reset_index().sort_values("매출", ascending=False)
    r.dataframe(prod.head(20).style.format({"매출": "{:,.0f}"}), hide_index=True, width="stretch")

# ---------------- Referral ----------------
with tab_rf:
    st.info("공유·초대 이벤트가 없어 추천을 직접 측정할 수 없습니다. Referral 채널(외부 링크 유입)을 대체 지표로 보고 나머지 채널과 비교합니다.")
    s["그룹"] = s.channel.where(s.channel == "Referral", "Referral 외 전체")
    firsts = first_sessions(s_all)
    fsel = firsts[firsts.user_pseudo_id.isin(s.user_pseudo_id)]
    rows = []
    for name, g in s.groupby("그룹"):
        f = fsel[fsel.channel == "Referral"] if name == "Referral" else fsel[fsel.channel != "Referral"]
        r30, _, _ = nday_return_rate(f, s_all, 30)
        rows.append({"그룹": name, "세션": len(g), "세션 비중": len(g) / len(s),
                     "새 사용자": g[g.ga_session_number == 1].user_pseudo_id.nunique(),
                     "구매 전환율": g.purchase.mean(), "매출": g.session_revenue.sum(),
                     "참여율": g.engaged_session.mean(), "30일 재방문율": r30})
    rf = pd.DataFrame(rows)
    st.dataframe(rf.style.format({"세션 비중": "{:.1%}", "구매 전환율": "{:.1%}", "매출": "{:,.0f}", "참여율": "{:.1%}", "30일 재방문율": "{:.1%}"}),
                 hide_index=True, width="stretch")
    if (s.channel == "Referral").sum() < 100:
        st.caption("Referral 세션이 적어서 기간·기기 필터를 걸면 비율이 크게 흔들릴 수 있습니다.")
    src = s[s.channel == "Referral"].groupby("session_source").size().reset_index(name="세션").sort_values("세션", ascending=False)
    if len(src):
        st.subheader("Referral 소스별 세션")
        st.plotly_chart(px.bar(src, x="session_source", y="세션"), width="stretch")
