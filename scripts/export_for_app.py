"""Export dbt marts and model outputs for the Streamlit app.

Run from the repo root after `dbt build`:
    python scripts/export_for_app.py

Everything the app needs is written to app/data/ as small parquet/json files,
so the deployed app never touches the (gitignored) warehouse.duckdb.
Each model block is wrapped in try/except so one failure does not stop the rest.
"""
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "data"
OUT.mkdir(parents=True, exist_ok=True)
con = duckdb.connect(str(ROOT / "warehouse.duckdb"), read_only=True)


def q(sql):
    return con.execute(sql).fetchdf()


def save(df, name):
    df.to_parquet(OUT / f"{name}.parquet", index=False)
    print(f"  {name:<20}{len(df):>9,} rows")


def save_json(obj, name):
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=2, default=str))
    print(f"  {name:<20}json")


def block(title):
    def deco(fn):
        print(title)
        try:
            fn()
        except Exception:
            print(f"  FAILED: {title}")
            traceback.print_exc()
        return fn
    return deco


# --------------------------------------------------------------------------
# 1. Marts, straight from dbt
# --------------------------------------------------------------------------
print("1. Marts")
save(q("select * from main.fct_channel_performance"), "channel_performance")
spend = q("""
    select spend_date, channel, channel_type,
           sum(spend) as spend, sum(impressions) as impressions, sum(reported_clicks) as clicks
    from main.fct_ad_spend group by 1, 2, 3 order by 1, 2""")
spend["spend_date"] = pd.to_datetime(spend["spend_date"])
save(spend, "daily_spend")

orders = q("""
    select order_id, user_id, order_date, revenue, num_touches, is_dark_order,
           first_touch_channel, last_touch_channel, country, device_type
    from main.fct_orders""")
orders["order_date"] = pd.to_datetime(orders["order_date"])
for c in ["first_touch_channel", "last_touch_channel"]:
    orders[c] = orders[c].fillna("unattributed")
orders["device_type"] = orders["device_type"].fillna("unknown")
orders["country"] = orders["country"].fillna("unknown")
save(orders, "orders")

tp = q("""
    select order_id, user_id, channel, touch_position, total_touches, touch_timestamp,
           order_timestamp, revenue, first_touch_weight, last_touch_weight, linear_weight
    from main.fct_attribution_touchpoints where channel is not null""")
save(tp, "touchpoints")


def collapse(s):
    out = []
    for c in s:
        if not out or out[-1] != c:
            out.append(c)
    return " > ".join(out)


tps = tp.sort_values(["order_id", "touch_position"])
jr = tps.groupby("order_id").agg(
    path=("channel", collapse), n_touches=("channel", "size"),
    first_ts=("touch_timestamp", "min"), order_ts=("order_timestamp", "first"),
    revenue=("revenue", "first"), opener=("channel", "first"), closer=("channel", "last")).reset_index()
jr["days_to_convert"] = (pd.to_datetime(jr["order_ts"]) - pd.to_datetime(jr["first_ts"])).dt.total_seconds() / 86400
save(jr.drop(columns=["first_ts", "order_ts"]), "journeys")


