import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from utils import CH_COLORS, dates_filter, load, load_json, md, money, note, setup

setup("Overview", "📊")
orders, spend, cp = load("orders"), load("daily_spend"), load("channel_performance")
meta = load_json("pipeline_meta")
paid = set(cp.loc[cp["is_paid"], "channel"])

st.title("Marketing performance overview")
st.caption("Every number here is read from the dbt marts built in this repo, via precomputed files in app/data. "
           "Use the sidebar filters; the other pages go deeper on attribution, customer value and budget.")

lo, hi = dates_filter(orders["order_date"], "home_dates")
countries = st.sidebar.multiselect("Country", sorted(orders["country"].unique()))
devices = st.sidebar.multiselect("Device", sorted(orders["device_type"].unique()))

o = orders[(orders["order_date"] >= lo) & (orders["order_date"] <= hi)]
if countries:
    o = o[o["country"].isin(countries)]
if devices:
    o = o[o["device_type"].isin(devices)]
s = spend[(spend["spend_date"] >= lo) & (spend["spend_date"] <= hi)]
sliced = bool(countries or devices)

rev, n_ord = o["revenue"].sum(), len(o)
paid_spend = s.loc[s["channel"].isin(paid), "spend"].sum()
paid_rev = o.loc[o["last_touch_channel"].isin(paid), "revenue"].sum()
c = st.columns(6)
c[0].metric("Revenue", money(rev))
c[1].metric("Orders", f"{n_ord:,}")
c[2].metric("Avg order value", money(rev / max(n_ord, 1), 2))
c[3].metric("Customers", f"{o['user_id'].nunique():,}")
c[4].metric("Paid spend", money(paid_spend) if not sliced else "n/a",
            help="Ad spend is not split by country or device, so it is hidden when those filters are on.")
c[5].metric("Paid ROAS (last touch)", f"{paid_rev / paid_spend:.2f}x" if paid_spend and not sliced else "n/a")

# weekly trend
wk = o.set_index("order_date")["revenue"].resample("W").sum()
sw = s[s["channel"].isin(paid)].set_index("spend_date")["spend"].resample("W").sum()
fig = make_subplots(specs=[[{"secondary_y": True}]])
fig.add_trace(go.Bar(x=sw.index, y=sw.values, name="Paid spend", marker_color="#c8ced8"), secondary_y=False)
fig.add_trace(go.Scatter(x=wk.index, y=wk.values, name="Revenue", line=dict(color="#2a6fdb", width=3)), secondary_y=True)
fig.update_yaxes(title_text="Paid spend ($)", secondary_y=False, showgrid=False)
fig.update_yaxes(title_text="Revenue ($)", secondary_y=True)
fig.update_layout(height=340, margin=dict(t=30, b=10), title="Weekly revenue and paid spend",
                  legend=dict(orientation="h", y=1.12))
st.plotly_chart(fig, width='stretch')

left, right = st.columns([3, 2])
with left:
    mix = o.assign(week=o["order_date"].dt.to_period("W").dt.start_time)
    mix = mix.groupby(["week", "last_touch_channel"])["revenue"].sum().reset_index()
    f2 = px.area(mix, x="week", y="revenue", color="last_touch_channel", color_discrete_map=CH_COLORS,
                 title="Revenue by last-touch channel", labels={"revenue": "Revenue ($)", "last_touch_channel": "Channel"})
    f2.update_layout(height=340, margin=dict(t=40, b=10), legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(f2, width='stretch')
with right:
    g = o.groupby("device_type")["revenue"].sum().reset_index()
    f3 = px.pie(g, names="device_type", values="revenue", hole=.55, title="Revenue by device")
    f3.update_layout(height=340, margin=dict(t=40, b=10))
    st.plotly_chart(f3, width='stretch')

ch = o[o["last_touch_channel"] != "unattributed"].groupby("last_touch_channel")["revenue"].sum().sort_values(ascending=False)
unpaid_share = ch[~ch.index.isin(paid)].sum() / max(ch.sum(), 1)
dark = o["is_dark_order"].mean()
top = ch.index[0]
lines = [f"**{top}** drives the most last-touch revenue ({money(ch.iloc[0])}, {ch.iloc[0] / ch.sum():.0%} of attributed revenue).",
         f"**{unpaid_share:.0%}** of attributed revenue is credited to channels with no ad spend (email, organic, direct), so paid ROAS alone understates what marketing is doing.",
         f"**{dark:.1%}** of orders have no tracked touchpoint at all (dark orders), a measurement gap the Data Trust page reconciles."]
note("What this says\n\n" + "\n".join(f"- {t}" for t in lines))

c1, c2 = st.columns(2)
with c1:
    gc = o.groupby("country")["revenue"].sum().sort_values().reset_index()
    f4 = px.bar(gc, x="revenue", y="country", orientation="h", title="Revenue by country", labels={"revenue": "Revenue ($)"})
    f4.update_layout(height=320, margin=dict(t=40, b=10))
    st.plotly_chart(f4, width='stretch')
with c2:
    md("### Where to go next")
    st.page_link("pages/1_Attribution.py", label="Attribution: who gets credit, and does it change the answer?", icon="🎯")
    st.page_link("pages/2_Customers_LTV.py", label="Customers: predicted lifetime value and who to win back", icon="👥")
    st.page_link("pages/3_Budget_MMM.py", label="Budget: marketing mix model and spend optimizer", icon="💰")
    st.page_link("pages/4_Data_Trust.py", label="Data trust: tests, reconciliation, limitations", icon="✅")
    md(f"Data covers **{meta['data_start']} to {meta['data_end']}**, {meta['orders']:,} orders from {meta['customers']:,} customers.")
