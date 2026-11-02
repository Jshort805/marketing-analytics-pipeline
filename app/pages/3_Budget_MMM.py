import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils import CH_COLORS, load, load_json, md, money, note, setup

setup("Budget (MMM)", "💰")
st.title("Budget: where would the next dollar work hardest?")
st.caption("A weekly marketing mix model: spend is carried over time (adstock), shows diminishing returns (saturation), "
           "and each channel gets a non-negative effect on revenue. Uncertainty comes from 300 block-bootstrap refits.")

mm, ch, boot, dec = load_json("mmm_model"), load("mmm_channels"), load("mmm_boot"), load("mmm_decomp")
chans = ch["channel"].tolist()
d, a = mm["decay"], mm["alpha"]
k = (1.0 / ((1 - d) * ch["m"])).to_numpy()
beta = ch["beta"].to_numpy()
B = boot[chans].to_numpy()
cur = ch["weekly_spend_mean"].to_numpy()


def revenue(x, b=beta):
    return (b * (np.maximum(x, 0) * k) ** a).sum(axis=-1)


note("Read this before using any number on the page\n\n"
     f"Fitted on {mm['n_weeks']} weeks ({mm['week_start']} to {mm['week_end']}). In-sample R² is {mm['r2_in_sample']:.2f}; "
     f"R² on held-out weeks is {mm['r2_cv']:.2f}. With this little history, channel effects are only loosely identified, "
     "so we also assume at least 40% of revenue is baseline (shrinkage was raised until that held; this is an assumption, not a finding), and "
     "treat ROAS values as a ranking with a wide band, not as exact returns. Real MMMs add more history, seasonality, promotions and "
     "experiments (geo or holdout tests) to calibrate the results.", "warning")

t1, t2, t3, t4 = st.tabs(["What drove revenue", "Channel returns", "Optimize budget", "What-if"])

with t1:
    p = dec[dec["component"] != "actual"].copy()
    act = dec[dec["component"] == "actual"]
    order = ["baseline"] + chans
    fig = px.area(p, x="week", y="value", color="component", category_orders={"component": order},
                  color_discrete_map={**CH_COLORS, "baseline": "#dfe3ea"}, title="Weekly revenue split into baseline and paid-channel contribution",
                  labels={"value": "Revenue ($)", "component": ""})
    fig.add_trace(go.Scatter(x=act["week"], y=act["value"], name="Actual revenue", line=dict(color="black", width=1.5, dash="dot")))
    fig.update_layout(height=430, margin=dict(t=40), legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width='stretch')
    tot = p.groupby("component")["value"].sum()
    base_share = tot["baseline"] / tot.sum()
    md(f"About **{base_share:.0%}** of revenue is baseline (it would have happened without paid media: brand, email, organic, returning customers). "
       f"The model credits the remaining **{1 - base_share:.0%}** to paid channels.")

with t2:
    r = ch.copy()
    fig = go.Figure()
    for _, row in r.sort_values("roas_avg").iterrows():
        fig.add_trace(go.Scatter(x=[row["roas_lo"], row["roas_hi"]], y=[row["channel"]] * 2, mode="lines",
                                 line=dict(color=CH_COLORS.get(row["channel"], "#999"), width=6), showlegend=False))
        fig.add_trace(go.Scatter(x=[row["roas_avg"]], y=[row["channel"]], mode="markers", marker=dict(size=12, color="black"), showlegend=False))
    fig.update_layout(title="Average return per $1 (dot) with 10th to 90th percentile band", height=380, margin=dict(t=40),
                      xaxis_title="Modeled revenue per $1 of spend")
    st.plotly_chart(fig, width='stretch')
    fig = go.Figure()
    for _, row in r.sort_values("marginal_roas").iterrows():
        fig.add_trace(go.Bar(x=[row["marginal_roas"]], y=[row["channel"]], orientation="h", marker_color=CH_COLORS.get(row["channel"], "#999"),
                             error_x=dict(type="data", symmetric=False, array=[row["marginal_hi"] - row["marginal_roas"]],
                                          arrayminus=[row["marginal_roas"] - row["marginal_lo"]]), showlegend=False))
    fig.update_layout(title="Marginal return: what the NEXT dollar earns at current spend", height=380, margin=dict(t=40),
                      xaxis_title="Revenue from one more $1 per week")
    st.plotly_chart(fig, width='stretch')
    best, worst = r.loc[r["marginal_roas"].idxmax()], r.loc[r["marginal_roas"].idxmin()]
    note(f"What this says\n\n- At today's spend, the next dollar earns most in **{best['channel']}** ({best['marginal_roas']:.2f}) and least in **{worst['channel']}** ({worst['marginal_roas']:.2f}).\n"
         "- Average return and marginal return differ because of saturation: a channel can look great on average and still be maxed out.")
    xs = st.selectbox("Response curve for", chans)
    i = chans.index(xs)
    grid = np.linspace(0, ch.loc[i, "weekly_spend_max"] * 1.6, 120)
    resp = beta[i] * (grid * k[i]) ** a
    lo_c, hi_c = np.percentile(B[:, i] * (grid[:, None] * k[i]) ** a, [10, 90], axis=1)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=np.r_[grid, grid[::-1]], y=np.r_[hi_c, lo_c[::-1]], fill="toself", line=dict(width=0),
                             fillcolor="rgba(42,111,219,.18)", name="10 to 90%"))
    fig.add_trace(go.Scatter(x=grid, y=resp, name="Modeled", line=dict(color="#2a6fdb", width=3)))
    fig.add_vline(x=cur[i], line_dash="dot", annotation_text="current avg")
    fig.update_layout(title=f"{xs}: weekly revenue vs weekly spend", height=360, margin=dict(t=40),
                      xaxis_title="Weekly spend ($)", yaxis_title="Weekly revenue contribution ($)")
    st.plotly_chart(fig, width='stretch')

