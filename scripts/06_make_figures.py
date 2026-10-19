"""README용 차트 이미지(docs/images)와 표(docs/_tables.md)를 만든다."""
import shutil
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))
sys.stdout.reconfigure(encoding="utf-8")
from common import DATA_END, day_offsets, first_sessions, funnel_times, nday_return_rate, prior_counts  # noqa: E402

plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "axes.spines.top": False,
                     "axes.spines.right": False, "figure.dpi": 130, "savefig.bbox": "tight"})
IMG = ROOT / "docs" / "images"
IMG.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "output"
md = []


def table(df, fmt=None):
    fmt = fmt or {}
    d = df.copy()
    for c, f in fmt.items():
        d[c] = d[c].map(lambda x: "-" if pd.isna(x) else f.format(x))
    return d.to_markdown(index=False)


s = pd.read_csv(OUT / "sessions.csv", parse_dates=["session_start_kst"])
ev = pd.read_csv(OUT / "events_flat.csv", parse_dates=["event_ts_kst"], dtype={"transaction_id": str, "session_engaged": str})
it = pd.read_csv(OUT / "items_flat.csv", dtype={"transaction_id": str})
s["channel"] = s.channel_group.where(s.session_medium != "channel_message", "Kakao Message")
first = s[s.ga_session_number == 1].sort_values("session_start_kst").drop_duplicates("user_pseudo_id")
s["user_channel"] = s.user_pseudo_id.map(first.set_index("user_pseudo_id").channel)

C = ["#2b7de0", "#e8673a", "#17a97b", "#9b59b6", "#f0b429", "#7f8c8d", "#d6336c"]
shutil.copy(OUT / "monthly_users.png", IMG / "01_monthly_users.png")
mu = pd.read_csv(OUT / "monthly_users.csv")
md.append("### monthly\n" + table(mu.rename(columns={"month": "월"})))

# ---- 채널 ----
ch = s.groupby("channel").agg(세션=("session_key", "count"), 참여=("engaged_session", "mean"), 구매세션=("purchase", "sum"),
                              매출=("session_revenue", "sum")).reset_index()
ch["세션 비중"] = ch.세션 / ch.세션.sum()
ch["구매 전환율"] = ch.구매세션 / ch.세션
ch["세션당 매출"] = ch.매출 / ch.세션
nu = s[s.ga_session_number == 1].groupby("user_channel").user_pseudo_id.nunique().rename("새 사용자")
ch = ch.merge(nu, left_on="channel", right_index=True, how="left").sort_values("세션", ascending=False)
md.append("### channel\n" + table(ch.rename(columns={"channel": "채널", "참여": "참여 세션 비율"})[
    ["채널", "새 사용자", "세션", "세션 비중", "참여 세션 비율", "구매세션", "구매 전환율", "매출", "세션당 매출"]],
    {"세션 비중": "{:.1%}", "참여 세션 비율": "{:.1%}", "구매 전환율": "{:.1%}", "매출": "{:,.0f}", "세션당 매출": "{:,.0f}", "새 사용자": "{:,.0f}"}))

fig, ax = plt.subplots(1, 3, figsize=(15, 4.3))
o = ch.sort_values("새 사용자")
ax[0].barh(o.channel, o["새 사용자"], color=C[0]); ax[0].set_title("채널별 새 사용자 수 (첫 세션 채널)")
for y, v in enumerate(o["새 사용자"]): ax[0].text(v, y, f" {v:,.0f}", va="center", fontsize=9)
o = ch.sort_values("세션")
ax[1].barh(o.channel, o["세션 비중"] * 100, color=C[1]); ax[1].set_title("채널별 세션 비중 (%)")
for y, (v, n) in enumerate(zip(o["세션 비중"] * 100, o.세션)): ax[1].text(v, y, f" {v:.1f}% ({n:,})", va="center", fontsize=9)
o = ch.sort_values("참여")
ax[2].barh(o.channel, o["참여"] * 100, color=C[2]); ax[2].set_title("유입 품질: 채널별 참여 세션 비율 (%)")
ax[2].set_xlim(0, 100)
for y, v in enumerate(o["참여"] * 100): ax[2].text(v, y, f" {v:.1f}%", va="center", fontsize=9)
fig.tight_layout(); fig.savefig(IMG / "02_acquisition_channels.png"); plt.close(fig)

