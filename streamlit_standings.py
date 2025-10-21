import streamlit as st
import pandas as pd
import numpy as np
import requests

# =====================================================
# ---------------- COMMON FUNCTIONS -------------------
# =====================================================

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


def resolve_tiebreakers_with_bylaws(df, sanctioned_teams=None):
    standings = compute_standings_with_bylaws(df, sanctioned_teams)
    df_stand = pd.DataFrame.from_dict(standings, orient="index")
    df_stand["Diff"] = df_stand["PF"] - df_stand["PA"]
    df_stand["Total"] = df_stand["W"] + df_stand["L"]
    df_stand = df_stand.reset_index().rename(columns={"index": "Team"})

    name_map = {}
    for _, row in df.iterrows():
        name_map[row["Local"]] = row["Local_Name"]
        name_map[row["Visitor"]] = row["Visitor_Name"]
    df_stand["ClubName"] = df_stand["Team"].map(name_map)

    df_stand = df_stand.sort_values(by=["W", "L", "Diff", "PF", "ClubName"],
                                    ascending=[False, True, False, False, True])
    return df_stand.reset_index(drop=True)


def generate_txt_string(df_standings, label="A"):
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
# ---------------- EUROLEAGUE FUNCTIONS ---------------
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


# =====================================================
# ---------------- EUROCUP FUNCTIONS ------------------
# =====================================================

def eurocup_calendar_2025():
    url = "https://api-live.euroleague.net/v2/competitions/U/seasons/U2025/games"
    response = requests.get(url).json()["data"]

    local, visiting, plusminus, lscore, vscore, lw, vw, round_, group, local_name, visitor_name = ([] for _ in range(11))

    for i in response:
        local.append(i["local"]["club"]["code"])
        visiting.append(i["road"]["club"]["code"])
        round_.append(i["round"])
        group.append(i["group"]["rawName"])
        local_name.append(i["local"]["club"]["name"])
        visitor_name.append(i["road"]["club"]["name"])

        if i["local"]["score"] > i["road"]["score"]:
            plusminus.append(i["local"]["standingsScore"] - i["road"]["standingsScore"])
            lscore.append(i["local"]["standingsScore"])
            vscore.append(i["road"]["standingsScore"])
            lw.append(1)
            vw.append(0)
        elif i["local"]["score"] < i["road"]["score"]:
            plusminus.append(i["local"]["standingsScore"] - i["road"]["standingsScore"])
            lscore.append(i["local"]["standingsScore"])
            vscore.append(i["road"]["standingsScore"])
            lw.append(0)
            vw.append(1)
        else:
            plusminus.append(np.nan)
            lscore.append(np.nan)
            vscore.append(np.nan)
            lw.append(np.nan)
            vw.append(np.nan)

    df = pd.DataFrame({
        "Local": local, "Visitor": visiting, "HomeWin": lw, "RoadWin": vw,
        "HomeScore": lscore, "RoadScore": vscore, "PlusMinus": plusminus,
        "Round": round_, "Group": group,
        "Local_Name": local_name, "Visitor_Name": visitor_name
    })

    return df[df["Group"] == "A"].reset_index(drop=True), df[df["Group"] == "B"].reset_index(drop=True)


# =====================================================
# ---------------- STREAMLIT APP ----------------------
# =====================================================

st.set_page_config(page_title="Euroleague & Eurocup Standings", layout="wide")
st.title("🏀 Euroleague & Eurocup Standings Generator (Editable)")

tab1, tab2 = st.tabs(["EuroLeague", "EuroCup"])

