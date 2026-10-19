import json, glob
import pandas as pd

files = sorted(glob.glob("data/lite/*.json"))
raw = []
for f in files:
    with open(f, encoding="utf-8") as fh:
        raw += [json.loads(l) for l in fh if l.strip()]
n_raw = len(raw)

def param(params, key):
    for p in params or []:
        if p["key"] == key:
            v = p["value"]
            for k in ("string_value", "int_value", "double_value", "float_value"):
                if v.get(k) is not None:
                    return v[k]
    return None

NUM = ["ga_session_id", "ga_session_number", "engagement_time_msec", "value"]
STR = ["page_location", "page_title", "session_engaged", "transaction_id", "payment_type", "search_term"]

rows, items = [], []
for r in raw:
    ep = r.get("event_params")
    d, g, ts = r.get("device") or {}, r.get("geo") or {}, r.get("traffic_source") or {}
    cc = (r.get("session_traffic_source_last_click") or {}).get("cross_channel_campaign") or {}
    ec = r.get("ecommerce") or {}
    row = {"event_date": r["event_date"], "event_name": r["event_name"],
           "user_pseudo_id": r["user_pseudo_id"], "user_id": r.get("user_id"),
           "event_timestamp": r["event_timestamp"]}
    for k in NUM + STR:
        row[k] = param(ep, k)
    row.update(device_category=d.get("category"), operating_system=d.get("operating_system"),
               browser=(d.get("web_info") or {}).get("browser"), region=g.get("region"), city=g.get("city"),
               first_source=ts.get("source"), first_medium=ts.get("medium"), first_campaign=ts.get("name"),
               session_source=cc.get("source"), session_medium=cc.get("medium"),
               session_campaign=cc.get("campaign_name"), channel_group=cc.get("default_channel_group"),
               purchase_revenue=ec.get("purchase_revenue"), shipping_value=ec.get("shipping_value"),
               refund_value=ec.get("refund_value"))
    rows.append(row)
    for it in r.get("items") or []:
        items.append({"event_date": r["event_date"], "event_name": r["event_name"],
                      "user_pseudo_id": r["user_pseudo_id"], "ga_session_id": param(ep, "ga_session_id"),
                      "transaction_id": param(ep, "transaction_id") or ec.get("transaction_id"),
                      **{k: it.get(k) for k in ["item_id","item_name","item_brand","item_category","item_category2",
                                                "item_variant","price","quantity","item_revenue","coupon"]}})

ev = pd.DataFrame(rows)
for c in NUM:
    ev[c] = pd.to_numeric(ev[c], errors="coerce")
for c in ["purchase_revenue", "shipping_value", "refund_value"]:
    ev[c] = pd.to_numeric(ev[c], errors="coerce")
ev["event_ts_kst"] = (pd.to_datetime(pd.to_numeric(ev.pop("event_timestamp")), unit="us", utc=True)
                      .dt.tz_convert("Asia/Seoul").dt.tz_localize(None))
ev["session_key"] = ev["user_pseudo_id"] + "_" + ev["ga_session_id"].astype("Int64").astype(str)
ev.loc[ev["ga_session_id"].isna(), "session_key"] = None
cols = ["event_date","event_name","user_pseudo_id","user_id","event_ts_kst","ga_session_id","ga_session_number",
        "page_location","page_title","engagement_time_msec","session_engaged","value","transaction_id","payment_type",
        "search_term","session_key","device_category","operating_system","browser","region","city","first_source",
        "first_medium","first_campaign","session_source","session_medium","session_campaign","channel_group",
        "purchase_revenue","shipping_value","refund_value"]
ev = ev[cols]
print(f"원본 이벤트 {n_raw:,} / events_flat {len(ev):,} / 일치={n_raw==len(ev)}")
print("\n[컬럼별 결측 비율 %]"); print((ev.isna().mean()*100).round(1).to_string())
ev.to_csv("output/events_flat.csv", index=False, encoding="utf-8-sig")

# items_flat
it = pd.DataFrame(items)
it["session_key"] = it["user_pseudo_id"] + "_" + it["ga_session_id"].astype("Int64").astype(str)
icols = ["event_date","event_name","session_key","transaction_id","item_id","item_name","item_brand","item_category",
         "item_category2","item_variant","price","quantity","item_revenue","coupon"]
it = it[icols]
it.to_csv("output/items_flat.csv", index=False, encoding="utf-8-sig")
print(f"\nitems_flat {len(it):,}행, 이벤트별:\n{it.event_name.value_counts().to_string()}")
pur = ev[ev.event_name=="purchase"]
a, b = it[it.event_name=="purchase"].item_revenue.sum(), pur.purchase_revenue.sum()
print(f"\npurchase: items item_revenue 합 {a:,.0f} vs purchase_revenue 합 {b:,.0f} (차이 {b-a:,.0f}), 구매 {len(pur)}건")
tx = it[it.event_name=="purchase"].groupby("transaction_id").item_revenue.sum()
m = pur.set_index("transaction_id").purchase_revenue.to_frame().join(tx.rename("items_sum"))
m["diff"] = m.purchase_revenue - m.items_sum
print("건별 차이 있는 구매:", (m["diff"].abs()>0.5).sum(), "/ 중복 transaction_id:", pur.transaction_id.duplicated().sum())
print(m[m["diff"].abs()>0.5].head(10).to_string())

# sessions
e = ev.dropna(subset=["session_key"]).sort_values("event_ts_kst")
g = e.groupby("session_key")
s = g.agg(user_pseudo_id=("user_pseudo_id","first"), session_start_kst=("event_ts_kst","min"),
          ga_session_number=("ga_session_number","first"), device_category=("device_category","first"),
          channel_group=("channel_group","first"), session_source=("session_source","first"),
          session_medium=("session_medium","first"), session_campaign=("session_campaign","first"),
          session_revenue=("purchase_revenue","sum")).reset_index()
s["session_date"] = s.session_start_kst.dt.date
s["is_new_user"] = s.ga_session_number == 1
for n in ["view_item","add_to_cart","begin_checkout","add_shipping_info","add_payment_info","purchase"]:
    s[n] = s.session_key.isin(e[e.event_name==n].session_key).astype(int)
s["pageviews"] = s.session_key.map(e[e.event_name=="page_view"].groupby("session_key").size()).fillna(0).astype(int)
s["engaged_session"] = s.session_key.isin(e[e.session_engaged.astype(str)=="1"].session_key).astype(int)
s = s[["session_key","user_pseudo_id","session_start_kst","session_date","ga_session_number","is_new_user","device_category",
       "channel_group","session_source","session_medium","session_campaign","view_item","add_to_cart","begin_checkout",
       "add_shipping_info","add_payment_info","purchase","session_revenue","pageviews","engaged_session"]]
s.to_csv("output/sessions.csv", index=False, encoding="utf-8-sig")
print(f"\n세션 수 {len(s):,} / 신규 세션 비율 {s.is_new_user.mean():.1%} / 참여 세션 비율 {s.engaged_session.mean():.1%} / 세션당 PV {s.pageviews.mean():.2f}")
print(f"사용자 수 {s.user_pseudo_id.nunique():,} / 구매 세션 {s.purchase.sum()} / 전환율 {s.purchase.mean():.2%}")