fig, ax = plt.subplots(1, 3, figsize=(15, 4.3))
o = ch.sort_values("매출", ascending=False)
for a, col, t, f in [(ax[0], "매출", "채널별 매출 (원)", "{:,.0f}"), (ax[1], "구매 전환율", "채널별 구매 전환율 (세션 기준)", "{:.1%}"),
                     (ax[2], "세션당 매출", "채널별 세션당 매출 (원)", "{:,.0f}")]:
    a.bar(o.channel, o[col], color=C[3]); a.set_title(t); a.tick_params(axis="x", rotation=40)
    for x, v in enumerate(o[col]): a.text(x, v, f.format(v), ha="center", va="bottom", fontsize=8)
fig.tight_layout(); fig.savefig(IMG / "03_revenue_by_channel.png"); plt.close(fig)

# ---- 활성화 / 매출 요약 ----
new_s = s[s.ga_session_number == 1]
n_new = new_s.user_pseudo_id.nunique()
eng = ev.groupby("session_key").engagement_time_msec.sum().reindex(s.session_key).fillna(0) / 1000
ords = ev[ev.event_name == "purchase"].drop_duplicates("transaction_id")
rev, n_ord = ords.purchase_revenue.sum(), len(ords)
buyers = s[s.purchase == 1].user_pseudo_id.nunique(); users = s.user_pseudo_id.nunique()
ip = it[it.event_name == "purchase"].copy()
ip["discount"] = ip.price * ip.quantity - ip.item_revenue
ip["has_coupon"] = ip.coupon.notna() & ip.coupon.astype(str).str.strip().ne("") & ip.coupon.ne("(not set)")
kpi = pd.DataFrame([
    ["세션 수", f"{len(s):,}"], ["사용자 수", f"{users:,}"], ["신규 세션 비율", f"{s.is_new_user.mean():.1%}"],
    ["참여 세션 비율", f"{s.engaged_session.mean():.1%}"], ["세션당 페이지뷰", f"{s.pageviews.mean():.2f}"],
    ["세션당 평균 참여 시간", f"{eng.mean():.1f}초"],
    ["신규 사용자 활성화율(첫 세션 상품 조회)", f"{new_s[new_s.view_item == 1].user_pseudo_id.nunique() / n_new:.1%}"],
    ["첫 세션 장바구니 담기율", f"{new_s[new_s.add_to_cart == 1].user_pseudo_id.nunique() / n_new:.1%}"],
    ["구매 전환율(세션)", f"{s.purchase.mean():.2%}"], ["구매 전환율(사용자)", f"{buyers / users:.2%}"],
    ["주문 수", f"{n_ord:,}"], ["매출", f"{rev:,.0f}원"], ["AOV", f"{rev / n_ord:,.0f}원"],
    ["ARPU", f"{rev / users:,.0f}원"], ["ARPPU", f"{rev / buyers:,.0f}원"],
    ["쿠폰 사용률(주문)", f"{ip[ip.has_coupon].transaction_id.nunique() / n_ord:.1%}"], ["할인액 합계", f"{ip.discount.sum():,.0f}원"]],
    columns=["지표", "값"])
md.append("### kpi\n" + table(kpi))

# ---- 카테고리 / 상품 ----
cat = ip.groupby("item_category").item_revenue.sum().sort_values()
fig, ax = plt.subplots(figsize=(8, 4))
ax.barh(cat.index, cat.values, color=C[4]); ax.set_title("카테고리별 상품 매출 (원)")
for y, v in enumerate(cat.values): ax.text(v, y, f" {v:,.0f}", va="center", fontsize=9)
fig.savefig(IMG / "04_revenue_by_category.png"); plt.close(fig)
md.append("### category\n" + table(cat.sort_values(ascending=False).rename("매출").reset_index().rename(columns={"item_category": "대분류"}), {"매출": "{:,.0f}"}))
prod = ip.groupby("item_name").agg(매출=("item_revenue", "sum"), 수량=("quantity", "sum"), 주문수=("transaction_id", "nunique")).reset_index().sort_values("매출", ascending=False).head(10)
md.append("### product\n" + table(prod.rename(columns={"item_name": "상품"}), {"매출": "{:,.0f}"}))

# ---- 결제수단 ----
pay = (ev[ev.event_name == "add_payment_info"].dropna(subset=["payment_type"]).sort_values("event_ts_kst")
       .drop_duplicates("session_key", keep="last")[["session_key", "payment_type", "event_ts_kst"]]
       .merge(s[["session_key", "purchase", "device_category"]], on="session_key"))
