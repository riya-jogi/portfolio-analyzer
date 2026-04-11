"""
Streamlit UI for Stock Portfolio Analyzer — talks to Django REST API.
Set API_BASE_URL via environment variable or .streamlit/secrets.toml
"""

from __future__ import annotations

import logging
import os

import matplotlib.pyplot as plt
import pandas as pd
import requests
import streamlit as st

# Streamlit 1.56 still logs deprecation warnings to the console even when using `width=`;
# our app does not pass `use_container_width`. Quiet that logger to keep the terminal clean.
logging.getLogger("streamlit.deprecation_util").setLevel(logging.ERROR)

DEFAULT_API = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")


def api_base() -> str:
    try:
        return st.secrets.get("API_BASE_URL", DEFAULT_API)
    except Exception:
        return DEFAULT_API


def _fmt_pct(val) -> str:
    if val is None:
        return "—"
    try:
        return f"{float(val):.4f}%"
    except (TypeError, ValueError):
        return "—"


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
            st.session_state.pop("analysis_data", None)
            st.rerun()

    if not st.session_state.token:
        st.info("Register or log in from the sidebar to upload a portfolio and view analysis.")
        return

    headers = {"Authorization": f"Token {st.session_state.token}"}

    st.subheader("Upload portfolio (CSV)")
    st.caption(
        "Columns: `stock_name`, `quantity`, `buy_price`, `buy_date` — upload replaces your saved holdings."
    )
    up = st.file_uploader("CSV file", type=["csv"])
    if up is not None and st.button("Upload and replace portfolio"):
        try:
            files = {"file": (up.name, up.getvalue(), "text/csv")}
            r = requests.post(f"{base}/upload/", files=files, headers=headers, timeout=120)
            data = r.json()
            if r.ok:
                st.session_state.pop("analysis_data", None)
                st.success(data.get("message", "OK"))
                st.json(data)
            else:
                st.error(data.get("error", data))
        except requests.RequestException as ex:
            st.error(f"Upload failed: {ex}")

    st.subheader("Analysis")
    if st.button("Refresh analysis"):
        st.session_state.pop("analysis_data", None)
        st.rerun()

    if "analysis_data" not in st.session_state:
        try:
            r = requests.get(f"{base}/analysis/", headers=headers, timeout=120)
            payload = r.json()
        except requests.RequestException as ex:
            st.error(f"Analysis request failed: {ex}")
            return
        if not r.ok:
            st.error(payload.get("detail") or payload)
            return
        st.session_state.analysis_data = payload

    data = st.session_state.analysis_data

    if not data.get("success"):
        st.warning(data)
        return

    summ = data.get("summary") or {}
    missing_n = data.get("missing_price_count", 0)

    # KPI row
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Investment", f"{summ.get('total_investment', 0)}")
    c2.metric("Current value", f"{summ.get('current_value', 0)}")
    c3.metric("Profit / Loss", f"{summ.get('profit_loss', 0)}")
    c4.metric("Loss %", _fmt_pct(summ.get("loss_percent")))
    c5.metric("Recovery %", _fmt_pct(summ.get("recovery_needed_percent")))

    plp = summ.get("profit_loss_percent")
    st.caption(f"Portfolio P/L %: {_fmt_pct(plp)}")

    xirr = summ.get("xirr")
    xerr = summ.get("xirr_error")
    if xirr is not None:
        st.metric("Portfolio XIRR (annualized)", f"{float(xirr) * 100:.4f}%")
    elif xerr:
        st.caption(f"XIRR: — ({xerr})")

    st.caption(
        f"Priced lots: {summ.get('priced_holdings_count', 0)} / {summ.get('total_holdings_count', 0)}"
    )

    if missing_n and missing_n > 0:
        st.error(
            f"Missing live price for {missing_n} holding line(s). "
            "P/L and totals exclude unknown quotes where applicable."
        )

    insights = data.get("insights") or []
    if insights:
        st.subheader("Insights")
        for msg in insights:
            st.error(msg)

    holdings = data.get("holdings") or []
    top_gainers = data.get("top_gainers") or []
    top_losers = data.get("top_losers") or []

    if top_gainers:
        st.subheader("Top gainers")
        st.dataframe(data=pd.DataFrame(top_gainers))
    if top_losers:
        st.subheader("Top losers")
        st.dataframe(data=pd.DataFrame(top_losers))

    if holdings:
        df = pd.DataFrame(holdings)

        st.subheader("Holdings")
        search = st.text_input("Search by stock name", key="hold_search")
        filt = st.selectbox("Filter", ["All", "Profit", "Loss"], key="hold_filter")

        view = df.copy()
        if search.strip():
            q = search.strip().lower()
            view = view[view["stock_name"].astype(str).str.lower().str.contains(q, na=False)]
        if filt == "Profit":
            view = view[view["profit_loss"].notna() & (view["profit_loss"] > 0)]
        elif filt == "Loss":
            view = view[view["profit_loss"].notna() & (view["profit_loss"] < 0)]

        if "profit_loss" in view.columns:
            try:
                styler = view.style.map(
                    lambda v: (
                        "color: #1e7e34; font-weight: 600"
                        if pd.notna(v) and float(v) > 0
                        else (
                            "color: #c62828; font-weight: 600"
                            if pd.notna(v) and float(v) < 0
                            else ""
                        )
                    ),
                    subset=["profit_loss"],
                )
                st.dataframe(data=styler)
            except Exception:
                st.dataframe(data=view)
        else:
            st.dataframe(data=view)

        # Diversification: top 5 stocks by value (aggregate by name), rest as Others
        priced = df[df.get("price_available", False) == True].copy()  # noqa: E712
        if not priced.empty and "current_value" in priced.columns:
            by_name = (
                priced.groupby("stock_name", as_index=False)["current_value"]
                .sum()
                .sort_values("current_value", ascending=False)
            )
            st.subheader("Diversification (top 5 + Others)")
            if len(by_name) > 5:
                top5 = by_name.head(5)
                other_val = by_name.iloc[5:]["current_value"].astype(float).sum()
                labels = list(top5["stock_name"].astype(str)) + ["Others"]
                sizes = list(top5["current_value"].astype(float)) + [other_val]
            else:
                labels = list(by_name["stock_name"].astype(str))
                sizes = list(by_name["current_value"].astype(float))
            fig, ax = plt.subplots(figsize=(6, 6))
            ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=90)
            ax.axis("equal")
            plt.tight_layout()
            st.pyplot(fig, clear_figure=False)
            plt.close(fig)

        st.subheader("Bar chart — current value by line (where price known)")
        plot_df = df[df["price_available"] == True] if "price_available" in df.columns else df  # noqa: E712
        if not plot_df.empty and "current_value" in plot_df.columns:
            fig, ax = plt.subplots(figsize=(10, max(3, len(plot_df) * 0.35)))
            labels = plot_df["stock_name"].astype(str)
            vals = plot_df["current_value"].fillna(0).astype(float)
            ax.barh(labels, vals, color="steelblue")
            ax.set_xlabel("Current value")
            ax.invert_yaxis()
            plt.tight_layout()
            st.pyplot(fig, clear_figure=False)
            plt.close(fig)
        else:
            st.warning("No priced rows to chart.")

    st.divider()
    st.caption("Backend: Django + DRF | Data: yfinance | IRR: pyxirr")


if __name__ == "__main__":
    main()
