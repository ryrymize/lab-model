import streamlit as st
import pandas as pd
import numpy as np
import json
import io
from datetime import datetime

st.set_page_config(page_title="Lab Volume & Staffing Model", layout="wide")

# ── Instrument definitions ──────────────────────────────────────────────────
INSTRUMENTS = {
    # Chemistry / Preanalytic
    "cobas 8100 preanalytic line": {"tph": 600,  "section": "Chemistry"},
    "cobas c702":                  {"tph": 1000, "section": "Chemistry"},
    "cobas c501":                  {"tph": 600,  "section": "Chemistry"},
    "cobas e801":                  {"tph": 300,  "section": "Chemistry"},
    "cobas e602":                  {"tph": 170,  "section": "Chemistry"},
    "Clinitek Advantus":           {"tph": 60,   "section": "Urinalysis"},
    "IRIS iQ200":                  {"tph": 60,   "section": "Urinalysis"},
    "A20 Osmometer":               {"tph": 30,   "section": "Chemistry"},
    "FFN reader (Hologic)":        {"tph": 10,   "section": "Chemistry"},
    # Hematology
    "Sysmex XN-3100":              {"tph": 100,  "section": "Hematology"},
    "Sysmex XN-9100":              {"tph": 200,  "section": "Hematology"},
    "Sysmex SP-50":                {"tph": 50,   "section": "Hematology"},
    "CellaVision DM96":            {"tph": 50,   "section": "Hematology"},
    "CellaVision DM1200":          {"tph": 120,  "section": "Hematology"},
    "iSed (ESR)":                  {"tph": 60,   "section": "Hematology"},
    # Coagulation
    "Werfen ACL TOP 350":          {"tph": 60,   "section": "Coagulation"},
    "Werfen ACL TOP 370":          {"tph": 100,  "section": "Coagulation"},
    "Werfen ACL TOP 750":          {"tph": 200,  "section": "Coagulation"},
    # Manual
    "Manual WBC differential":     {"tph": 12,   "section": "Manual"},
    "Manual body fluid count":     {"tph": 8,    "section": "Manual"},
    "Manual body fluid diff":      {"tph": 6,    "section": "Manual"},
}

LAB_LOCATIONS = ["Core Lab", "Yawkey Lab", "Ragon 1 Lab", "Ragon 2 Lab"]

SECTIONS = sorted(set(v["section"] for v in INSTRUMENTS.values()))

# ── Session state init ──────────────────────────────────────────────────────
def init_state():
    if "phases" not in st.session_state:
        st.session_state.phases = {
            "Current State": {
                "routing": {},
                "growth": {},
                "lab_config": {
                    loc: {
                        "hours": 24 if "Core" in loc else 12,
                        "fte": 4,
                        "instruments": {},
                    }
                    for loc in LAB_LOCATIONS
                },
            }
        }
    if "active_phase" not in st.session_state:
        st.session_state.active_phase = "Current State"
    if "dept_df" not in st.session_state:
        st.session_state.dept_df = pd.DataFrame(columns=["Department", "Section/Type", "Base Vol/Day"])
    if "hourly_df" not in st.session_state:
        st.session_state.hourly_df = pd.DataFrame()

init_state()

def get_phase():
    return st.session_state.phases[st.session_state.active_phase]

def proj_vol(dept_name, base_vol):
    ph = get_phase()
    growth = ph["growth"].get(dept_name, 0)
    return int(base_vol * (1 + growth / 100))

def loc_vol(loc):
    ph = get_phase()
    df = st.session_state.dept_df
    if df.empty:
        return 0
    total = 0
    for _, row in df.iterrows():
        if ph["routing"].get(row["Department"], LAB_LOCATIONS[0]) == loc:
            total += proj_vol(row["Department"], row["Base Vol/Day"])
    return total

def loc_capacity(loc):
    ph = get_phase()
    cfg = ph["lab_config"][loc]
    hrs = cfg["hours"]
    total = 0
    for inst, qty in cfg["instruments"].items():
        tph = INSTRUMENTS.get(inst, {}).get("tph", 0)
        total += tph * qty * hrs
    return total

