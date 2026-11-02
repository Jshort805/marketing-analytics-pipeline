"""Shared helpers for the multi-page app."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

DATA = Path(__file__).parent / "data"

CH_COLORS = {
    "google_search": "#2a6fdb", "meta_facebook": "#7b4fd6", "meta_instagram": "#d9489a",
    "tiktok_ads": "#16a39a", "display_network": "#e08a1e", "affiliate": "#8a6d3b",
    "email": "#5aa02c", "organic_search": "#3b9ac7", "direct": "#8b95a5", "unattributed": "#c8ced8",
}
MODEL_LABELS = {
    "first": "First touch", "last": "Last touch", "linear": "Linear",
    "position": "Position-based (40/20/40)", "decay": "Time decay (7-day half-life)",
}


@st.cache_data
def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA / f"{name}.parquet")


@st.cache_data
def load_json(name: str) -> dict:
    return json.loads((DATA / f"{name}.json").read_text())


def have(name: str) -> bool:
    return (DATA / f"{name}.parquet").exists() or (DATA / f"{name}.json").exists()


def setup(title: str, icon: str = "📊"):
    st.set_page_config(page_title=f"{title} | Marketing Analytics", page_icon=icon, layout="wide")
    st.markdown(
        "<style>.block-container{padding-top:2rem;max-width:1250px}"
        "div[data-testid=stMetric]{background:rgba(120,130,150,.08);padding:.7rem .9rem;border-radius:10px}"
        "</style>", unsafe_allow_html=True)
    try:
        meta = load_json("pipeline_meta")
        st.sidebar.caption(f"Data refreshed {meta['generated_at']}  \nSynthetic data, for demonstration")
    except Exception:
        pass


def note(text: str, kind: str = "info"):
    """st.info / warning with dollar signs escaped so they do not render as math."""
    getattr(st, kind)(text.replace("$", "\\$"))


def md(text: str):
    st.markdown(text.replace("$", "\\$"))


def money(x, d: int = 0) -> str:
    if pd.isna(x):
        return "n/a"
    return f"${x:,.{d}f}"


def dates_filter(df_dates: pd.Series, key: str):
    d0, d1 = df_dates.min().date(), df_dates.max().date()
    rng = st.sidebar.date_input("Order dates", (d0, d1), min_value=d0, max_value=d1, key=key)
    if not isinstance(rng, (tuple, list)) or len(rng) != 2:
        st.sidebar.info("Pick an end date.")
        st.stop()
    return pd.Timestamp(rng[0]), pd.Timestamp(rng[1])