# -----------------------------------------------------
# TAB 1: EUROLEAGUE
# -----------------------------------------------------
with tab1:
    st.header("EuroLeague Standings")

    df, sanctioned = actual_calendar_EL()
    show_all = st.checkbox("Mostrar todos los partidos (no solo los incompletos)", value=False, key="el_show_all")

    df_edit = df if show_all else df[df["HomeWin"].isna()].copy()
    df_edit = df_edit.sort_values(by="Round", ascending=True).reset_index(drop=True)
    df_edit["Winner"] = np.where(df_edit["HomeWin"] == 1, "Local",
                          np.where(df_edit["RoadWin"] == 1, "Visitor", ""))

    st.markdown("### Introduce o modifica los resultados manualmente")

    editable = st.data_editor(
        df_edit[["Round", "Local", "Visitor", "HomeScore", "RoadScore", "Winner"]],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Winner": st.column_config.SelectboxColumn("Winner", options=["Local", "Visitor"], required=False)
        },
        key="editor_el"
    )

    for _, row in editable.iterrows():
        mask = (df["Local"] == row["Local"]) & (df["Visitor"] == row["Visitor"]) & (df["Round"] == row["Round"])
        if pd.isna(row["HomeScore"]) or pd.isna(row["RoadScore"]) or not row["Winner"]:
            continue
        df.loc[mask, "HomeScore"] = row["HomeScore"]
        df.loc[mask, "RoadScore"] = row["RoadScore"]
        if row["Winner"] == "Local":
            df.loc[mask, "HomeWin"], df.loc[mask, "RoadWin"] = 1, 0
        elif row["Winner"] == "Visitor":
            df.loc[mask, "HomeWin"], df.loc[mask, "RoadWin"] = 0, 1
        df.loc[mask, "PlusMinus"] = row["HomeScore"] - row["RoadScore"]

    if st.button("Generate EuroLeague Standings"):
        standings = resolve_tiebreakers_with_bylaws(df, sanctioned)
        txt_output = generate_txt_string(standings, label="EL")
        st.success("✅ Standings generated successfully!")
        st.text_area("EuroLeague Standings (.txt format):", txt_output, height=500)

# -----------------------------------------------------
# TAB 2: EUROCUP
# -----------------------------------------------------
with tab2:
    st.header("EuroCup Standings")

    df_a, df_b = eurocup_calendar_2025()

    subtab1, subtab2 = st.tabs(["Group A", "Group B"])

    for group_label, df_group, key_prefix in [("A", df_a, "a"), ("B", df_b, "b")]:
        with (subtab1 if group_label == "A" else subtab2):
            show_all = st.checkbox(f"Mostrar todos los partidos del Grupo {group_label}", value=False, key=f"show_all_{key_prefix}")

            df_edit = df_group if show_all else df_group[df_group["HomeWin"].isna()].copy()
            df_edit = df_edit.sort_values(by="Round", ascending=True).reset_index(drop=True)
            df_edit["Winner"] = np.where(df_edit["HomeWin"] == 1, "Local",
                                  np.where(df_edit["RoadWin"] == 1, "Visitor", ""))

            editable = st.data_editor(
                df_edit[["Round", "Local", "Visitor", "HomeScore", "RoadScore", "Winner"]],
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Winner": st.column_config.SelectboxColumn("Winner", options=["Local", "Visitor"], required=False)
                },
                key=f"editor_{key_prefix}"
            )

            for _, row in editable.iterrows():
                mask = (df_group["Local"] == row["Local"]) & (df_group["Visitor"] == row["Visitor"]) & (df_group["Round"] == row["Round"])
                if pd.isna(row["HomeScore"]) or pd.isna(row["RoadScore"]) or not row["Winner"]:
                    continue
                df_group.loc[mask, "HomeScore"] = row["HomeScore"]
                df_group.loc[mask, "RoadScore"] = row["RoadScore"]
                if row["Winner"] == "Local":
                    df_group.loc[mask, "HomeWin"], df_group.loc[mask, "RoadWin"] = 1, 0
                elif row["Winner"] == "Visitor":
                    df_group.loc[mask, "HomeWin"], df_group.loc[mask, "RoadWin"] = 0, 1
                df_group.loc[mask, "PlusMinus"] = row["HomeScore"] - row["RoadScore"]

            if st.button(f"Generate Group {group_label} Standings"):
                standings = resolve_tiebreakers_with_bylaws(df_group)
                txt_output = generate_txt_string(standings, label=group_label)
                st.success(f"✅ EuroCup Group {group_label} standings generated!")
                st.text_area(f"EuroCup Group {group_label} (.txt format):", txt_output, height=500)






