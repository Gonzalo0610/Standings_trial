import streamlit as st
import pandas as pd
import numpy as np
import requests

# =====================================================
# ----------------- EUROLEAGUE FUNCTIONS ---------------
# =====================================================

def actual_calendar_EL():
    url = "https://api-live.euroleague.net/v2/competitions/E/seasons/E2025/games"
    response = requests.get(url).json()["data"]

    local, visiting, local_name, visitor_name = [], [], [], []
    plusminus, lscore, vscore, lw, vw, round_ = [], [], [], [], [], []
    sanctioned = set()

    for i in response:
        l_team = i["local"]["club"]["code"]
        v_team = i["road"]["club"]["code"]
        l_score = i["local"]["score"]
        v_score = i["road"]["score"]
        l_stand = i["local"]["standingsScore"]
        v_stand = i["road"]["standingsScore"]

        local.append(l_team)
        visiting.append(v_team)
        local_name.append(i["local"]["club"]["name"])
        visitor_name.append(i["road"]["club"]["name"])
        round_.append(i["round"])

        if l_score == 20 and v_score == 0:
            sanctioned.add(v_team)
        elif l_score == 0 and v_score == 20:
            sanctioned.add(l_team)

        if l_score > v_score:
            plusminus.append(l_stand - v_stand)
            lscore.append(l_stand)
            vscore.append(v_stand)
            lw.append(1)
            vw.append(0)
        elif l_score < v_score:
            plusminus.append(l_stand - v_stand)
            lscore.append(l_stand)
            vscore.append(v_stand)
            lw.append(0)
            vw.append(1)
        else:
            plusminus.append(np.nan)
            lscore.append(np.nan)
            vscore.append(np.nan)
            lw.append(np.nan)
            vw.append(np.nan)

    return pd.DataFrame({
        "Local": local, "Visitor": visiting,
        "Local_Name": local_name, "Visitor_Name": visitor_name,
        "HomeWin": lw, "RoadWin": vw,
        "HomeScore": lscore, "RoadScore": vscore,
        "PlusMinus": plusminus, "Round": round_
    }), list(sanctioned)


def compute_standings_with_bylaws(df, sanctioned_teams=None):
    if sanctioned_teams is None:
        sanctioned_teams = []

    teams = pd.unique(df[["Local", "Visitor"]].values.ravel())
    standings = {team: {"W": 0, "L": 0, "PF": 0, "PA": 0, "Games": 0, "Sanctioned": team in sanctioned_teams} for team in teams}

    for _, row in df.iterrows():
        if np.isnan(row["HomeWin"]):
            continue
        home, away = row["Local"], row["Visitor"]
        hs, rs = row["HomeScore"], row["RoadScore"]

        standings[home]["Games"] += 1
        standings[away]["Games"] += 1
        standings[home]["PF"] += hs
        standings[home]["PA"] += rs
        standings[away]["PF"] += rs
        standings[away]["PA"] += hs

        if row["HomeWin"] == 1:
            standings[home]["W"] += 1
            standings[away]["L"] += 1
        else:
            standings[away]["W"] += 1
            standings[home]["L"] += 1

    return standings


def head_to_head_bylaws(df, tied_teams):
    subset = df[df["Local"].isin(tied_teams) & df["Visitor"].isin(tied_teams)]
    match_counts = subset.groupby(["Local", "Visitor"]).size().reset_index(name="count")
    pair_counts = {}

    for _, row in match_counts.iterrows():
        pair = tuple(sorted([row["Local"], row["Visitor"]]))
        pair_counts[pair] = pair_counts.get(pair, 0) + row["count"]

    if not all(count >= 2 for count in pair_counts.values()):
        return None

    h2h_stats = {team: {"W": 0, "PF": 0, "PA": 0} for team in tied_teams}

    for _, row in subset.iterrows():
        if np.isnan(row["HomeWin"]):
            continue
        home, away = row["Local"], row["Visitor"]
        hs, rs = row["HomeScore"], row["RoadScore"]

        h2h_stats[home]["PF"] += hs
        h2h_stats[home]["PA"] += rs
        h2h_stats[away]["PF"] += rs
        h2h_stats[away]["PA"] += hs

        if row["HomeWin"] == 1:
            h2h_stats[home]["W"] += 1
        else:
            h2h_stats[away]["W"] += 1

    df_h2h = pd.DataFrame.from_dict(h2h_stats, orient="index")
    df_h2h["Diff"] = df_h2h["PF"] - df_h2h["PA"]
    return df_h2h.sort_values(by=["W", "Diff", "PF"], ascending=False)