# --------------------------------------------------------------------------
# 2. Customer lifetime value (BG/NBD + Gamma-Gamma), same method as btyd_ltv.ipynb
# --------------------------------------------------------------------------
@block("2. Customer LTV")
def ltv():
    from lifetimes import BetaGeoFitter, GammaGammaFitter
    from lifetimes.utils import summary_data_from_transaction_data

    o = orders[["user_id", "order_date", "revenue"]]
    end = o["order_date"].max()
    s = summary_data_from_transaction_data(o, "user_id", "order_date", monetary_value_col="revenue",
                                           observation_period_end=end)
    bgf = BetaGeoFitter(penalizer_coef=0.001).fit(s["frequency"], s["recency"], s["T"])
    rep = s[s["frequency"] > 0]
    ggf = GammaGammaFitter(penalizer_coef=0.001).fit(rep["frequency"], rep["monetary_value"])
    s["p_alive"] = bgf.conditional_probability_alive(s["frequency"], s["recency"], s["T"])
    s["pred_purchases_12m"] = bgf.conditional_expected_number_of_purchases_up_to_time(
        365, s["frequency"], s["recency"], s["T"])
    s["pred_aov"] = ggf.conditional_expected_average_profit(s["frequency"], s["monetary_value"])
    s["pred_ltv_12m"] = s["pred_purchases_12m"] * s["pred_aov"]
    s["ltv_decile"] = pd.qcut(s["pred_ltv_12m"].rank(method="first"), 10, labels=False) + 1

    first = (orders.sort_values(["order_date", "order_id"]).drop_duplicates("user_id")
             [["user_id", "first_touch_channel", "country", "device_type", "order_date"]]
             .rename(columns={"first_touch_channel": "acq_channel", "order_date": "first_order_date"}))
    tot = orders.groupby("user_id").agg(orders_n=("order_id", "nunique"), revenue_to_date=("revenue", "sum")).reset_index()
    coh = q("select user_id, date_trunc('month', first_seen_date) as cohort_month from main.stg_customers")
    cust = (s.reset_index().merge(first, on="user_id", how="left").merge(tot, on="user_id", how="left")
            .merge(coh, on="user_id", how="left"))
    cust["cohort_month"] = pd.to_datetime(cust["cohort_month"])
    save(cust, "customers")

    # unit economics by acquisition channel
    sp = spend.groupby("channel")["spend"].sum()
    ch = (cust.groupby("acq_channel").agg(new_customers=("user_id", "count"),
                                          revenue_to_date=("revenue_to_date", "mean"),
                                          pred_ltv_12m=("pred_ltv_12m", "mean"),
                                          p_alive=("p_alive", "mean")).reset_index()
          .rename(columns={"acq_channel": "channel"}))
    ch["spend"] = ch["channel"].map(sp).fillna(0.0)
    ch["cac_new"] = np.where(ch["spend"] > 0, ch["spend"] / ch["new_customers"], np.nan)
    ch["value_per_customer"] = ch["revenue_to_date"] + ch["pred_ltv_12m"]
    ch["ltv_cac"] = ch["value_per_customer"] / ch["cac_new"]
    save(ch, "channel_ltv")

    # cohort curves, same logic as cohort_ltv.ipynb
    d = (q("""select c.user_id, date_trunc('month', c.first_seen_date) as cohort_month, o.order_date, o.revenue
              from main.stg_customers c join main.fct_orders o on c.user_id = o.user_id"""))
    d["cohort_month"] = pd.to_datetime(d["cohort_month"])
    d["order_date"] = pd.to_datetime(d["order_date"])
    d["months_since"] = ((d["order_date"].dt.year - d["cohort_month"].dt.year) * 12
                         + (d["order_date"].dt.month - d["cohort_month"].dt.month))
    size = d.groupby("cohort_month")["user_id"].nunique()
    m = d.groupby(["cohort_month", "months_since"])["revenue"].sum().reset_index()
    m["cohort_size"] = m["cohort_month"].map(size)
    m["rev_per_customer"] = m["revenue"] / m["cohort_size"]
    m = m.sort_values(["cohort_month", "months_since"])
    m["cum_rev_per_customer"] = m.groupby("cohort_month")["rev_per_customer"].cumsum()
    keep = sorted(m["cohort_month"].unique())[1:-1]
    save(m[m["cohort_month"].isin(keep)], "cohort_curves")

    # out-of-sample check: fit on everything before the last 180 days, predict the last 180
    cut = end - pd.Timedelta(days=180)
    cal = summary_data_from_transaction_data(o[o["order_date"] <= cut], "user_id", "order_date", observation_period_end=cut)
    hold = o[o["order_date"] > cut].groupby("user_id")["order_date"].nunique()
    cal["actual"] = hold.reindex(cal.index).fillna(0)
    b2 = BetaGeoFitter(penalizer_coef=0.001).fit(cal["frequency"], cal["recency"], cal["T"])
    cal["predicted"] = b2.conditional_expected_number_of_purchases_up_to_time(180, cal["frequency"], cal["recency"], cal["T"])
    cal["bucket"] = cal["frequency"].clip(upper=6).astype(int)
    save(cal.groupby("bucket").agg(customers=("predicted", "size"), actual=("actual", "mean"),
                                   predicted=("predicted", "mean")).reset_index(), "ltv_calibration")


