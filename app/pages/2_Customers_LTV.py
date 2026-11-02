import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils import CH_COLORS, load, md, money, note, setup

setup("Customers and LTV", "👥")
st.title("Customers: what are they worth, and who is slipping away?")
st.caption("Predictions use BG/NBD (how many more purchases) and Gamma-Gamma (how much each is worth), "
           "the same method as analysis/ltv/btyd_ltv.ipynb. Forecast horizon is the next 12 months.")

cust, chl, coh, cal = load("customers"), load("channel_ltv"), load("cohort_curves"), load("ltv_calibration")

with st.sidebar:
    chs = st.multiselect("Acquisition channel", sorted(cust["acq_channel"].dropna().unique()))
    cs = st.multiselect("Country", sorted(cust["country"].dropna().unique()))
f = cust
if chs:
    f = f[f["acq_channel"].isin(chs)]
if cs:
    f = f[f["country"].isin(cs)]

at_risk = f[(f["frequency"] >= 2) & (f["p_alive"] < 0.5)]
c = st.columns(5)
c[0].metric("Customers", f"{len(f):,}")
c[1].metric("Revenue to date", money(f["revenue_to_date"].sum()))
c[2].metric("Predicted next-12-month revenue", money(f["pred_ltv_12m"].sum()))
c[3].metric("Avg probability still active", f"{f['p_alive'].mean():.0%}")
c[4].metric("Repeat buyers likely lapsed", f"{len(at_risk):,}", help="2+ purchases and under 50% chance of being active")

tab1, tab2, tab3, tab4 = st.tabs(["Value by channel", "Concentration", "Cohorts", "Win-back list"])

with tab1:
    d = chl.copy()
    d["paid"] = d["spend"] > 0
    a, b = st.columns(2)
    with a:
        m = d.melt(id_vars="channel", value_vars=["revenue_to_date", "pred_ltv_12m"], var_name="part", value_name="v")
        m["part"] = m["part"].map({"revenue_to_date": "Spent so far", "pred_ltv_12m": "Predicted next 12 months"})
        fig = px.bar(m, x="channel", y="v", color="part", title="Value per customer by acquisition channel",
                     labels={"v": "$ per customer", "part": ""}, color_discrete_sequence=["#8b95a5", "#2a6fdb"])
        fig.update_layout(height=380, margin=dict(t=40), legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig, width='stretch')
    with b:
        p = d[d["paid"]].sort_values("ltv_cac", ascending=False)
        fig = px.bar(p, x="channel", y="ltv_cac", color="channel", color_discrete_map=CH_COLORS,
                     title="Customer value divided by acquisition cost", labels={"ltv_cac": "Value : CAC"})
        fig.add_hline(y=3, line_dash="dot", annotation_text="3x rule of thumb")
        fig.update_layout(height=380, showlegend=False, margin=dict(t=40))
        st.plotly_chart(fig, width='stretch')
    st.dataframe(d[["channel", "new_customers", "spend", "cac_new", "value_per_customer", "ltv_cac", "p_alive"]],
                 hide_index=True, width='stretch',
                 column_config={"spend": st.column_config.NumberColumn(format="$%.0f"),
                                "cac_new": st.column_config.NumberColumn("CAC", format="$%.2f"),
                                "value_per_customer": st.column_config.NumberColumn("Value / customer", format="$%.2f"),
                                "ltv_cac": st.column_config.NumberColumn("Value : CAC", format="%.1fx"),
                                "p_alive": st.column_config.NumberColumn("Still active", format="%.2f")})
    p = d[d["paid"]].dropna(subset=["ltv_cac"]).sort_values("ltv_cac")
    if len(p):
        note(f"What this says\n\n- **{p.iloc[-1]['channel']}** returns the most value per acquisition dollar ({p.iloc[-1]['ltv_cac']:.1f}x); "
             f"**{p.iloc[0]['channel']}** the least ({p.iloc[0]['ltv_cac']:.1f}x).\n"
             "- Last-click ROAS ignores repeat purchases. This view credits a channel for the customers it brings in and what they go on to spend.\n"
             "- CAC here is channel spend divided by customers whose first order was first-touched by that channel, an approximation.")

