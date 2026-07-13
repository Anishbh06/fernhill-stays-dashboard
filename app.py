import streamlit as st
import pandas as pd
import plotly.express as px

# ── Page Config ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Fernhill Stays Dashboard",
    page_icon="🏨",
    layout="wide",
)

# ── Load & Prepare Data ──────────────────────────────────────────────────
@st.cache_data
def load_data():
    df = pd.read_csv("data/bookings_clean.csv")
    df["check_in_date"] = pd.to_datetime(df["check_in_date"], errors="coerce")
    df["month"] = df["check_in_date"].dt.to_period("M").astype(str)
    return df

df = load_data()

# ── Colour palette ────────────────────────────────────────────────────────
PROPERTY_COLORS = {
    "Birchwood Stay": "#6366f1",
    "Cedar Court": "#06b6d4",
    "Lakeview Residency": "#10b981",
    "Marigold Suites": "#f59e0b",
    "Palm Grove Inn": "#ef4444",
}
CHANNEL_COLORS = {
    "Direct": "#6366f1",
    "OTA-MMT": "#06b6d4",
    "Walk-In": "#10b981",
    "Corporate": "#f59e0b",
    "OTA-Booking": "#ef4444",
}

# ── Sidebar Filters ──────────────────────────────────────────────────────
st.sidebar.title("🔍 Filters")

properties = st.sidebar.multiselect(
    "Properties",
    options=sorted(df["property"].unique()),
    default=sorted(df["property"].unique()),
)
channels = st.sidebar.multiselect(
    "Channels",
    options=sorted(df["booking_channel"].dropna().unique()),
    default=sorted(df["booking_channel"].dropna().unique()),
)
months = st.sidebar.multiselect(
    "Months",
    options=sorted(df["month"].dropna().unique()),
    default=sorted(df["month"].dropna().unique()),
)

# Apply filters
mask = (
    df["property"].isin(properties)
    & (df["booking_channel"].isin(channels) | df["booking_channel"].isna())
    & df["month"].isin(months)
)
fdf = df[mask].copy()

if len(fdf) == 0:
    st.warning("No data matches the selected filters. Please adjust your selections.")
    st.stop()

completed = fdf[fdf["status"].isin(["Checked-Out", "Confirmed"])]
cancelled = fdf[fdf["status"].isin(["Cancelled", "No-Show"])]

# ── Header ────────────────────────────────────────────────────────────────
st.title("🏨 Fernhill Stays — Performance Dashboard")
st.caption(
    "Data: Jan–May 2026 · Cleaned from `bookings_jan_may_2026.csv` · "
    f"{len(fdf)} bookings shown"
)

# ── Top-level KPI Cards ──────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
total_rev = completed["realized_revenue"].sum()
total_bookings = len(fdf)
cancel_rate = len(cancelled) / len(fdf) * 100 if len(fdf) > 0 else 0
# Exclude zero-night and missing-rate rows from ADR
adr_rows = completed[(completed["nights"] > 0) & (completed["nightly_rate_inr"].notna())]
avg_rate = adr_rows["nightly_rate_inr"].mean() if len(adr_rows) > 0 else 0
# Revenue lost to cancellations (what could have been earned)
rev_lost = cancelled["total_amount_inr"].sum()

k1.metric("💰 Realized Revenue", f"₹{total_rev:,.0f}")
k2.metric("📋 Total Bookings", f"{total_bookings}")
k3.metric("❌ Cancellation Rate", f"{cancel_rate:.1f}%")
k4.metric("🏷️ Avg Nightly Rate", f"₹{avg_rate:,.0f}")
k5.metric("💸 Revenue Lost", f"₹{rev_lost:,.0f}", help="Potential revenue from cancelled/no-show bookings")

# ── What to do next (client-facing, filter-aware) ─────────────────────────
prop_cancel_rows = []
for prop, g in fdf.groupby("property"):
    prop_cancel_rows.append({
        "property": prop,
        "cancel_rate": len(g[g["status"].isin(["Cancelled", "No-Show"])]) / len(g),
        "n": len(g),
    })
prop_cancel = pd.DataFrame(prop_cancel_rows)
worst_prop_row = prop_cancel.sort_values(["cancel_rate", "n"], ascending=[False, False]).iloc[0]

