import streamlit as st
from common import load, sidebar_filters, render_funnel

st.set_page_config(page_title="구매 퍼널", layout="wide")
s, ev, it = load()
s_f, _ = sidebar_filters(s)
labels = {"session_start": "세션 시작", "view_item": "상품 상세 조회", "add_to_cart": "장바구니 담기",
          "begin_checkout": "결제 시작", "purchase": "구매 완료"}
with st.expander("퍼널 단계 5가지 추천 이유"):
    st.markdown("""
1. **세션 시작**: 모든 방문의 분모
2. **상품 상세 조회(view_item)**: 구매 의도가 생긴 시점
3. **장바구니 담기(add_to_cart)**: 구매 의도가 행동으로 확인되는 시점
4. **결제 시작(begin_checkout)**: 장바구니에서 실제 결제로 넘어간 시점
5. **구매 완료(purchase)**: 최종 전환

단계 사이 이탈은 각각 상품 매력, 담기 망설임, 결제 진입 장벽, 결제 마찰로 해석할 수 있습니다.
결제 시작 이후의 세부 단계는 '결제 퍼널' 페이지에서 따로 봅니다.
""")
render_funnel("구매 퍼널", list(labels), labels, ev, s_f,
              "세션 기준이며, 단계 순서대로 발생한 세션만 다음 단계로 셉니다. 왼쪽 필터가 적용됩니다.")
