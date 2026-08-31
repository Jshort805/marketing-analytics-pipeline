"""
generate_data.py
-----------------
Synthetic marketing data generator.

Simulating:
  1. Ad platforms (Google Ads, Meta Ads, TikTok Ads, an affiliate network)  -> campaigns + daily spend
  2. Web analytics / tag manager (click & session tracking)                -> touchpoints ("clicks")
  3. E-commerce / CRM backend                                              -> customers + orders

  customer journeys (touchpoints) are simulated first -> orders are derived
  from those journeys -> ad platform spend is derived from (but not identical
  to) the touchpoints, on purpose, to mimic the real-world: the clicks an
  ad platform reports rarely match 1:1 with the sessions your own web
  analytics tracks (ad-blockers, bot filtering, double counting, etc).

A fixed random seed makes every run of this script produce identical data.

OUTPUT
Five raw CSVs, written to data/raw/:
  - campaigns.csv        (dim-like: one row per ad campaign)
  - ad_spend.csv          (fact: one row per campaign per day)
  - clicks.csv            (fact: one row per marketing touchpoint)
  - customers.csv         (dim-like: one row per user)
  - orders.csv            (fact: one row per purchase)

A few data-quality issues are injected on purpose (mixed-case channel
strings, whitespace in campaign names, a handful of duplicate order rows,
a few missing device types) so the dbt staging layer has real cleaning work
to do.
"""

import random
from datetime import date, timedelta, datetime, time
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

# ---------------------------------------------------------------------------
# 1. CONFIG / REPRODUCIBILITY
# ---------------------------------------------------------------------------
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker()
Faker.seed(SEED)

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)

END_DATE = date.today()
START_DATE = END_DATE - timedelta(days=730)
TOTAL_DAYS = (END_DATE - START_DATE).days

N_USERS = 9000          # customers who have at least one marketing touchpoint
N_DARK_ORDERS = 220     # word-of-mouth / type-in orders with NO marketing touch at all
                        # (this is "dark" / unattributed revenue -- every marketing
                        #  team has some of it, and it's a great teaching example for
                        #  why attribution coverage is never 100%)

P_DORMANT = 0.35                 # probability an active customer stops buying after each order
AVG_DAYS_BETWEEN_PURCHASES = 45  # mean gap between repeat purchases, while active
# ---------------------------------------------------------------------------
# 2. CHANNEL DEFINITIONS
#    conv_weight: this channel's individual "closing power" -- used to build a
#      combined conversion probability across a whole journey (see below).
#    volume_weight: relative share of total touchpoints that land on this
#      channel.
#    paid: whether this channel has an ad-platform spend/performance feed.
# ---------------------------------------------------------------------------
CHANNELS = {
    "google_search":   {"type": "paid_search",  "paid": True,  "cpc": (1.10, 3.60), "ctr": (0.030, 0.065), "conv_weight": 0.115, "volume_weight": 19},
    "meta_facebook":   {"type": "paid_social",  "paid": True,  "cpc": (0.35, 1.20), "ctr": (0.008, 0.020), "conv_weight": 0.045, "volume_weight": 22},
    "meta_instagram":  {"type": "paid_social",  "paid": True,  "cpc": (0.40, 1.30), "ctr": (0.007, 0.018), "conv_weight": 0.035, "volume_weight": 16},
    "tiktok_ads":      {"type": "paid_social",  "paid": True,  "cpc": (0.25, 0.90), "ctr": (0.010, 0.026), "conv_weight": 0.025, "volume_weight": 13},
    "display_network": {"type": "paid_display", "paid": True,  "cpc": (0.15, 0.55), "ctr": (0.003, 0.010), "conv_weight": 0.015, "volume_weight": 10},
    "affiliate":       {"type": "affiliate",    "paid": True,  "cpc": (0.60, 1.80), "ctr": (0.020, 0.045), "conv_weight": 0.095, "volume_weight": 6},
    "email":           {"type": "email",        "paid": False, "cpc": None,         "ctr": None,           "conv_weight": 0.130, "volume_weight": 8},
    "organic_search":  {"type": "organic",      "paid": False, "cpc": None,         "ctr": None,           "conv_weight": 0.075, "volume_weight": 12},
    "direct":          {"type": "direct",       "paid": False, "cpc": None,         "ctr": None,           "conv_weight": 0.145, "volume_weight": 6},
}
PAID_CHANNELS = [c for c, v in CHANNELS.items() if v["paid"]]
ALL_CHANNELS = list(CHANNELS.keys())
CHANNEL_VOL_WEIGHTS = np.array([CHANNELS[c]["volume_weight"] for c in ALL_CHANNELS], dtype=float)
CHANNEL_VOL_WEIGHTS = CHANNEL_VOL_WEIGHTS / CHANNEL_VOL_WEIGHTS.sum()