with tab2:
    s = f.sort_values("pred_ltv_12m", ascending=False).reset_index(drop=True)
    s["cum"] = s["pred_ltv_12m"].cumsum() / s["pred_ltv_12m"].sum()
    s["cust_pct"] = (s.index + 1) / len(s)
    top10 = s.loc[s["cust_pct"] <= 0.10, "pred_ltv_12m"].sum() / s["pred_ltv_12m"].sum()
    a, b = st.columns(2)
    with a:
        fig = go.Figure(go.Scatter(x=s["cust_pct"], y=s["cum"], fill="tozeroy", line=dict(color="#2a6fdb")))
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(dash="dot", color="grey")))
        fig.update_layout(title="Share of predicted value held by the top customers", height=360, showlegend=False,
                          xaxis=dict(title="Share of customers", tickformat=".0%"), yaxis=dict(title="Share of value", tickformat=".0%"),
                          margin=dict(t=40))
        st.plotly_chart(fig, width='stretch')
    with b:
        dec = f.groupby("ltv_decile")["pred_ltv_12m"].mean().reset_index()
        fig = px.bar(dec, x="ltv_decile", y="pred_ltv_12m", title="Average predicted 12-month value by decile",
                     labels={"ltv_decile": "Decile (10 = best)", "pred_ltv_12m": "$ per customer"})
        fig.update_layout(height=360, margin=dict(t=40))
        st.plotly_chart(fig, width='stretch')
    note(f"What this says\n\n- The top 10% of customers account for **{top10:.0%}** of predicted next-year revenue. "
         "Retention and service spend should be weighted toward them, and look-alike audiences should be built from them.")
    md("##### Does the model hold up on data it has not seen?")
    st.caption("Fitted on everything before the last 180 days, then asked to predict purchases in those 180 days.")
    cm = cal.melt(id_vars=["bucket", "customers"], value_vars=["actual", "predicted"], var_name="kind", value_name="purchases")
    fig = px.bar(cm, x="bucket", y="purchases", color="kind", barmode="group", color_discrete_sequence=["#8b95a5", "#2a6fdb"],
                 labels={"bucket": "Repeat purchases before the cut-off (6 = 6 or more)", "purchases": "Avg purchases in the next 180 days"})
    fig.update_layout(height=320, margin=dict(t=20), legend_title_text="")
    st.plotly_chart(fig, width='stretch')

with tab3:
    cc = coh.copy()
    cc["cohort"] = cc["cohort_month"].dt.strftime("%Y-%m")
    fig = px.line(cc, x="months_since", y="cum_rev_per_customer", color="cohort", color_discrete_sequence=px.colors.sequential.Blues[2:],
                  title="Cumulative revenue per customer, by month of first visit",
                  labels={"months_since": "Months since acquisition", "cum_rev_per_customer": "Cumulative revenue per customer ($)"})
    fig.update_layout(height=460, margin=dict(t=40))
    st.plotly_chart(fig, width='stretch')
    md("Curves that sit higher are better-quality cohorts. If recent cohorts sit lower at the same age, acquisition quality is slipping, "
       "which is invisible in a single ROAS number.")

with tab4:
    th = st.slider("Probability still active is below", 0.05, 0.9, 0.5, 0.05)
    mf = st.slider("Minimum purchases so far", 1, 8, 2)
    w = f[(f["p_alive"] < th) & (f["frequency"] + 1 >= mf)].copy()
    w = w.sort_values("revenue_to_date", ascending=False)
    c1, c2 = st.columns(2)
    c1.metric("Customers on the list", f"{len(w):,}")
    c2.metric("Their revenue to date", money(w["revenue_to_date"].sum()))
    cols = ["user_id", "acq_channel", "country", "orders_n", "revenue_to_date", "p_alive", "recency", "T"]
    st.dataframe(w[cols].head(200), hide_index=True, width='stretch',
                 column_config={"revenue_to_date": st.column_config.NumberColumn("Revenue to date", format="$%.0f"),
                                "p_alive": st.column_config.ProgressColumn("Still active", min_value=0, max_value=1, format="%.2f"),
                                "recency": st.column_config.NumberColumn("Days between first and last order", format="%.0f"),
                                "T": st.column_config.NumberColumn("Customer age (days)", format="%.0f")})
    st.download_button("Download list as CSV", w[cols].to_csv(index=False), "winback_list.csv", "text/csv")
    md("In production this list would feed an email or CRM audience, refreshed each time the pipeline runs.")