# --------------------------------------------------------------------------
# 3. Marketing mix model: adstock + saturation, non-negative least squares, bootstrap
# --------------------------------------------------------------------------
@block("3. Marketing mix model")
def mmm():
    from scipy.optimize import nnls

    wk_s = q("select date_trunc('week', spend_date) as week, channel, sum(spend) as spend "
             "from main.fct_ad_spend group by 1, 2")
    wk_r = q("select date_trunc('week', order_date) as week, sum(revenue) as revenue "
             "from main.fct_orders group by 1")
    wide = wk_s.pivot(index="week", columns="channel", values="spend").fillna(0.0)
    df = wide.join(wk_r.set_index("week")).fillna(0.0).sort_index().iloc[1:-1]  # drop partial edge weeks
    chans = [c for c in wide.columns if wide[c].sum() > 0]
    df = df[chans + ["revenue"]]
    y = df["revenue"].to_numpy(float)
    n = len(df)

    def adstock(x, d):
        out, acc = np.zeros(len(x)), 0.0
        for i, v in enumerate(x):
            acc = v + d * acc
            out[i] = acc
        return out

    def design(d, a):
        A = np.column_stack([adstock(df[c].to_numpy(float), d) for c in chans])
        m = np.maximum(A.mean(axis=0), 1e-9)
        return np.column_stack([np.ones(n), (A / m) ** a]), m

    LAM = [0.0]

    def fit(Xm, yv):
        mu = Xm[:, 1:].mean(axis=0)
        Xc = Xm[:, 1:] - mu
        pen = np.sqrt(LAM[0] * (Xc ** 2).sum(axis=0).mean()) * np.eye(Xc.shape[1])
        b, _ = nnls(np.vstack([Xc, pen]), np.r_[yv - yv.mean(), np.zeros(Xc.shape[1])])
        return np.r_[yv.mean() - mu @ b, b]

    sst = ((y - y.mean()) ** 2).sum()
    folds = np.array_split(np.arange(n), 4)
    best = None
    for d in [0.0, 0.2, 0.4, 0.6, 0.8]:
        for a in [0.3, 0.5, 0.7, 0.9]:
            X, _ = design(d, a)
            sse = 0.0
            for f in folds:
                tr = np.setdiff1d(np.arange(n), f)
                b = fit(X[tr], y[tr])
                sse += ((y[f] - X[f] @ b) ** 2).sum()
            r2cv = 1 - sse / sst
            if best is None or r2cv > best[0]:
                best = (r2cv, d, a)
    r2cv, d, a = best
    X, m = design(d, a)
    for k in [0, .1, .3, 1, 3, 10, 30, 100, 300, 1000]:
        LAM[0] = k
        beta = fit(X, y)
        if beta[0] >= 0.4 * y.mean():
            break
    fitted = X @ beta
    resid = y - fitted
    r2 = 1 - (resid ** 2).sum() / sst

    rng = np.random.default_rng(42)
    boots = []
    for _ in range(300):
        r, blk = [], 4
        while len(r) < n:
            s0 = rng.integers(0, n - blk + 1)
            r.extend(resid[s0:s0 + blk])
        boots.append(fit(X, fitted + np.array(r[:n])))
    B = np.array(boots)
    save(pd.DataFrame(B, columns=["intercept"] + chans).rename_axis("rep").reset_index(), "mmm_boot")

    tot_sp = df[chans].sum().to_numpy()
    F = X[:, 1:]
    contrib_pt = beta[1:] * F.sum(axis=0)
    roas_pt = contrib_pt / tot_sp
    roas_b = B[:, 1:] * F.sum(axis=0) / tot_sp
    s_bar = df[chans].mean().to_numpy()
    k = 1 / ((1 - d) * m)
    marg = lambda bb: bb * a * (s_bar * k) ** (a - 1) * k
    rows = pd.DataFrame({
        "channel": chans, "beta": beta[1:], "m": m, "weekly_spend_mean": s_bar,
        "weekly_spend_max": df[chans].max().to_numpy(), "total_spend": tot_sp,
        "contribution_total": contrib_pt, "roas_avg": roas_pt,
        "roas_lo": np.percentile(roas_b, 10, axis=0), "roas_hi": np.percentile(roas_b, 90, axis=0),
        "marginal_roas": marg(beta[1:]),
        "marginal_lo": np.percentile(marg(B[:, 1:]), 10, axis=0),
        "marginal_hi": np.percentile(marg(B[:, 1:]), 90, axis=0)})
    save(rows, "mmm_channels")

    dec = pd.DataFrame({"week": df.index, "component": "baseline", "value": beta[0]})
    parts = [dec]
    for i, c in enumerate(chans):
        parts.append(pd.DataFrame({"week": df.index, "component": c, "value": beta[i + 1] * F[:, i]}))
    parts.append(pd.DataFrame({"week": df.index, "component": "actual", "value": y}))
    save(pd.concat(parts, ignore_index=True), "mmm_decomp")
    save_json({"decay": d, "alpha": a, "intercept": float(beta[0]), "r2_in_sample": float(r2),
               "r2_cv": float(r2cv), "n_weeks": int(n), "week_start": str(df.index.min().date()),
               "week_end": str(df.index.max().date()), "bootstrap_reps": 300, "baseline_floor": 0.4, "ridge_k": float(LAM[0])}, "mmm_model")


# --------------------------------------------------------------------------
# 4. Pipeline health: dbt results and table sizes
# --------------------------------------------------------------------------
@block("4. Pipeline status")
def status():
    rr = ROOT / "dbt_project" / "target" / "run_results.json"
    if rr.exists():
        j = json.loads(rr.read_text())
        res = pd.DataFrame([{"unique_id": r["unique_id"], "resource_type": r["unique_id"].split(".")[0],
                             "name": r["unique_id"].split(".")[2], "status": r["status"],
                             "seconds": r.get("execution_time", 0.0)} for r in j["results"]])
        save(res, "dbt_results")
        dbt_version = j.get("metadata", {}).get("dbt_version", "")
    else:
        dbt_version = ""
    tables = q("select table_schema || '.' || table_name as t from information_schema.tables "
               "where table_schema in ('main', 'raw') order by 1")["t"].tolist()
    counts = {t: int(con.execute(f"select count(*) from {t}").fetchone()[0]) for t in tables}
    save_json({"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               "data_start": str(orders["order_date"].min().date()), "data_end": str(orders["order_date"].max().date()),
               "orders": int(len(orders)), "customers": int(orders["user_id"].nunique()),
               "dbt_version": dbt_version, "table_rows": counts}, "pipeline_meta")


print("Done. Files in", OUT)