ch_stats = []
for ch, g in fdf[fdf["booking_channel"].notna()].groupby("booking_channel"):
    cc = g[g["status"].isin(["Checked-Out", "Confirmed"])]
    cancel_n = len(g[g["status"].isin(["Cancelled", "No-Show"])])
    ch_stats.append({
        "channel": ch,
        "cancel_rate": cancel_n / len(g),
        "avg_value": cc["realized_revenue"].mean() if len(cc) else 0.0,
        "n": len(g),
    })
ch_df = pd.DataFrame(ch_stats)
best_ch = ch_df.sort_values(["avg_value", "cancel_rate"], ascending=[False, True]).iloc[0] if len(ch_df) else None
worst_ch = ch_df.sort_values(["cancel_rate", "avg_value"], ascending=[False, True]).iloc[0] if len(ch_df) else None

st.info(
    f"**Where to focus (current filters)**\n\n"
    f"1. **{worst_prop_row['property']}** — {worst_prop_row['cancel_rate']*100:.0f}% cancellation rate "
    f"({int(worst_prop_row['n'])} bookings). Fix conversion before chasing rate.\n"
    f"2. **Channels** — "
    + (
        f"lean into **{best_ch['channel']}** (avg ₹{best_ch['avg_value']:,.0f}, "
        f"{best_ch['cancel_rate']*100:.0f}% cancel) and tighten **{worst_ch['channel']}** "
        f"({worst_ch['cancel_rate']*100:.0f}% cancel, avg ₹{worst_ch['avg_value']:,.0f})."
        if best_ch is not None and worst_ch is not None
        else "apply a channel filter to compare value vs reliability."
    )
    + f"\n3. **Revenue at risk** — ₹{rev_lost:,.0f} tied up in cancelled/no-show bookings "
    f"({cancel_rate:.0f}% of bookings in view)."
)

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "📊 Property Performance",
    "📡 Channel Analysis",
    "💯 Health Score",
])

# ======================================================================
# TAB 1: PROPERTY PERFORMANCE
# ======================================================================
with tab1:
    st.subheader("How is each property doing?")

    # Revenue by Property
    prop_rev = (
        completed.groupby("property")["realized_revenue"]
        .sum()
        .reset_index()
        .sort_values("realized_revenue", ascending=True)
    )
    fig_rev = px.bar(
        prop_rev,
        x="realized_revenue",
        y="property",
        orientation="h",
        color="property",
        color_discrete_map=PROPERTY_COLORS,
        labels={"realized_revenue": "Realized Revenue (₹)", "property": ""},
        title="Revenue by Property",
    )
    fig_rev.update_layout(showlegend=False, height=350)
    fig_rev.update_traces(texttemplate="₹%{x:,.0f}", textposition="outside")
    st.plotly_chart(fig_rev, use_container_width=True)

    # Monthly Trend
    monthly = (
        completed.groupby(["month", "property"])["realized_revenue"]
        .sum()
        .reset_index()
    )
    fig_trend = px.line(
        monthly,
        x="month",
        y="realized_revenue",
        color="property",
        color_discrete_map=PROPERTY_COLORS,
        markers=True,
        labels={"realized_revenue": "Revenue (₹)", "month": "Month", "property": "Property"},
        title="Monthly Revenue Trend",
    )
    fig_trend.update_layout(height=350)
    st.plotly_chart(fig_trend, use_container_width=True)

    # Booking Status Breakdown
    col_status1, col_status2 = st.columns(2)
    with col_status1:
        status_counts = fdf.groupby(["property", "status"]).size().reset_index(name="count")
        fig_status = px.bar(
            status_counts,
            x="property",
            y="count",
            color="status",
            barmode="stack",
            title="Booking Status by Property",
            labels={"count": "Bookings", "property": "Property", "status": "Status"},
            color_discrete_map={"Checked-Out": "#10b981", "Confirmed": "#6366f1", "Cancelled": "#ef4444", "No-Show": "#f59e0b"},
        )
        fig_status.update_layout(height=350)
        st.plotly_chart(fig_status, use_container_width=True)

    with col_status2:
        room_type_rev = (
            completed.groupby("room_type")["realized_revenue"]
            .sum()
            .reset_index()
        )
        fig_room = px.pie(
            room_type_rev,
            values="realized_revenue",
            names="room_type",
            title="Revenue by Room Type",
            color_discrete_sequence=["#6366f1", "#10b981", "#f59e0b"],
        )
        fig_room.update_layout(height=350)
        st.plotly_chart(fig_room, use_container_width=True)

    # Property Summary Table
    st.subheader("Property Summary")
    prop_summary = []
    for prop in sorted(fdf["property"].unique()):
        p = fdf[fdf["property"] == prop]
        pc = completed[completed["property"] == prop]
        px_cancel = cancelled[cancelled["property"] == prop]
        adr = pc[(pc["nights"] > 0) & (pc["nightly_rate_inr"].notna())]["nightly_rate_inr"].mean()

        prop_summary.append({
            "Property": prop,
            "Total Bookings": len(p),
            "Completed": len(pc),
            "Cancelled/No-Show": len(px_cancel),
            "Cancel Rate": f"{len(px_cancel)/len(p)*100:.0f}%" if len(p) > 0 else "0%",
            "Revenue (₹)": f"{pc['realized_revenue'].sum():,.0f}",
            "Avg Rate (₹)": f"{adr:,.0f}" if pd.notna(adr) else "N/A",
            "Room-Nights": f"{pc['nights'].sum():.0f}",
        })
    st.dataframe(pd.DataFrame(prop_summary), use_container_width=True, hide_index=True)