def util_color(pct):
    if pct == 0:
        return "gray"
    if pct > 100:
        return "red"
    if pct > 80:
        return "orange"
    return "green"

# ── Sidebar: phase management ───────────────────────────────────────────────
with st.sidebar:
    st.header("Project phases")

    phase_names = list(st.session_state.phases.keys())
    chosen = st.radio("Active phase", phase_names, index=phase_names.index(st.session_state.active_phase))
    st.session_state.active_phase = chosen

    st.divider()
    new_name = st.text_input("New phase name", placeholder="e.g. Phase 1 – ED expansion")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Add phase", use_container_width=True):
            if new_name and new_name not in st.session_state.phases:
                import copy
                st.session_state.phases[new_name] = copy.deepcopy(get_phase())
                st.session_state.active_phase = new_name
                st.rerun()
    with col2:
        if st.button("Delete", use_container_width=True, disabled=len(phase_names) <= 1):
            del st.session_state.phases[st.session_state.active_phase]
            st.session_state.active_phase = list(st.session_state.phases.keys())[0]
            st.rerun()

    st.divider()
    st.subheader("Save / load")
    save_data = {
        "phases": st.session_state.phases,
        "dept_df": st.session_state.dept_df.to_dict(orient="records"),
    }
    st.download_button(
        "Download config (JSON)",
        data=json.dumps(save_data, indent=2),
        file_name=f"lab_model_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
        mime="application/json",
        use_container_width=True,
    )
    uploaded_cfg = st.file_uploader("Load config (JSON)", type="json", key="cfg_upload")
    if uploaded_cfg:
        loaded = json.load(uploaded_cfg)
        st.session_state.phases = loaded["phases"]
        st.session_state.dept_df = pd.DataFrame(loaded.get("dept_df", []))
        st.session_state.active_phase = list(loaded["phases"].keys())[0]
        st.success("Config loaded.")
        st.rerun()