pay["post"] = pay.event_ts_kst >= pd.Timestamp("2026-08-20")
pp = pay.groupby("payment_type").agg(결제정보입력=("session_key", "count"), 구매=("purchase", "sum")).reset_index()
pp["전환율"] = pp.구매 / pp.결제정보입력
pp = pp.sort_values("전환율")
fig, ax = plt.subplots(figsize=(8, 4))
ax.barh(pp.payment_type, pp.전환율 * 100, color=C[0]); ax.set_title("결제수단별 전환율 (결제정보 입력 세션 중 같은 세션에서 구매, %)")
for y, (v, a, b) in enumerate(zip(pp.전환율 * 100, pp.구매, pp.결제정보입력)): ax.text(v, y, f" {v:.1f}% ({a}/{b})", va="center", fontsize=9)
fig.savefig(IMG / "05_payment_conversion.png"); plt.close(fig)
md.append("### payment\n" + table(pp.rename(columns={"payment_type": "결제수단"}).sort_values("전환율", ascending=False), {"전환율": "{:.1%}"}))
pm = pay[pay.device_category == "mobile"].groupby("post").agg(입력=("session_key", "count"), 구매=("purchase", "sum")).reset_index()
pm["전환율"] = pm.구매 / pm.입력
pm["시기"] = pm.post.map({False: "간편결제 도입 전(~8/19)", True: "도입 후(8/20~)"})
md.append("### payment_mobile\n" + table(pm[["시기", "입력", "구매", "전환율"]], {"전환율": "{:.1%}"}))

# ---- 퍼널 ----
def funnel_fig(stages, labels, fname, title, color):
    t = funnel_times(ev, stages)
    cnt = [int(t[c].notna().sum()) for c in stages]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    y = np.arange(len(stages))[::-1]
    ax.barh(y, cnt, color=color, height=.65)
    for yi, i in zip(y, range(len(stages))):
        txt = f" {cnt[i]:,} ({cnt[i] / cnt[0]:.1%} of 시작" + (f", 이전 대비 {cnt[i] / cnt[i - 1]:.1%})" if i else ")")
        ax.text(cnt[i], yi, txt, va="center", fontsize=9)
    ax.set_yticks(y); ax.set_yticklabels([labels[c] for c in stages]); ax.set_xlim(0, cnt[0] * 1.55); ax.set_title(title)
    fig.savefig(IMG / fname); plt.close(fig)
    return t, cnt


PL = {"session_start": "세션 시작", "view_item": "상품 상세 조회", "add_to_cart": "장바구니 담기", "begin_checkout": "결제 시작", "purchase": "구매 완료"}
CL = {"begin_checkout": "결제 시작", "add_shipping_info": "배송 정보 입력", "add_payment_info": "결제 정보 입력", "purchase": "구매 완료"}
res = {}
for key, labels, fn, title, col in [("purchase", PL, "06_purchase_funnel.png", "구매 퍼널 (세션 기준)", C[0]),
                                    ("checkout", CL, "07_checkout_funnel.png", "결제 퍼널 (세션 기준)", C[1])]:
    st = list(labels)
    t, cnt = funnel_fig(st, labels, fn, title, col)
    pc = prior_counts(ev, t, st)
    rows = [{"단계": labels[c], "세션 수": n, "첫 단계 대비": n / cnt[0], "이전 단계 대비": (n / cnt[i - 1] if i else 1.0),
             "이탈 세션": (cnt[i - 1] - n if i else 0)} for i, (c, n) in enumerate(zip(st, cnt))]
    md.append(f"### funnel_{key}\n" + table(pd.DataFrame(rows), {"세션 수": "{:,}", "첫 단계 대비": "{:.1%}", "이전 단계 대비": "{:.1%}", "이탈 세션": "{:,}"}))
    r1 = [{"다음 단계": labels[c], "직전 단계": labels[st[st.index(c) - 1]], "도달 세션": len(v), "평균 횟수": v.mean(), "중앙값": v.median(),
           "1회": (v == 1).mean(), "2~3회": v.between(2, 3).mean(), "4회 이상": (v >= 4).mean()} for c, v in pc.items()]
    md.append(f"### prior_{key}\n" + table(pd.DataFrame(r1), {"평균 횟수": "{:.2f}", "중앙값": "{:.0f}", "1회": "{:.1%}", "2~3회": "{:.1%}", "4회 이상": "{:.1%}"}))
    r2, dist = [], {}
    for a, b in zip(st, st[1:]):
        d = (t[b] - t[a]).dt.total_seconds().dropna()
        dist[f"{labels[a]}\n→ {labels[b]}"] = d
        r2.append({"구간": f"{labels[a]} → {labels[b]}", "세션 수": len(d), "평균(초)": d.mean(), "중앙값(초)": d.median(), "75%(초)": d.quantile(.75)})
    md.append(f"### time_{key}\n" + table(pd.DataFrame(r2), {"평균(초)": "{:,.0f}", "중앙값(초)": "{:,.0f}", "75%(초)": "{:,.0f}"}))
    res[key] = (pc, dist, st, labels)

