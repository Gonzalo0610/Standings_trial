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
# ---------------- STREAMLIT INTERFACE ----------------
# =====================================================

st.set_page_config(page_title="Euroleague Standings Generator", layout="wide")
st.title("🏀 Euroleague Standings Generator (Editable)")

st.header("EuroLeague Standings")

# Obtener datos iniciales
df, sanctioned = actual_calendar_EL()

# Opción de mostrar solo partidos sin resultado
show_all = st.checkbox("Mostrar todos los partidos (no solo los incompletos)", value=False)

if not show_all:
    df_edit = df[df["HomeWin"].isna()].copy()
else:
    df_edit = df.copy()

st.markdown("### Introduce o modifica los resultados manualmente")
st.markdown("_Rellena HomeScore, RoadScore y selecciona el ganador (Local o Visitor)_")

# Añadir columna de ganador
df_edit["Winner"] = np.where(df_edit["HomeWin"] == 1, "Local",
                      np.where(df_edit["RoadWin"] == 1, "Visitor", ""))

editable = st.data_editor(
    df_edit[["Round", "Local", "Visitor", "HomeScore", "RoadScore", "Winner"]],
    num_rows="dynamic",
    use_container_width=True,
    key="editor"
)

# Actualizar DataFrame con valores editados
for idx, row in editable.iterrows():
    mask = (df["Local"] == row["Local"]) & (df["Visitor"] == row["Visitor"]) & (df["Round"] == row["Round"])
    if not row["Winner"]:
        continue
    df.loc[mask, "HomeScore"] = row["HomeScore"]
    df.loc[mask, "RoadScore"] = row["RoadScore"]
    if row["Winner"] == "Local":
        df.loc[mask, "HomeWin"] = 1
        df.loc[mask, "RoadWin"] = 0
    elif row["Winner"] == "Visitor":
        df.loc[mask, "HomeWin"] = 0
        df.loc[mask, "RoadWin"] = 1
    df.loc[mask, "PlusMinus"] = row["HomeScore"] - row["RoadScore"]

# Botón para generar standings
if st.button("Generate EuroLeague Standings"):
    standings = resolve_tiebreakers_with_bylaws(df, sanctioned)
    txt_output = generate_txt_string(standings, label="EL")

    st.success("✅ Standings generated successfully!")
    st.text_area("EuroLeague Standings (.txt format):", txt_output, height=500)


