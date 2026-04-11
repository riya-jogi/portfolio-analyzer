"""
Streamlit UI for Stock Portfolio Analyzer — talks to Django REST API.
Set API_BASE_URL via environment variable or .streamlit/secrets.toml
"""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import pandas as pd
import requests
import streamlit as st

DEFAULT_API = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")


def api_base() -> str:
    try:
        return st.secrets.get("API_BASE_URL", DEFAULT_API)
    except Exception:
        return DEFAULT_API


def main():
    st.set_page_config(page_title="Stock Portfolio Analyzer", layout="wide")
    st.title("Stock Portfolio Analyzer")

    if "token" not in st.session_state:
        st.session_state.token = None

    base = api_base().rstrip("/")
    st.sidebar.markdown(f"**API:** `{base}`")

    with st.sidebar:
        st.subheader("Account")
        tab_reg, tab_log = st.tabs(["Register", "Login"])
        with tab_reg:
            e1 = st.text_input("Email (register)", key="r_email")
            n1 = st.text_input("Name", key="r_name")
            p1 = st.text_input("Password", type="password", key="r_pw")
            if st.button("Register"):
                try:
                    r = requests.post(
                        f"{base}/api/auth/register/",
                        json={"email": e1, "name": n1, "password": p1},
                        timeout=60,
                    )
                    data = r.json()
                    if r.ok and data.get("token"):
                        st.session_state.token = data["token"]
                        st.success("Registered and logged in.")
                    else:
                        st.error(data.get("errors") or data.get("error") or data)
                except requests.RequestException as ex:
                    st.error(f"Request failed: {ex}")

        with tab_log:
            e2 = st.text_input("Email (login)", key="l_email")
            p2 = st.text_input("Password ", type="password", key="l_pw")
            if st.button("Login"):
                try:
                    r = requests.post(
                        f"{base}/api/auth/login/",
                        json={"email": e2, "password": p2},
                        timeout=60,
                    )
                    data = r.json()
                    if r.ok and data.get("token"):
                        st.session_state.token = data["token"]
                        st.success("Logged in.")
                    else:
                        st.error(data.get("error") or data)
                except requests.RequestException as ex:
                    st.error(f"Request failed: {ex}")

        if st.session_state.token and st.button("Logout"):
            st.session_state.token = None
            st.rerun()

    if not st.session_state.token:
        st.info("Register or log in from the sidebar to upload a portfolio and view analysis.")
        return

    headers = {"Authorization": f"Token {st.session_state.token}"}

    st.subheader("Upload portfolio (CSV)")
    st.caption("Columns: `stock_name`, `quantity`, `buy_price`, `buy_date` — upload replaces your saved holdings.")
    up = st.file_uploader("CSV file", type=["csv"])
    if up is not None and st.button("Upload and replace portfolio"):
        try:
            files = {"file": (up.name, up.getvalue(), "text/csv")}
            r = requests.post(f"{base}/upload/", files=files, headers=headers, timeout=120)
            data = r.json()
            if r.ok:
                st.success(data.get("message", "OK"))
                st.json(data)
            else:
                st.error(data.get("error", data))
        except requests.RequestException as ex:
            st.error(f"Upload failed: {ex}")

    st.subheader("Analysis")
    if st.button("Refresh analysis"):
        st.session_state.pop("_analysis_cache", None)

    try:
        r = requests.get(f"{base}/analysis/", headers=headers, timeout=120)
        data = r.json()
    except requests.RequestException as ex:
        st.error(f"Analysis request failed: {ex}")
        return

    if not r.ok:
        st.error(data.get("detail") or data)
        return

    if not data.get("success"):
        st.warning(data)
        return

    summ = data.get("summary") or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total investment", f"{summ.get('total_investment', 0)}")
    c2.metric("Current value (priced)", f"{summ.get('current_value', 0)}")
    c3.metric("Profit / Loss", f"{summ.get('profit_loss', 0)}")
    plp = summ.get("profit_loss_percent")
    c4.metric("P/L %", f"{plp}" if plp is not None else "—")

    xirr = summ.get("xirr")
    xerr = summ.get("xirr_error")
    if xirr is not None:
        st.metric("Portfolio XIRR (annualized)", f"{float(xirr) * 100:.4f}%")
    elif xerr:
        st.caption(f"XIRR: — ({xerr})")

    st.caption(
        f"Priced lots: {summ.get('priced_holdings_count', 0)} / {summ.get('total_holdings_count', 0)}"
    )

    stocks = data.get("stocks") or []
    if stocks:
        df = pd.DataFrame(stocks)
        st.subheader("Holdings table")
        st.dataframe(df, use_container_width=True)

        st.subheader("Bar chart — current value by line (where price known)")
        plot_df = df[df["price_available"] == True] if "price_available" in df.columns else df
        if not plot_df.empty and "current_value" in plot_df.columns:
            fig, ax = plt.subplots(figsize=(10, max(3, len(plot_df) * 0.35)))
            labels = plot_df["stock_name"].astype(str)
            vals = plot_df["current_value"].fillna(0).astype(float)
            ax.barh(labels, vals, color="steelblue")
            ax.set_xlabel("Current value")
            ax.invert_yaxis()
            plt.tight_layout()
            st.pyplot(fig)
            plt.close(fig)
        else:
            st.warning("No priced rows to chart.")

    st.divider()
    st.caption("Backend: Django + DRF | Data: yfinance | IRR: pyxirr")


if __name__ == "__main__":
    main()