fig, ax = plt.subplots(1, 2, figsize=(14, 4.5))
for a, key, ttl in [(ax[0], "purchase", "구매 퍼널: 다음 단계까지 걸린 시간(초, 로그 축)"), (ax[1], "checkout", "결제 퍼널: 다음 단계까지 걸린 시간(초, 로그 축)")]:
    dist = res[key][1]
    a.boxplot([d.clip(lower=0.5) for d in dist.values()], tick_labels=list(dist.keys()), showmeans=True)
    a.set_yscale("log"); a.set_title(ttl, fontsize=11); a.tick_params(axis="x", labelsize=8)
fig.tight_layout(); fig.savefig(IMG / "08_funnel_time_to_next.png"); plt.close(fig)

fig, ax = plt.subplots(1, 2, figsize=(14, 4))
for a, key, ttl in [(ax[0], "purchase", "구매 퍼널: 다음 단계 전 직전 단계 수행 횟수(평균)"), (ax[1], "checkout", "결제 퍼널: 다음 단계 전 직전 단계 수행 횟수(평균)")]:
    pc, _, st, labels = res[key]
    names = [f"{labels[st[st.index(c) - 1]]}\n→ {labels[c]}" for c in pc]
    vals = [v.mean() for v in pc.values()]
    a.bar(names, vals, color=C[2]); a.set_title(ttl, fontsize=11); a.tick_params(axis="x", labelsize=8)
    for x, v in enumerate(vals): a.text(x, v, f"{v:.2f}", ha="center", va="bottom", fontsize=9)
fig.tight_layout(); fig.savefig(IMG / "09_funnel_prior_counts.png"); plt.close(fig)

# ---- 리텐션 ----
firsts = first_sessions(s.rename(columns={}))
v = day_offsets(firsts, s)
last_day = DATA_END.normalize()
fday = firsts.first_ts.dt.normalize()
rows = []
for n in range(1, 31):
    obs = fday + pd.Timedelta(days=n) <= last_day
    base = int(obs.sum())
    u = v[(v.n == n) & v.user_pseudo_id.isin(firsts[obs].user_pseudo_id)].user_pseudo_id.nunique()
    rows.append({"N일": n, "방문 사용자": u, "관찰 가능 사용자": base, "재방문율": u / base})
cur = pd.DataFrame(rows)
fig, ax = plt.subplots(figsize=(11, 4.5))
ax.bar(cur["N일"], cur["방문 사용자"], color="#9ecae1", label="방문 사용자 수")
ax.set_xlabel("첫 방문 후 경과일 (N일)"); ax.set_ylabel("방문 사용자 수")
ax2 = ax.twinx(); ax2.plot(cur["N일"], cur["재방문율"] * 100, color="#d62728", marker="o", label="재방문 %")
ax2.set_ylabel("재방문 %"); ax2.spines["right"].set_visible(True); ax2.set_ylim(0)
for x, y in zip(cur["N일"][:3], cur["재방문율"][:3] * 100): ax2.annotate(f"{y:.1f}%", (x, y), textcoords="offset points", xytext=(5, 6), fontsize=9)
ax.set_title("N일 리텐션 곡선 (0일=첫 방문 100%는 제외)")
fig.legend(loc="upper right", bbox_to_anchor=(.88, .86)); fig.savefig(IMG / "10_retention_curve.png"); plt.close(fig)
md.append("### retention_curve\n" + table(cur.head(14), {"재방문율": "{:.1%}"}))

rr = []
for n in (7, 14, 30):
    r, o_, b_ = nday_return_rate(firsts, s, n)
    rr.append({"N": f"{n}일 내 재방문", "재방문율": r, "재방문 사용자": o_, "관찰 가능 새 사용자": b_})
