import streamlit as st
from common import load, sidebar_filters, render_funnel

st.set_page_config(page_title="결제 퍼널", layout="wide")
s, ev, it = load()
s_f, _ = sidebar_filters(s)
labels = {"begin_checkout": "결제 시작", "add_shipping_info": "배송 정보 입력",
          "add_payment_info": "결제 정보 입력", "purchase": "구매 완료"}
render_funnel("결제 퍼널", list(labels), labels, ev, s_f,
              "결제를 시작한 세션이 배송, 결제수단, 구매까지 가는 과정입니다. 모바일 간편결제 도입일(2026-08-20) 전후는 기간 필터로 비교해 보세요.")