# ======================================================================
# TAB 2: CHANNEL ANALYSIS
# ======================================================================
with tab2:
    st.subheader("Which booking channels are worth it?")

    # Channel Revenue
    ch_rev = (
        completed[completed["booking_channel"].notna()]
        .groupby("booking_channel")["realized_revenue"]
        .sum()
        .reset_index()
        .sort_values("realized_revenue", ascending=True)
    )
    fig_ch = px.bar(
        ch_rev,
        x="realized_revenue",
        y="booking_channel",
        orientation="h",
        color="booking_channel",
        color_discrete_map=CHANNEL_COLORS,
        labels={"realized_revenue": "Revenue (₹)", "booking_channel": ""},
        title="Revenue by Channel",
    )
    fig_ch.update_layout(showlegend=False, height=350)
    fig_ch.update_traces(texttemplate="₹%{x:,.0f}", textposition="outside")
    st.plotly_chart(fig_ch, use_container_width=True)

    # Channel Cancellation Rate comparison
    col_a, col_b = st.columns(2)
    with col_a:
        ch_cancel = []
        for ch in sorted(fdf["booking_channel"].dropna().unique()):
            c = fdf[fdf["booking_channel"] == ch]
            cx = c[c["status"].isin(["Cancelled", "No-Show"])]
            ch_cancel.append({
                "Channel": ch,
                "Cancel Rate (%)": len(cx) / len(c) * 100 if len(c) > 0 else 0,
            })
        ch_cancel_df = pd.DataFrame(ch_cancel).sort_values("Cancel Rate (%)", ascending=True)
        fig_cancel = px.bar(
            ch_cancel_df,
            x="Cancel Rate (%)",
            y="Channel",
            orientation="h",
            color="Channel",
            color_discrete_map=CHANNEL_COLORS,
            title="Cancellation Rate by Channel",
        )
        fig_cancel.update_layout(showlegend=False, height=300)
        fig_cancel.update_traces(texttemplate="%{x:.0f}%", textposition="outside")
        st.plotly_chart(fig_cancel, use_container_width=True)

    with col_b:
        ch_avg = (
            completed[completed["booking_channel"].notna()]
            .groupby("booking_channel")["realized_revenue"]
            .mean()
            .reset_index()
            .rename(columns={"realized_revenue": "Avg Booking Value (₹)"})
            .sort_values("Avg Booking Value (₹)", ascending=True)
        )
        fig_avg = px.bar(
            ch_avg,
            x="Avg Booking Value (₹)",
            y="booking_channel",
            orientation="h",
            color="booking_channel",
            color_discrete_map=CHANNEL_COLORS,
            title="Avg Booking Value by Channel",
        )
        fig_avg.update_layout(showlegend=False, height=300)
        fig_avg.update_traces(texttemplate="₹%{x:,.0f}", textposition="outside")
        st.plotly_chart(fig_avg, use_container_width=True)

    # Channel mix per property (stacked bar)
    ch_mix = (
        completed[completed["booking_channel"].notna()]
        .groupby(["property", "booking_channel"])["realized_revenue"]
        .sum()
        .reset_index()
    )
    fig_mix = px.bar(
        ch_mix,
        x="property",
        y="realized_revenue",
        color="booking_channel",
        color_discrete_map=CHANNEL_COLORS,
        labels={"realized_revenue": "Revenue (₹)", "property": "Property", "booking_channel": "Channel"},
        title="Channel Mix per Property",
        barmode="stack",
    )
    fig_mix.update_layout(height=400)
    st.plotly_chart(fig_mix, use_container_width=True)

    # Channel Summary Table
    st.subheader("Channel Summary")
    ch_summary = []
    for ch in sorted(fdf["booking_channel"].dropna().unique()):
        c = fdf[fdf["booking_channel"] == ch]
        cc = completed[completed["booking_channel"] == ch]
        cx = c[c["status"].isin(["Cancelled", "No-Show"])]

        ch_summary.append({
            "Channel": ch,
            "Bookings": len(c),
            "Completed": len(cc),
            "Cancel Rate": f"{len(cx)/len(c)*100:.0f}%" if len(c) > 0 else "0%",
            "Revenue (₹)": f"{cc['realized_revenue'].sum():,.0f}",
            "Avg Value (₹)": f"{cc['realized_revenue'].mean():,.0f}" if len(cc) > 0 else "N/A",
        })
    st.dataframe(pd.DataFrame(ch_summary), use_container_width=True, hide_index=True)

    # Note about missing channels
    missing_ch = fdf["booking_channel"].isna().sum()
    if missing_ch > 0:
        st.info(f"ℹ️ {missing_ch} bookings have no channel recorded and are excluded from channel analysis. Their revenue is still counted in property totals.")

