
import streamlit as st
import requests
import pandas as pd

st.title("📊 Stock Portfolio Analyzer")

uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

if uploaded_file:
    res = requests.post("http://127.0.0.1:8000/upload/", files={"file": uploaded_file})

    if res.status_code == 200:
        st.success("Uploaded successfully!")

        analysis = requests.get("http://127.0.0.1:8000/analysis/").json()

        st.subheader("Portfolio Summary")
        st.write(f"Investment: ₹{analysis['investment']}")
        st.write(f"Current Value: ₹{analysis['current_value']}")
        st.write(f"Profit: ₹{analysis['profit']}")

        df = pd.DataFrame({
            "Metric": ["Investment", "Current Value"],
            "Value": [analysis['investment'], analysis['current_value']]
        })

        st.bar_chart(df.set_index("Metric"))
    else:
        st.error("Upload failed")
