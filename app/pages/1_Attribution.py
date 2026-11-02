import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils import CH_COLORS, MODEL_LABELS, dates_filter, load, md, money, note, setup

setup("Attribution", "🎯")
st.title("Attribution: who gets credit?")
st.caption("Five ways to split an order's revenue across the touchpoints that preceded it. "
           "First, last and linear come straight from the dbt mart; position-based and time-decay are computed here from the same rows.")

cp, spend, orders, jr = load("channel_performance"), load("daily_spend"), load("orders"), load("journeys")
lo, hi = dates_filter(orders["order_date"], "attr_dates")
paid_set = set(cp.loc[cp["is_paid"], "channel"])


@st.cache_data
def weighted_touches() -> pd.DataFrame:
    t = load("touchpoints").copy()
    t["touch_timestamp"] = pd.to_datetime(t["touch_timestamp"])
    t["order_timestamp"] = pd.to_datetime(t["order_timestamp"])
    t = t.sort_values(["order_id", "touch_timestamp"])
    t["n"] = t.groupby("order_id")["channel"].transform("size")
    t["pos"] = t.groupby("order_id").cumcount() + 1
    mid = np.where(t["n"] > 2, 0.2 / (t["n"] - 2).clip(lower=1), 0.0)
    t["position"] = np.select([t["n"] == 1, t["n"] == 2, t["pos"] == 1, t["pos"] == t["n"]], [1.0, 0.5, 0.4, 0.4], mid)
    days = (t["order_timestamp"] - t["touch_timestamp"]).dt.total_seconds() / 86400
    raw = 0.5 ** (days / 7)
    t["decay"] = raw / raw.groupby(t["order_id"]).transform("sum")
    t = t.rename(columns={"first_touch_weight": "first", "last_touch_weight": "last", "linear_weight": "linear"})
    t["order_date"] = t["order_timestamp"].dt.normalize()
    return t


t = weighted_touches()
t = t[(t["order_date"] >= lo) & (t["order_date"] <= hi)]
sp = spend[(spend["spend_date"] >= lo) & (spend["spend_date"] <= hi)].groupby("channel")["spend"].sum()


def channel_table(model: str) -> pd.DataFrame:
    g = pd.DataFrame({"revenue": (t["revenue"] * t[model]).groupby(t["channel"]).sum(),
                      "orders": t[model].groupby(t["channel"]).sum()})
    g["spend"] = sp.reindex(g.index).fillna(0.0)
    g["roas"] = np.where(g["spend"] > 0, g["revenue"] / g["spend"].replace(0, np.nan), np.nan)
    g["cac"] = np.where(g["spend"] > 0, g["spend"] / g["orders"].replace(0, np.nan), np.nan)
    g["share"] = g["revenue"] / g["revenue"].sum()
    return g.reset_index().rename(columns={"index": "channel"})


tab1, tab2, tab3 = st.tabs(["Compare models", "Openers vs closers", "Customer journeys"])

with tab1:
    model = st.radio("Attribution model", list(MODEL_LABELS), format_func=MODEL_LABELS.get, horizontal=True)
    g = channel_table(model).sort_values("revenue", ascending=False)
    pg = g[g["spend"] > 0].sort_values("roas", ascending=False)
    c1, c2 = st.columns(2)
    with c1:
        f = px.bar(pg, x="channel", y="roas", color="channel", color_discrete_map=CH_COLORS,
                   title=f"ROAS, {MODEL_LABELS[model].lower()}", labels={"roas": "Revenue per $1 spend"})
        f.add_hline(y=1, line_dash="dot", annotation_text="break-even")
        f.update_layout(height=340, showlegend=False, margin=dict(t=40))
        st.plotly_chart(f, width='stretch')
    with c2:
        f = px.bar(pg.sort_values("cac"), x="channel", y="cac", color="channel", color_discrete_map=CH_COLORS,
                   title="Cost per attributed order", labels={"cac": "Spend per order ($)"})
        f.update_layout(height=340, showlegend=False, margin=dict(t=40))
        st.plotly_chart(f, width='stretch')

    show = g.assign(channel_type=g["channel"].map(lambda c: "paid" if c in paid_set else "unpaid"))
    st.dataframe(show[["channel", "channel_type", "spend", "revenue", "orders", "roas", "cac", "share"]],
                 hide_index=True, width='stretch',
                 column_config={"spend": st.column_config.NumberColumn(format="$%.0f"),
                                "revenue": st.column_config.NumberColumn(format="$%.0f"),
                                "orders": st.column_config.NumberColumn(format="%.0f"),
                                "roas": st.column_config.NumberColumn("ROAS", format="%.2fx"),
                                "cac": st.column_config.NumberColumn("Cost / order", format="$%.2f"),
                                "share": st.column_config.ProgressColumn("Share of revenue", format="%.2f", min_value=0, max_value=1)})

    # model x channel ROAS heatmap + rank movement
    mat = pd.DataFrame({MODEL_LABELS[m]: channel_table(m).set_index("channel")["roas"] for m in MODEL_LABELS})
    mat = mat.loc[[c for c in mat.index if c in paid_set]].dropna(how="all")
    hm = px.imshow(mat, text_auto=".2f", aspect="auto", color_continuous_scale="Blues",
                   title="ROAS for every channel under every model", labels=dict(color="ROAS"))
    hm.update_layout(height=360, margin=dict(t=40))
    st.plotly_chart(hm, width='stretch')
    ranks = mat.rank(ascending=False)
    swing = (ranks.max(axis=1) - ranks.min(axis=1)).sort_values(ascending=False)
    best_last, best_first = mat.iloc[:, 1].idxmax(), mat.iloc[:, 0].idxmax()
    note(f"What this says\n\n- The answer depends on the model: **{best_first}** has the best ROAS under first touch and **{best_last}** under last touch.\n"
         f"- **{swing.index[0]}** moves the most in rank across models ({int(swing.iloc[0])} places), so a budget decision about it should not rest on one model.")