def resolve_tiebreakers_with_bylaws(df, sanctioned_teams=None):
    standings = compute_standings_with_bylaws(df, sanctioned_teams)
    df_stand = pd.DataFrame.from_dict(standings, orient="index")
    df_stand["Diff"] = df_stand["PF"] - df_stand["PA"]
    df_stand["Total"] = df_stand["W"] + df_stand["L"]
    df_stand = df_stand.reset_index().rename(columns={"index": "Team"})

    # Map acronyms to full club names
    name_map = {}
    for _, row in df.iterrows():
        name_map[row["Local"]] = row["Local_Name"]
        name_map[row["Visitor"]] = row["Visitor_Name"]
    df_stand["ClubName"] = df_stand["Team"].map(name_map)

    df_stand = df_stand.sort_values(by=["W", "L", "Diff", "PF", "ClubName"],
                                    ascending=[False, True, False, False, True])
    return df_stand.reset_index(drop=True)


def generate_txt_string(df_standings, label="A"):
    """Versión modificada que devuelve string, no archivo"""
    df = df_standings.copy()
    if "Rank" not in df.columns:
        df["Rank"] = df.reset_index().index + 1
    if "GP" not in df.columns:
        df["GP"] = df["W"] + df["L"]

    lines = []
    for _, row in df.iterrows():
        pf = int(round(row["PF"]))
        pa = int(round(row["PA"]))
        diff = pf - pa
        lines.append(f'C;{label};{row["Rank"]};{row["Team"]};{row["GP"]};{row["W"]};{row["L"]};{pf};{pa};{diff};{row["Team"]}')
    return "\n".join(lines)


# =====================================================
# ---------------- STREAMLIT INTERFACE ----------------
# =====================================================

st.set_page_config(page_title="Euroleague & Eurocup Standings", layout="wide")
st.title("🏀 Euroleague & Eurocup Standings Generator")

tab1, tab2 = st.tabs(["EuroLeague", "EuroCup"])

# ----------- TAB EUROLEAGUE -----------
with tab1:
    st.header("EuroLeague Standings")
    if st.button("Generate EuroLeague Standings"):
        df, sanctioned = actual_calendar_EL()
        standings = resolve_tiebreakers_with_bylaws(df, sanctioned)
        txt_output = generate_txt_string(standings, label="EL")

        st.success("✅ Standings generated successfully!")
        st.text_area("EuroLeague Standings (.txt format):", txt_output, height=500)


# ----------- TAB EUROCUP -----------
from standingsEC import eurocup_calendar_2025, resolve_tiebreakers_with_bylaws as resolve_ec, generate_txt_standings_output

with tab2:
    st.header("EuroCup Standings")
    if st.button("Generate EuroCup Standings"):
        df_a, df_b = eurocup_calendar_2025()

        standings_a = resolve_ec(df_a)
        standings_b = resolve_ec(df_b)

        txt_a = generate_txt_string(standings_a, label="A")
        txt_b = generate_txt_string(standings_b, label="B")

        st.success("✅ EuroCup standings generated!")
        subtab1, subtab2 = st.tabs(["Group A", "Group B"])
        with subtab1:
            st.text_area("EuroCup Group A (.txt format):", txt_a, height=500)
        with subtab2:
            st.text_area("EuroCup Group B (.txt format):", txt_b, height=500)
