import sys
import pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.stdout.reconfigure(encoding="utf-8")
plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False

ev = pd.read_csv("output/events_flat.csv", parse_dates=["event_ts_kst"])
s = pd.read_csv("output/sessions.csv", parse_dates=["session_start_kst"])
ev["month"] = ev.event_ts_kst.dt.to_period("M").astype(str)
s["month"] = s.session_start_kst.dt.to_period("M").astype(str)

print("[추천 기준]\n사용자=고유 user_pseudo_id, 세션=user_pseudo_id+'_'+ga_session_id (ga_session_id 단독은 사용자 간 중복 가능)")
print(f"전체 기간: 사용자 {ev.user_pseudo_id.nunique():,}명 / 세션 {ev.session_key.nunique():,}개")
print(f"(참고) ga_session_id만 세면 {ev.ga_session_id.nunique():,}개, user_id 기준 로그인 사용자 {ev.user_id.nunique()}명")

first_month = ev.groupby("user_pseudo_id").month.min()
eng = ev.groupby(["month", "user_pseudo_id"]).engagement_time_msec.sum().reset_index()
total = ev.groupby("month").user_pseudo_id.nunique()
active_users = eng[eng.engagement_time_msec >= 3000]
active = active_users.groupby("month").user_pseudo_id.nunique()
new = active_users[active_users.month == active_users.user_pseudo_id.map(first_month)].groupby("month").user_pseudo_id.nunique()
sess = s.groupby("month").session_key.nunique()
t = pd.DataFrame({"전체 사용자": total, "활성 사용자": active, "새 사용자": new, "세션": sess}).fillna(0).astype(int)
print("\n[월별]"); print(t.to_string())
print(f"월별 사용자 합 {t['전체 사용자'].sum():,} ≠ 전체 기간 고유 사용자 {ev.user_pseudo_id.nunique():,} (월 간 중복)")
t.to_csv("output/monthly_users.csv", encoding="utf-8-sig")

fig, ax = plt.subplots(figsize=(8, 4.5))
for c, m in [("전체 사용자", "o"), ("활성 사용자", "s"), ("새 사용자", "^")]:
    ax.plot(t.index, t[c], marker=m, lw=2, label=c)
    for x, y in zip(t.index, t[c]): ax.annotate(f"{y:,}", (x, y), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=9)
ax.set_title("월별 사용자 수 (활성: 월 참여시간 3초 이상, 새 사용자: 활성 사용자 중 첫 관측 월)")
ax.set_ylim(0); ax.grid(alpha=.3); ax.legend(); ax.set_ylabel("사용자 수")
fig.tight_layout(); fig.savefig("output/monthly_users.png", dpi=150)