with tab2:
    fo = orders.loc[(orders["order_date"] >= lo) & (orders["order_date"] <= hi)]
    a = fo.groupby("first_touch_channel")["revenue"].sum().rename("opens")
    b = fo.groupby("last_touch_channel")["revenue"].sum().rename("closes")
    oc = pd.concat([a, b], axis=1).fillna(0).reset_index().rename(columns={"index": "channel"})
    oc["spend"] = oc["channel"].map(sp).fillna(0.0)
    oc["role"] = np.where(oc["opens"] > oc["closes"], "opener", "closer")
    f = px.scatter(oc, x="opens", y="closes", size=oc["spend"].clip(lower=1500), color="channel", color_discrete_map=CH_COLORS,
                   text="channel", title="First-touch revenue vs last-touch revenue", labels={"opens": "Revenue as first touch ($)", "closes": "Revenue as last touch ($)"})
    mx = float(max(oc["opens"].max(), oc["closes"].max()))
    f.add_trace(go.Scatter(x=[0, mx], y=[0, mx], mode="lines", line=dict(dash="dot", color="grey"), showlegend=False))
    f.update_traces(textposition="top center", selector=dict(mode="markers+text"))
    f.update_layout(height=460, showlegend=False, margin=dict(t=40))
    st.plotly_chart(f, width='stretch')
    md("Channels **below the dotted line** open more journeys than they close (awareness, prospecting). "
       "Channels **above** it close more than they open (harvesting demand someone else created). Bubble size is ad spend.")
    multi = jr[jr["n_touches"] > 1]
    flow = multi.groupby(["opener", "closer"]).size().reset_index(name="orders")
    left = sorted(flow["opener"].unique())
    right = sorted(flow["closer"].unique())
    labels = [f"{c} (first)" for c in left] + [f"{c} (last)" for c in right]
    sk = go.Figure(go.Sankey(
        node=dict(label=labels, pad=14, color=[CH_COLORS.get(c, "#999") for c in left + right]),
        link=dict(source=[left.index(x) for x in flow["opener"]], target=[len(left) + right.index(x) for x in flow["closer"]],
                  value=flow["orders"], color="rgba(140,150,170,.3)")))
    sk.update_layout(title="Multi-touch journeys: who starts them and who finishes them", height=480, margin=dict(t=40))
    st.plotly_chart(sk, width='stretch')

with tab3:
    j = jr.copy()
    c1, c2, c3 = st.columns(3)
    c1.metric("Orders with a tracked journey", f"{len(j):,}")
    c2.metric("Average touches before purchase", f"{j['n_touches'].mean():.1f}")
    c3.metric("Median days from first touch to order", f"{j['days_to_convert'].median():.1f}")
    a, b = st.columns(2)
    with a:
        h = j["n_touches"].clip(upper=10).value_counts().sort_index().reset_index()
        h.columns = ["touches", "orders"]
        f = px.bar(h, x="touches", y="orders", title="Journey length (10 = 10 or more)")
        f.update_layout(height=320, margin=dict(t=40))
        st.plotly_chart(f, width='stretch')
    with b:
        f = px.histogram(j[j["days_to_convert"] <= 30], x="days_to_convert", nbins=30, title="Days from first touch to order",
                         labels={"days_to_convert": "Days"})
        f.update_layout(height=320, margin=dict(t=40))
        st.plotly_chart(f, width='stretch')
    mn = st.slider("Minimum touches in a path", 2, 6, 2)
    p = (j[j["n_touches"] >= mn].groupby("path").agg(orders=("revenue", "size"), revenue=("revenue", "sum"),
                                                   avg_days=("days_to_convert", "mean")).reset_index()
         .sort_values("orders", ascending=False).head(15))
    f = px.bar(p.sort_values("orders"), x="orders", y="path", orientation="h", title="Most common conversion paths",
               color="avg_days", color_continuous_scale="Blues", labels={"avg_days": "Avg days"})
    f.update_layout(height=480, margin=dict(t=40), yaxis_title=None)
    st.plotly_chart(f, width='stretch')