with t3:
    c1, c2, c3 = st.columns(3)
    budget = c1.slider("Total weekly paid budget ($)", int(cur.sum() * 0.5), int(cur.sum() * 1.6), int(cur.sum()), step=50)
    swing = c2.slider("Max change per channel", 10, 100, 50, step=10, format="%d%%") / 100
    floor = c3.checkbox("Keep every channel at least 25% of today's level", value=True)
    lo_b = cur * (1 - swing) if not floor else np.maximum(cur * (1 - swing), cur * 0.25)
    hi_b = cur * (1 + swing)
    x = lo_b.copy()
    left = budget - x.sum()
    if left < 0:
        st.error("The budget is below the sum of channel minimums. Raise the budget or loosen the limits.")
        st.stop()
    step = budget / 1500
    for _ in range(3000):
        if left < 1e-6:
            break
        marg = beta * a * (np.maximum(x, 1e-3) * k) ** (a - 1) * k
        marg[x >= hi_b - 1e-9] = -1
        j = int(np.argmax(marg))
        if marg[j] < 0:
            break
        inc = min(step, left, hi_b[j] - x[j])
        x[j] += inc
        left -= inc
    cur_rev, new_rev = revenue(cur), revenue(x)
    up = revenue(x, B) - revenue(cur, B)
    u10, u90 = np.percentile(up, [10, 90])
    m = st.columns(4)
    m[0].metric("Weekly spend (recommended)", money(x.sum()))
    m[1].metric("Modeled weekly revenue, today", money(cur_rev))
    m[2].metric("Modeled weekly revenue, recommended", money(new_rev), delta=money(new_rev - cur_rev))
    m[3].metric("Likely uplift range (10 to 90%)", f"{money(u10)} to {money(u90)}")
    cmp = pd.DataFrame({"channel": chans * 2, "plan": ["Today"] * len(chans) + ["Recommended"] * len(chans), "spend": np.r_[cur, x]})
    fig = px.bar(cmp, x="channel", y="spend", color="plan", barmode="group", color_discrete_sequence=["#8b95a5", "#2a6fdb"],
                 title="Weekly spend by channel", labels={"spend": "Weekly spend ($)", "plan": ""})
    fig.update_layout(height=380, margin=dict(t=40), legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig, width='stretch')
    chg = pd.DataFrame({"channel": chans, "today": cur, "recommended": x, "change": x - cur, "change_pct": (x - cur) / np.maximum(cur, 1)})
    st.dataframe(chg, hide_index=True, width='stretch',
                 column_config={"today": st.column_config.NumberColumn(format="$%.0f"), "recommended": st.column_config.NumberColumn(format="$%.0f"),
                                "change": st.column_config.NumberColumn(format="$%.0f"), "change_pct": st.column_config.NumberColumn("Change", format="%.0f%%")})
    prob = float((up > 0).mean())
    note(f"What this says\n\n- Moving money toward channels with higher marginal return lifts modeled weekly revenue by about {money(new_rev - cur_rev)}.\n"
         f"- In {prob:.0%} of the 300 bootstrap refits the recommended plan beats today's, so the direction is {'fairly robust' if prob > 0.8 else 'uncertain'}. "
         "A good next step is to test the biggest shift with a holdout before moving the whole budget.")

with t4:
    md("Try your own plan. Each slider is a percent change to that channel's weekly spend.")
    cols = st.columns(3)
    pct = np.array([cols[i % 3].slider(c, -100, 100, 0, step=10, format="%d%%", key=f"w_{c}") for i, c in enumerate(chans)]) / 100
    x2 = cur * (1 + pct)
    delta = revenue(x2) - revenue(cur)
    ub = revenue(x2, B) - revenue(cur, B)
    a1, a2, a3 = st.columns(3)
    a1.metric("Spend change per week", money(x2.sum() - cur.sum()))
    a2.metric("Modeled revenue change per week", money(delta))
    a3.metric("Range (10 to 90%)", f"{money(np.percentile(ub, 10))} to {money(np.percentile(ub, 90))}")
    fig = px.histogram(pd.DataFrame({"uplift": ub}), x="uplift", nbins=40, title="Revenue change across 300 bootstrap refits",
                       labels={"uplift": "Weekly revenue change ($)"})
    fig.add_vline(x=0, line_dash="dot")
    fig.update_layout(height=300, margin=dict(t=40))
    st.plotly_chart(fig, width='stretch')