md.append("### retention_n\n" + table(pd.DataFrame(rr), {"재방문율": "{:.1%}"}))
rc = []
for c, f in firsts.groupby("channel"):
    r, o_, b_ = nday_return_rate(f, s, 30)
    rc.append({"채널": c, "30일 재방문율": r, "재방문 사용자": o_, "관찰 가능 새 사용자": b_})
rc = pd.DataFrame(rc).sort_values("30일 재방문율")
fig, ax = plt.subplots(figsize=(8, 4))
ax.barh(rc.채널, rc["30일 재방문율"] * 100, color=C[5]); ax.set_title("채널별 30일 재방문율 (첫 세션 채널, %)")
for y, x in enumerate(rc["30일 재방문율"] * 100): ax.text(x, y, f" {x:.1f}%", va="center", fontsize=9)
fig.savefig(IMG / "11_retention_by_channel.png"); plt.close(fig)
md.append("### retention_channel\n" + table(rc.sort_values("30일 재방문율", ascending=False), {"30일 재방문율": "{:.1%}"}))


def heat(unit, fname, title, size):
    vv = v[(v.n >= 0) & (v.n <= 30)].copy()
    if unit == "W":
        vv["coh"] = vv.cohort.dt.to_period("W-SUN").dt.start_time
        f2 = firsts.assign(coh=firsts.first_ts.dt.to_period("W-SUN").dt.start_time)
        tail = pd.Timedelta(days=6)
    else:
        vv["coh"] = vv.cohort; f2 = firsts.assign(coh=firsts.first_ts.dt.normalize()); tail = pd.Timedelta(days=0)
    sz = f2.groupby("coh").size()
    act = vv.groupby(["coh", "n"]).user_pseudo_id.nunique().unstack(fill_value=0).reindex(sz.index, fill_value=0).reindex(columns=range(31), fill_value=0)
    mat = act.div(sz, axis=0) * 100
    for n in mat.columns:
        mat.loc[(pd.Series(mat.index, index=mat.index) + tail + pd.Timedelta(days=int(n))) > last_day, n] = np.nan
    fig, ax = plt.subplots(figsize=size)
    arr = mat.values.copy(); arr[:, 0] = np.nan  # 0일(100%)은 색 범위를 위해 제외
    im = ax.imshow(arr, aspect="auto", cmap="Blues", vmin=0, vmax=np.nanpercentile(arr[:, 1:], 98))
    ax.set_xticks(range(31)); ax.set_xticklabels(range(31), fontsize=7)
    ax.set_yticks(range(len(mat))); ax.set_yticklabels([d.strftime("%m-%d") + f" (n={sz[d]})" for d in mat.index], fontsize=7)
    ax.set_xlabel("첫 방문 후 경과일 (N일)"); ax.set_ylabel("첫 방문일(코호트)" if unit == "D" else "첫 방문 주(월요일)")
    ax.set_title(title)
    if unit == "W":
        for i in range(mat.shape[0]):
            for j in range(1, 31):
                if not np.isnan(mat.values[i, j]):
                    ax.text(j, i, f"{mat.values[i, j]:.0f}", ha="center", va="center", fontsize=6, color="black")
    fig.colorbar(im, ax=ax, label="재방문 %"); fig.savefig(IMG / fname); plt.close(fig)
    return mat, sz


heat("W", "12_retention_cohort_weekly.png", "N일 리텐션 코호트 히트맵 (주 단위 코호트, 숫자=%)", (13, 5))
heat("D", "13_retention_cohort_daily.png", "N일 리텐션 코호트 히트맵 (일 단위 코호트)", (13, 16))

# ---- 퍼널 외: 데이터 요약 표 ----
evc = ev.event_name.value_counts().rename_axis("이벤트").reset_index(name="건수")
evc["비중"] = evc.건수 / evc.건수.sum()
md.append("### events\n" + table(evc, {"건수": "{:,}", "비중": "{:.1%}"}))
mis = ((ev.isna().mean() * 100).round(1)).rename("결측 %").reset_index().rename(columns={"index": "컬럼"})
md.append("### missing\n" + table(mis))
Path(ROOT / "docs" / "_tables.md").write_text("\n\n".join(md), encoding="utf-8")
print("완료", sorted(p.name for p in IMG.iterdir()))