DEVICE_TYPES = ["mobile", "desktop", "tablet"]
DEVICE_WEIGHTS = [0.58, 0.35, 0.07]

PRODUCT_CATEGORIES = ["apparel", "footwear", "accessories", "home_goods", "electronics"]
CATEGORY_WEIGHTS = [0.32, 0.22, 0.20, 0.16, 0.10]

COUNTRIES = ["US", "US", "US", "US", "CA", "GB", "AU", "DE"]  # weighted toward US

LANDING_PAGES = [
    "/", "/new-arrivals", "/sale", "/collections/summer",
    "/product/classic-tee", "/product/running-shoes", "/blog/style-guide",
]

CAMPAIGN_OBJECTIVES = ["awareness", "conversion", "retargeting", "prospecting"]


def rand_date_between(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(delta, 0)))


# ---------------------------------------------------------------------------
# 3. CAMPAIGNS (one dimension table, paid channels only)
# ---------------------------------------------------------------------------
def generate_campaigns():
    rows = []
    campaign_id = 1000
    for channel in PAID_CHANNELS:
        n_campaigns = random.randint(2, 4)
        for _ in range(n_campaigns):
            campaign_id += 1
            # campaigns run for a random sub-window of the overall period,
            # some spanning the whole thing, some short bursts
            span_days = random.choice([TOTAL_DAYS, TOTAL_DAYS, random.randint(21, 90)])
            latest_start = max((END_DATE - timedelta(days=span_days)), START_DATE)
            c_start = rand_date_between(START_DATE, latest_start)
            c_end = min(c_start + timedelta(days=span_days), END_DATE)
            objective = random.choice(CAMPAIGN_OBJECTIVES)
            name = f" {channel}_{objective}_{c_start.strftime('%b%y').lower()} "  # deliberate stray whitespace
            rows.append({
                "campaign_id": campaign_id,
                "campaign_name": name,
                # deliberately inconsistent casing on ~30% of rows -> staging layer normalizes this
                "channel": channel.upper() if random.random() < 0.3 else channel,
                "objective": objective,
                "start_date": c_start.isoformat(),
                "end_date": c_end.isoformat(),
                "daily_budget": round(random.uniform(50, 900), 2),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. CUSTOMER JOURNEYS -> touchpoints (clicks) + orders + customers
# ---------------------------------------------------------------------------
def pick_active_campaign(campaigns_df, channel, on_date):
    chan_norm = channel  # already lowercase key from ALL_CHANNELS
    candidates = campaigns_df[
        (campaigns_df["channel"].str.lower() == chan_norm)
        & (campaigns_df["start_date"] <= on_date.isoformat())
        & (campaigns_df["end_date"] >= on_date.isoformat())
    ]
    if candidates.empty:
        return None
    return candidates.sample(1).iloc[0]["campaign_id"]


def generate_journeys(campaigns_df):
    clicks_rows = []
    orders_rows = []
    customers_rows = []

    click_id = 5_000_000
    order_id = 900_000

    n_touch_choices = [1, 2, 3, 4, 5]
    n_touch_weights = [0.40, 0.30, 0.15, 0.10, 0.05]

    for u in range(1, N_USERS + 1):
        user_id = f"u_{u:06d}"
        n_touches = np.random.choice(n_touch_choices, p=n_touch_weights)

        first_touch_date = rand_date_between(START_DATE, END_DATE - timedelta(days=6))
        touch_time = datetime.combine(first_touch_date, time(hour=random.randint(6, 23), minute=random.randint(0, 59)))

        touched_channels = []
        device = np.random.choice(DEVICE_TYPES, p=DEVICE_WEIGHTS)
        # ~2% of rows missing device_type -> realistic dirty data
        device_for_row = None if random.random() < 0.02 else device
        country = random.choice(COUNTRIES)

        for t in range(n_touches):
            if t > 0:
                gap_days = min(np.random.exponential(scale=3.0), 20)
                touch_time = touch_time + timedelta(days=gap_days, hours=random.randint(0, 12))
                if touch_time.date() > END_DATE:
                    break
            channel = np.random.choice(ALL_CHANNELS, p=CHANNEL_VOL_WEIGHTS)
            touched_channels.append(channel)

            campaign_id = None
            if CHANNELS[channel]["paid"]:
                campaign_id = pick_active_campaign(campaigns_df, channel, touch_time.date())
                if campaign_id is None:
                    # no active campaign that day for this channel -> fall back to direct
                    channel = "direct"
                    touched_channels[-1] = channel

            click_id += 1
            clicks_rows.append({
                "click_id": click_id,
                "user_id": user_id,
                "event_timestamp": touch_time.isoformat(),
                "channel": channel,
                "campaign_id": campaign_id,
                "device_type": device_for_row,
                "landing_page": random.choice(LANDING_PAGES),
                "country": country,
            })

        # ---- decide conversion: combined probability across touched channels ----
        # 1 - product(1 - conv_weight_i) => diminishing-returns synergy from multiple touches
        prob_no_convert = 1.0
        for ch in touched_channels:
            prob_no_convert *= (1 - CHANNELS[ch]["conv_weight"])
        conv_prob = min(1 - prob_no_convert, 0.90)

        converted = random.random() < conv_prob
        signup_date = None
        if converted:
            order_time = touch_time + timedelta(hours=random.uniform(1, 96))
            if order_time.date() > END_DATE:
                order_time = datetime.combine(END_DATE, time(20, 0))
            revenue = float(np.clip(np.random.lognormal(mean=4.1, sigma=0.55), 15, 480))
            category = np.random.choice(PRODUCT_CATEGORIES, p=CATEGORY_WEIGHTS)
            order_id += 1
            orders_rows.append({
                "order_id": order_id,
                "user_id": user_id,
                "order_timestamp": order_time.isoformat(),
                "revenue": round(revenue, 2),
                "product_category": category,
            })
            signup_date = order_time.date().isoformat()

            # ---- repeat purchases: hidden active/dormant customer state ----
                # while "active," the customer keeps buying on a randomized cadence;
                # after each order there's a chance they go dormant and stop for good.
                # this mirrors the generative assumption behind the BG/NBD model
                # fit later in analysis/ltv/btyd_ltv.ipynb.
            is_active = True
            last_purchase_time = order_time
            while is_active:
                if random.random() < P_DORMANT:
                    is_active = False
                    break
                gap_days = np.random.exponential(scale=AVG_DAYS_BETWEEN_PURCHASES)
                next_purchase_time = last_purchase_time + timedelta(days=gap_days)
                if next_purchase_time.date() > END_DATE:
                    break
                repeat_revenue = float(np.clip(np.random.lognormal(mean=4.1, sigma=0.55), 15, 480))
                repeat_category = np.random.choice(PRODUCT_CATEGORIES, p=CATEGORY_WEIGHTS)
                order_id += 1
                orders_rows.append({
                    "order_id": order_id,
                    "user_id": user_id,
                    "order_timestamp": next_purchase_time.isoformat(),
                    "revenue": round(repeat_revenue, 2),
                    "product_category": repeat_category,
                })
                last_purchase_time = next_purchase_time

        customers_rows.append({
            "user_id": user_id,
            "first_seen_date": first_touch_date.isoformat(),
            "signup_date": signup_date,
            "country": country,
            "device_type": device_for_row,
        })

    # ---- "dark" orders: real revenue with zero tracked marketing touchpoints ----
    for _ in range(N_DARK_ORDERS):
        user_id = f"u_dark_{random.randint(100000, 999999)}"
        order_time = datetime.combine(
            rand_date_between(START_DATE, END_DATE), time(hour=random.randint(6, 23))
        )
        revenue = float(np.clip(np.random.lognormal(mean=4.0, sigma=0.5), 15, 400))
        order_id += 1
        orders_rows.append({
            "order_id": order_id,
            "user_id": user_id,
            "order_timestamp": order_time.isoformat(),
            "revenue": round(revenue, 2),
            "product_category": np.random.choice(PRODUCT_CATEGORIES, p=CATEGORY_WEIGHTS),
        })
        customers_rows.append({
            "user_id": user_id,
            "first_seen_date": order_time.date().isoformat(),
            "signup_date": order_time.date().isoformat(),
            "country": random.choice(COUNTRIES),
            "device_type": np.random.choice(DEVICE_TYPES, p=DEVICE_WEIGHTS),
        })

    clicks_df = pd.DataFrame(clicks_rows)
    orders_df = pd.DataFrame(orders_rows)
    customers_df = pd.DataFrame(customers_rows)

    # inject ~0.5% duplicate order rows -> simulates a double-fired purchase pixel
    dupe_sample = orders_df.sample(frac=0.005, random_state=SEED)
    orders_df = pd.concat([orders_df, dupe_sample], ignore_index=True)

    return clicks_df, orders_df, customers_df


# ---------------------------------------------------------------------------
# 5. AD SPEND (derived from, but not identical to, tracked clicks)
# ---------------------------------------------------------------------------
def generate_ad_spend(campaigns_df, clicks_df):
    # tracked (web-analytics-side) clicks per campaign per day
    tracked = (
        clicks_df.dropna(subset=["campaign_id"])
        .assign(event_date=lambda d: pd.to_datetime(d["event_timestamp"], format="ISO8601").dt.date)
        .groupby(["campaign_id", "event_date"])
        .size()
        .rename("tracked_clicks")
        .reset_index()
    )

    rows = []
    for _, camp in campaigns_df.iterrows():
        channel_key = camp["channel"].lower()
        cpc_lo, cpc_hi = CHANNELS[channel_key]["cpc"]
        ctr_lo, ctr_hi = CHANNELS[channel_key]["ctr"]
        c_start = pd.to_datetime(camp["start_date"]).date()
        c_end = pd.to_datetime(camp["end_date"]).date()
        camp_tracked = tracked[tracked["campaign_id"] == camp["campaign_id"]].set_index("event_date")["tracked_clicks"]

        day = c_start
        # gentle upward drift in CPC over the campaign's life, like real auction inflation
        n_days = max((c_end - c_start).days, 1)
        for i in range(n_days + 1):
            day = c_start + timedelta(days=i)
            if day > END_DATE:
                break
            tracked_clicks_today = int(camp_tracked.get(day, 0))
            # ad-platform-reported clicks diverge from tracked sessions (bots, ad-blockers,
            # double counting) -- always a bit higher, sometimes a lot higher
            noise = np.random.uniform(1.05, 1.35)
            baseline = np.random.poisson(3)  # small residual traffic even with 0 tracked touches
            reported_clicks = max(int(round(tracked_clicks_today * noise)) + baseline, baseline)

            ctr = np.random.uniform(ctr_lo, ctr_hi)
            impressions = int(reported_clicks / max(ctr, 0.001))
            drift = 1 + 0.15 * (i / n_days)  # up to +15% CPC drift across the flight
            cpc = np.random.uniform(cpc_lo, cpc_hi) * drift
            spend = round(reported_clicks * cpc, 2)

            rows.append({
                "campaign_id": camp["campaign_id"],
                "date": day.isoformat(),
                "impressions": impressions,
                "clicks": reported_clicks,
                "spend": spend,
            })
    return pd.DataFrame(rows)


def main():
    print(f"Generating synthetic marketing data for {START_DATE} .. {END_DATE} ({TOTAL_DAYS} days)")

    campaigns_df = generate_campaigns()
    clicks_df, orders_df, customers_df = generate_journeys(campaigns_df)
    ad_spend_df = generate_ad_spend(campaigns_df, clicks_df)

    campaigns_df.to_csv(OUT_DIR / "campaigns.csv", index=False)
    ad_spend_df.to_csv(OUT_DIR / "ad_spend.csv", index=False)
    clicks_df.to_csv(OUT_DIR / "clicks.csv", index=False)
    customers_df.to_csv(OUT_DIR / "customers.csv", index=False)
    orders_df.to_csv(OUT_DIR / "orders.csv", index=False)

    print("Wrote raw CSVs to", OUT_DIR)
    print(f"  campaigns : {len(campaigns_df):>7,} rows")
    print(f"  ad_spend  : {len(ad_spend_df):>7,} rows")
    print(f"  clicks    : {len(clicks_df):>7,} rows")
    print(f"  customers : {len(customers_df):>7,} rows")
    print(f"  orders    : {len(orders_df):>7,} rows  (incl. {N_DARK_ORDERS} unattributed 'dark' orders + injected dupes)")


if __name__ == "__main__":
    main()