# ── Main tabs ───────────────────────────────────────────────────────────────
tab_data, tab_routing, tab_labs, tab_summary, tab_trends = st.tabs([
    "1 · Department data",
    "2 · Routing & growth",
    "3 · Lab configuration",
    "4 · Summary",
    "5 · Volume trends",
])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — Department data upload
# ════════════════════════════════════════════════════════════════════════════
with tab_data:
    st.subheader("Upload department volume data")
    st.markdown("""
Upload a CSV or Excel file with your sending department data.  
**Required columns:** `Department`, `Base Vol/Day`  
**Optional columns:** `Section/Type` (e.g. ED, Clinic, ICU, OR, Inpatient)

You can also upload a separate **hourly breakdown** file for trend analysis.
""")

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("##### Department baseline volumes")
        dept_file = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx"], key="dept_upload")
        if dept_file:
            try:
                if dept_file.name.endswith(".xlsx"):
                    df = pd.read_excel(dept_file)
                else:
                    df = pd.read_csv(dept_file)
                df.columns = [c.strip() for c in df.columns]
                if "Department" not in df.columns or "Base Vol/Day" not in df.columns:
                    st.error("File must have columns: Department, Base Vol/Day")
                else:
                    if "Section/Type" not in df.columns:
                        df["Section/Type"] = "Inpatient"
                    df["Base Vol/Day"] = pd.to_numeric(df["Base Vol/Day"], errors="coerce").fillna(0).astype(int)
                    st.session_state.dept_df = df[["Department", "Section/Type", "Base Vol/Day"]].copy()
                    ph = get_phase()
                    for dept in df["Department"]:
                        if dept not in ph["routing"]:
                            ph["routing"][dept] = LAB_LOCATIONS[0]
                        if dept not in ph["growth"]:
                            ph["growth"][dept] = 0
                    st.success(f"Loaded {len(df)} departments.")
            except Exception as e:
                st.error(f"Error reading file: {e}")

        st.markdown("**Expected file format:**")
        st.dataframe(pd.DataFrame({
            "Department": ["ED Main", "MICU", "Oncology Clinic"],
            "Section/Type": ["ED", "ICU", "Clinic"],
            "Base Vol/Day": [320, 180, 95],
        }), hide_index=True, use_container_width=True)

    with col_right:
        st.markdown("##### Hourly LIS data (for trend charts)")
        st.markdown("""
Export from your LIS with columns:  
`Department`, `Hour` (0–23), `Weekday` (Mon–Sun or 0–6), `Volume`

One row per department × hour × weekday combination.
""")
        hourly_file = st.file_uploader("Upload hourly data CSV or Excel", type=["csv", "xlsx"], key="hourly_upload")
        if hourly_file:
            try:
                if hourly_file.name.endswith(".xlsx"):
                    hdf = pd.read_excel(hourly_file)
                else:
                    hdf = pd.read_csv(hourly_file)
                hdf.columns = [c.strip() for c in hdf.columns]
                required = {"Department", "Hour", "Weekday", "Volume"}
                if not required.issubset(set(hdf.columns)):
                    st.error(f"Hourly file needs columns: {', '.join(required)}")
                else:
                    hdf["Volume"] = pd.to_numeric(hdf["Volume"], errors="coerce").fillna(0)
                    hdf["Hour"] = pd.to_numeric(hdf["Hour"], errors="coerce").fillna(0).astype(int)
                    st.session_state.hourly_df = hdf
                    st.success(f"Loaded {len(hdf)} hourly rows.")
            except Exception as e:
                st.error(f"Error reading file: {e}")

        if not st.session_state.hourly_df.empty:
            hdf = st.session_state.hourly_df
            st.markdown(f"**Loaded:** {hdf['Department'].nunique()} departments, "
                        f"{hdf['Hour'].nunique()} hours, {hdf['Weekday'].nunique()} day types")

    if not st.session_state.dept_df.empty:
        st.divider()
        st.markdown(f"**Current department table — {len(st.session_state.dept_df)} departments**")
        st.dataframe(st.session_state.dept_df, hide_index=True, use_container_width=True, height=300)

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — Routing & growth
# ════════════════════════════════════════════════════════════════════════════
with tab_routing:
    st.subheader(f"Routing & growth — {st.session_state.active_phase}")
    df = st.session_state.dept_df
    if df.empty:
        st.info("Upload department data in Tab 1 first.")
    else:
        ph = get_phase()

        # Filters
        col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
        with col_f1:
            search = st.text_input("Search department", placeholder="Type to filter...")
        with col_f2:
            types = ["All"] + sorted(df["Section/Type"].unique().tolist())
            type_filter = st.selectbox("Filter by type", types)
        with col_f3:
            loc_filter = st.selectbox("Filter by current route", ["All"] + LAB_LOCATIONS)

        filtered = df.copy()
        if search:
            filtered = filtered[filtered["Department"].str.contains(search, case=False, na=False)]
        if type_filter != "All":
            filtered = filtered[filtered["Section/Type"] == type_filter]
        if loc_filter != "All":
            filtered = filtered[filtered["Department"].apply(
                lambda d: ph["routing"].get(d, LAB_LOCATIONS[0]) == loc_filter)]

        st.markdown(f"Showing **{len(filtered)}** of {len(df)} departments")
        st.divider()

        # Batch reroute
        with st.expander("Batch reroute selected departments"):
            batch_search = st.text_input("Match department name contains", key="batch_search")
            batch_type = st.selectbox("Or match by type", ["(any)"] + sorted(df["Section/Type"].unique().tolist()), key="batch_type")
            batch_dest = st.selectbox("Route to", LAB_LOCATIONS, key="batch_dest")
            if st.button("Apply batch reroute"):
                targets = df["Department"].tolist()
                if batch_search:
                    targets = [d for d in targets if batch_search.lower() in d.lower()]
                if batch_type != "(any)":
                    type_set = set(df[df["Section/Type"] == batch_type]["Department"])
                    targets = [d for d in targets if d in type_set]
                for d in targets:
                    ph["routing"][d] = batch_dest
                st.success(f"Rerouted {len(targets)} departments to {batch_dest}.")
                st.rerun()

        # Per-department controls (paginated)
        PAGE_SIZE = 25
        total_pages = max(1, (len(filtered) - 1) // PAGE_SIZE + 1)
        page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1) - 1
        page_df = filtered.iloc[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

        header = st.columns([3, 1, 2, 2, 1, 1])
        for col, label in zip(header, ["Department", "Type", "Routes to", "Growth %", "Base vol", "Proj vol"]):
            col.markdown(f"<span style='font-size:11px;color:gray'>{label}</span>", unsafe_allow_html=True)

        for _, row in page_df.iterrows():
            dept = row["Department"]
            base = int(row["Base Vol/Day"])
            c1, c2, c3, c4, c5, c6 = st.columns([3, 1, 2, 2, 1, 1])
            c1.write(dept)
            c2.write(row["Section/Type"])
            cur_route = ph["routing"].get(dept, LAB_LOCATIONS[0])
            new_route = c3.selectbox("", LAB_LOCATIONS,
                index=LAB_LOCATIONS.index(cur_route),
                key=f"route_{dept}_{st.session_state.active_phase}",
                label_visibility="collapsed")
            ph["routing"][dept] = new_route
            cur_growth = ph["growth"].get(dept, 0)
            new_growth = c4.number_input("", min_value=-100, max_value=500,
                value=int(cur_growth), step=5,
                key=f"growth_{dept}_{st.session_state.active_phase}",
                label_visibility="collapsed")
            ph["growth"][dept] = new_growth
            c5.write(f"{base:,}")
            c6.write(f"{proj_vol(dept, base):,}")

# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — Lab configuration
# ════════════════════════════════════════════════════════════════════════════
with tab_labs:
    st.subheader(f"Lab configuration — {st.session_state.active_phase}")
    ph = get_phase()

    for loc in LAB_LOCATIONS:
        cfg = ph["lab_config"][loc]
        vol = loc_vol(loc)
        cap = loc_capacity(loc)
        util = round(vol / cap * 100) if cap > 0 else (999 if vol > 0 else 0)
        surplus = cap - vol

        color = util_color(util)
        badge = "🔴 Over capacity" if util > 100 else ("🟡 High load" if util > 80 else ("🟢 OK" if util > 0 else "⚪ No data"))

        with st.expander(f"**{loc}** — {vol:,} tests/day in · {util if util < 999 else '—'}% util · {badge}", expanded=True):
            col_ops, col_inst = st.columns([1, 2])

            with col_ops:
                st.markdown("**Operations**")
                cfg["hours"] = st.slider("Hours open/day", 1, 24, cfg["hours"], key=f"hrs_{loc}_{st.session_state.active_phase}")
                cfg["fte"] = st.number_input("FTEs on shift", 0, 50, cfg["fte"], key=f"fte_{loc}_{st.session_state.active_phase}")
                st.metric("Vol routed here", f"{vol:,}", help="Total projected tests/day from all routed departments")
                if cap > 0:
                    st.metric("Analyzer capacity", f"{cap:,}", delta=f"{surplus:+,} surplus" if surplus >= 0 else f"{surplus:,} deficit", delta_color="normal" if surplus >= 0 else "inverse")

            with col_inst:
                st.markdown("**Instruments assigned to this lab**")
                for section in SECTIONS:
                    section_insts = [i for i, v in INSTRUMENTS.items() if v["section"] == section]
                    st.markdown(f"<span style='font-size:11px;color:gray;text-transform:uppercase'>{section}</span>", unsafe_allow_html=True)
                    cols = st.columns(min(3, len(section_insts)))
                    for idx, inst in enumerate(section_insts):
                        with cols[idx % 3]:
                            qty = cfg["instruments"].get(inst, 0)
                            new_qty = st.number_input(
                                inst, min_value=0, max_value=20, value=qty, step=1,
                                key=f"inst_{loc}_{inst}_{st.session_state.active_phase}",
                                help=f"{INSTRUMENTS[inst]['tph']} tests/hr each"
                            )
                            cfg["instruments"][inst] = new_qty

# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — Summary
# ════════════════════════════════════════════════════════════════════════════
with tab_summary:
    st.subheader(f"Summary — {st.session_state.active_phase}")
    ph = get_phase()
    df = st.session_state.dept_df

    # Top metrics
    total_vol = sum(loc_vol(loc) for loc in LAB_LOCATIONS)
    total_cap = sum(loc_capacity(loc) for loc in LAB_LOCATIONS)
    overloaded = sum(1 for loc in LAB_LOCATIONS if (lv := loc_vol(loc)) > 0 and loc_capacity(loc) > 0 and lv > loc_capacity(loc))
    total_fte = sum(ph["lab_config"][loc]["fte"] for loc in LAB_LOCATIONS)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total projected vol/day", f"{total_vol:,}")
    m2.metric("Total analyzer capacity", f"{total_cap:,}")
    m3.metric("Overloaded labs", overloaded, delta="action needed" if overloaded else "all OK", delta_color="inverse" if overloaded else "off")
    m4.metric("Total FTEs", total_fte)

    st.divider()

    # Per-location table
    rows = []
    for loc in LAB_LOCATIONS:
        vol = loc_vol(loc)
        cap = loc_capacity(loc)
        util = round(vol / cap * 100) if cap > 0 else None
        surplus = (cap - vol) if cap > 0 else None
        cfg = ph["lab_config"][loc]
        depts_here = [row["Department"] for _, row in df.iterrows()
                      if ph["routing"].get(row["Department"], LAB_LOCATIONS[0]) == loc] if not df.empty else []
        insts_here = [f"{qty}× {inst}" for inst, qty in cfg["instruments"].items() if qty > 0]
        rows.append({
            "Lab": loc,
            "Hours": cfg["hours"],
            "FTEs": cfg["fte"],
            "Depts routed": len(depts_here),
            "Vol/day": vol,
            "Capacity/day": cap if cap > 0 else "—",
            "Util %": f"{util}%" if util is not None else "—",
            "Surplus": f"{surplus:+,}" if surplus is not None else "—",
            "Status": "🔴 Over" if (util or 0) > 100 else ("🟡 High" if (util or 0) > 80 else ("🟢 OK" if vol > 0 else "⚪")),
            "Instruments": ", ".join(insts_here) if insts_here else "None assigned",
        })

    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.divider()

    # Phase comparison
    if len(st.session_state.phases) > 1:
        st.subheader("Phase comparison")
        comp_rows = []
        for phase_name, phase_data in st.session_state.phases.items():
            for loc in LAB_LOCATIONS:
                # compute vol for this phase
                v = 0
                if not df.empty:
                    for _, row in df.iterrows():
                        growth = phase_data["growth"].get(row["Department"], 0)
                        pv = int(row["Base Vol/Day"] * (1 + growth / 100))
                        if phase_data["routing"].get(row["Department"], LAB_LOCATIONS[0]) == loc:
                            v += pv
                cfg = phase_data["lab_config"][loc]
                c = sum(INSTRUMENTS.get(inst, {}).get("tph", 0) * qty * cfg["hours"]
                        for inst, qty in cfg["instruments"].items())
                comp_rows.append({
                    "Phase": phase_name,
                    "Lab": loc,
                    "Vol/day": v,
                    "Capacity/day": c if c > 0 else 0,
                    "Util %": round(v / c * 100) if c > 0 else None,
                })
        comp_df = pd.DataFrame(comp_rows)

        try:
            import plotly.express as px
            fig = px.bar(comp_df, x="Lab", y="Vol/day", color="Phase", barmode="group",
                         title="Volume by lab across phases")
            fig.add_scatter(x=comp_df[comp_df["Phase"] == list(st.session_state.phases.keys())[0]]["Lab"],
                            y=comp_df[comp_df["Phase"] == list(st.session_state.phases.keys())[0]]["Capacity/day"],
                            mode="markers", name="Capacity", marker=dict(symbol="line-ew", size=12, color="black"))
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.dataframe(comp_df, hide_index=True, use_container_width=True)

    # Department routing summary
    if not df.empty:
        st.divider()
        st.subheader("Department routing detail")
        routing_rows = []
        for _, row in df.iterrows():
            dept = row["Department"]
            base = int(row["Base Vol/Day"])
            pv = proj_vol(dept, base)
            routing_rows.append({
                "Department": dept,
                "Type": row["Section/Type"],
                "Routes to": ph["routing"].get(dept, LAB_LOCATIONS[0]),
                "Growth %": ph["growth"].get(dept, 0),
                "Base vol/day": base,
                "Projected vol/day": pv,
            })
        rdf = pd.DataFrame(routing_rows)
        search2 = st.text_input("Filter departments", key="summary_search")
        if search2:
            rdf = rdf[rdf["Department"].str.contains(search2, case=False)]
        st.dataframe(rdf, hide_index=True, use_container_width=True, height=400)

        csv_out = rdf.to_csv(index=False)
        st.download_button("Download routing table (CSV)", csv_out,
                           file_name=f"routing_{st.session_state.active_phase}.csv", mime="text/csv")

# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — Volume trends
# ════════════════════════════════════════════════════════════════════════════
with tab_trends:
    st.subheader("Volume trends")
    hdf = st.session_state.hourly_df

    if hdf.empty:
        st.info("Upload hourly LIS data in Tab 1 to enable trend charts.")
    else:
        ph = get_phase()
        df = st.session_state.dept_df

        # Apply growth multipliers to hourly data
        growth_map = {dept: ph["growth"].get(dept, 0) for dept in hdf["Department"].unique()}
        hdf_adj = hdf.copy()
        hdf_adj["Multiplier"] = hdf_adj["Department"].map(
            lambda d: 1 + ph["growth"].get(d, 0) / 100
        )
        hdf_adj["Volume_adj"] = hdf_adj["Volume"] * hdf_adj["Multiplier"]

        # Map departments to lab locations
        hdf_adj["Lab"] = hdf_adj["Department"].map(
            lambda d: ph["routing"].get(d, LAB_LOCATIONS[0])
        )

        # Weekday classification
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        weekend_days = ["Saturday", "Sunday"]

        # Normalize Weekday column
        if hdf_adj["Weekday"].dtype in [int, float]:
            day_map = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
                       4: "Friday", 5: "Saturday", 6: "Sunday"}
            hdf_adj["Weekday"] = hdf_adj["Weekday"].map(day_map)

        hdf_adj["DayType"] = hdf_adj["Weekday"].apply(
            lambda d: "Weekday" if d in weekday_days else "Weekend"
        )

        try:
            import plotly.express as px
            import plotly.graph_objects as go

            view_opts = ["By hour of day", "By shift", "Weekday vs weekend", "By lab (all hours)"]
            view = st.radio("View", view_opts, horizontal=True)
            loc_sel = st.multiselect("Labs to show", LAB_LOCATIONS, default=LAB_LOCATIONS)
            filtered_h = hdf_adj[hdf_adj["Lab"].isin(loc_sel)]

            if view == "By hour of day":
                day_type = st.radio("Day type", ["All", "Weekday", "Weekend"], horizontal=True)
                if day_type != "All":
                    filtered_h = filtered_h[filtered_h["DayType"] == day_type]
                hourly = filtered_h.groupby(["Lab", "Hour"])["Volume_adj"].sum().reset_index()
                hourly["Hour_label"] = hourly["Hour"].apply(lambda h: f"{h:02d}:00")
                fig = px.line(hourly, x="Hour", y="Volume_adj", color="Lab",
                              title=f"Projected volume by hour — {day_type}",
                              labels={"Volume_adj": "Tests", "Hour": "Hour of day"})
                fig.update_xaxes(tickvals=list(range(0, 24)), ticktext=[f"{h:02d}:00" for h in range(24)])
                st.plotly_chart(fig, use_container_width=True)

                # Shift breakdown
                st.markdown("**Shift summary**")
                def shift(h):
                    if 7 <= h < 15: return "Day (07:00–15:00)"
                    elif 15 <= h < 23: return "Evening (15:00–23:00)"
                    else: return "Night (23:00–07:00)"
                filtered_h2 = filtered_h.copy()
                filtered_h2["Shift"] = filtered_h2["Hour"].apply(shift)
                shift_agg = filtered_h2.groupby(["Lab", "Shift"])["Volume_adj"].sum().reset_index()
                st.dataframe(shift_agg.rename(columns={"Volume_adj": "Projected vol"}),
                             hide_index=True, use_container_width=True)

            elif view == "By shift":
                def shift(h):
                    if 7 <= h < 15: return "Day"
                    elif 15 <= h < 23: return "Evening"
                    else: return "Night"
                filtered_h2 = filtered_h.copy()
                filtered_h2["Shift"] = filtered_h2["Hour"].apply(shift)
                shift_agg = filtered_h2.groupby(["Lab", "Shift", "DayType"])["Volume_adj"].sum().reset_index()
                fig = px.bar(shift_agg, x="Shift", y="Volume_adj", color="Lab", barmode="group",
                             facet_col="DayType",
                             title="Volume by shift and day type",
                             labels={"Volume_adj": "Tests"},
                             category_orders={"Shift": ["Day", "Evening", "Night"]})
                st.plotly_chart(fig, use_container_width=True)

            elif view == "Weekday vs weekend":
                day_agg = filtered_h.groupby(["Lab", "Weekday"])["Volume_adj"].sum().reset_index()
                day_agg["Weekday"] = pd.Categorical(day_agg["Weekday"], categories=day_order, ordered=True)
                day_agg = day_agg.sort_values("Weekday")
                fig = px.bar(day_agg, x="Weekday", y="Volume_adj", color="Lab", barmode="group",
                             title="Volume by day of week",
                             labels={"Volume_adj": "Tests", "Weekday": ""})
                st.plotly_chart(fig, use_container_width=True)

            elif view == "By lab (all hours)":
                pivot = filtered_h.groupby(["Lab", "Hour"])["Volume_adj"].sum().unstack(fill_value=0)
                fig = go.Figure()
                for lab in pivot.index:
                    fig.add_trace(go.Bar(name=lab, x=list(pivot.columns), y=list(pivot.loc[lab])))
                fig.update_layout(barmode="stack", title="Stacked volume by hour across all labs",
                                  xaxis_title="Hour", yaxis_title="Tests")
                fig.update_xaxes(tickvals=list(range(0, 24)), ticktext=[f"{h:02d}:00" for h in range(24)])
                st.plotly_chart(fig, use_container_width=True)

            # Capacity overlay
            st.divider()
            st.markdown("**Hourly capacity vs volume (averaged per hour)**")
            for loc in loc_sel:
                cap_per_hr = sum(
                    INSTRUMENTS.get(inst, {}).get("tph", 0) * qty
                    for inst, qty in ph["lab_config"][loc]["instruments"].items()
                )
                if cap_per_hr > 0:
                    loc_h = hdf_adj[hdf_adj["Lab"] == loc].groupby("Hour")["Volume_adj"].mean().reset_index()
                    fig2 = px.line(loc_h, x="Hour", y="Volume_adj",
                                   title=f"{loc} — avg hourly volume vs capacity",
                                   labels={"Volume_adj": "Tests/hr avg", "Hour": "Hour"})
                    fig2.add_hline(y=cap_per_hr, line_dash="dash", line_color="red",
                                   annotation_text=f"Max throughput: {cap_per_hr}/hr")
                    fig2.update_xaxes(tickvals=list(range(0, 24)), ticktext=[f"{h:02d}:00" for h in range(24)])
                    st.plotly_chart(fig2, use_container_width=True)

        except ImportError:
            st.warning("Install plotly for charts: pip install plotly")
            st.dataframe(hdf_adj.groupby(["Lab", "Hour"])["Volume_adj"].sum().reset_index(),
                         use_container_width=True)