# ======================================================================
# TAB 3: HEALTH SCORE
# ======================================================================
with tab3:
    st.subheader("Property Health Score — Where to Focus")
    st.caption(
        "Score = 30% Occupancy (room-nights) + 25% Revenue + 25% Cancellation + 20% Avg Rate · "
        "Normalised 0–100 against the best-performing property."
    )

    # Calculate sub-scores
    health_data = []
    for prop in sorted(fdf["property"].unique()):
        p = fdf[fdf["property"] == prop]
        pc = completed[completed["property"] == prop]
        px_cancel = cancelled[cancelled["property"] == prop]
        adr_valid = pc[(pc["nights"] > 0) & (pc["nightly_rate_inr"].notna())]

        health_data.append({
            "property": prop,
            "room_nights": pc["nights"].sum(),
            "revenue": pc["realized_revenue"].sum(),
            "cancel_rate": len(px_cancel) / len(p) if len(p) > 0 else 0,
            "avg_rate": adr_valid["nightly_rate_inr"].mean() if len(adr_valid) > 0 else 0,
        })

    hdf = pd.DataFrame(health_data)

    # Normalise each metric 0–100
    max_rn = hdf["room_nights"].max() if hdf["room_nights"].max() > 0 else 1
    max_rev = hdf["revenue"].max() if hdf["revenue"].max() > 0 else 1
    max_rate = hdf["avg_rate"].max() if hdf["avg_rate"].max() > 0 else 1
    min_cancel = hdf["cancel_rate"].min()
    max_cancel = hdf["cancel_rate"].max()
    cancel_range = max_cancel - min_cancel if max_cancel > min_cancel else 1

    hdf["occ_score"] = (hdf["room_nights"] / max_rn) * 100
    hdf["rev_score"] = (hdf["revenue"] / max_rev) * 100
    hdf["cancel_score"] = (1 - (hdf["cancel_rate"] - min_cancel) / cancel_range) * 100
    hdf["rate_score"] = (hdf["avg_rate"] / max_rate) * 100

    hdf["health_score"] = (
        0.30 * hdf["occ_score"]
        + 0.25 * hdf["rev_score"]
        + 0.25 * hdf["cancel_score"]
        + 0.20 * hdf["rate_score"]
    )

    hdf = hdf.sort_values("health_score", ascending=False)

    # Score cards
    cols = st.columns(len(hdf))
    for i, (_, row) in enumerate(hdf.iterrows()):
        score = row["health_score"]
        if score >= 75:
            color = "🟢"
        elif score >= 50:
            color = "🟡"
        else:
            color = "🔴"

        with cols[i]:
            st.metric(
                label=f"{color} {row['property']}",
                value=f"{score:.0f}/100",
            )

    st.divider()

    # Sub-score breakdown chart
    sub_scores = hdf[["property", "occ_score", "rev_score", "cancel_score", "rate_score"]].melt(
        id_vars="property",
        var_name="Component",
        value_name="Score",
    )
    component_labels = {
        "occ_score": "Occupancy (30%)",
        "rev_score": "Revenue (25%)",
        "cancel_score": "Cancellation (25%)",
        "rate_score": "Rate (20%)",
    }
    sub_scores["Component"] = sub_scores["Component"].map(component_labels)

    fig_health = px.bar(
        sub_scores,
        x="property",
        y="Score",
        color="Component",
        barmode="group",
        title="Health Score Breakdown",
        labels={"property": "Property", "Score": "Sub-Score (0–100)"},
        color_discrete_sequence=["#6366f1", "#10b981", "#ef4444", "#f59e0b"],
    )
    fig_health.update_layout(height=400)
    st.plotly_chart(fig_health, use_container_width=True)

    # Detailed table
    st.subheader("Score Details")
    score_table = hdf[["property", "occ_score", "rev_score", "cancel_score", "rate_score", "health_score"]].copy()
    score_table.columns = ["Property", "Occupancy (30%)", "Revenue (25%)", "Cancellation (25%)", "Rate (20%)", "Health Score"]
    for col in score_table.columns[1:]:
        score_table[col] = score_table[col].apply(lambda x: f"{x:.1f}")
    st.dataframe(score_table, use_container_width=True, hide_index=True)

    # Interpretation (reason from actual component gaps — not always "highest cancel")
    best = hdf.iloc[0]
    worst = hdf.iloc[-1]
    gap_cols = {
        "occupancy (room-nights)": "occ_score",
        "revenue": "rev_score",
        "cancellation reliability": "cancel_score",
        "average rate": "rate_score",
    }
    weakest_component = min(gap_cols, key=lambda label: worst[gap_cols[label]])
    st.success(f"✅ **{best['property']}** is the strongest property (score: {best['health_score']:.0f}/100)")
    st.error(
        f"🚨 **{worst['property']}** needs attention (score: {worst['health_score']:.0f}/100). "
        f"Weakest component: **{weakest_component}** "
        f"(cancel rate {worst['cancel_rate']*100:.0f}%)."
    )

    with st.expander("📐 How is the Health Score calculated?"):
        st.markdown("""
**Health Score = (0.30 × Occupancy) + (0.25 × Revenue) + (0.25 × Cancellation) + (0.20 × Rate)**

| Component | Weight | What it measures |
|---|---|---|
| **Occupancy** | 30% | Total room-nights sold, normalised against the best property |
| **Revenue** | 25% | Total realized revenue, normalised against the best property |
| **Cancellation** | 25% | Inverse of cancellation rate — lower cancellation = higher score |
| **Rate** | 20% | Average nightly rate for completed bookings |

**What's excluded:** True occupancy % (no room inventory data), seasonality adjustment, guest satisfaction, cost/profit margins.

**Weakness:** Without room inventory, a property with more rooms naturally sells more room-nights. The score reflects output volume, not efficiency per room.
        """)

# ── Footer ────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Built for Fernhill Stays · Data cleaned via `clean_data.py` · "
    "Charts use `realized_revenue` (cancelled/no-show bookings excluded)"
)

# Data quality note
with st.sidebar.expander("📋 Data Quality Notes"):
    st.markdown(f"""
- **{len(df)}** bookings after deduplication
- **{df['amount_error_flag'].sum()}** amount errors corrected
- **{df[df['status'].isin(['Cancelled', 'No-Show'])].shape[0]}** cancelled/no-show excluded from revenue
- **{df['missing_rate_flag'].sum()}** missing nightly rates
- **{df['missing_amount_flag'].sum()}** missing amounts
- **{df['missing_channel_flag'].sum()}** missing channels
- **{df['zero_night_anomaly'].sum()}** zero-night anomalies
    """)
