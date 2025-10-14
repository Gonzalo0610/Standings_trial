
import pandas as pd
import numpy as np
import requests
import os
from pathlib import Path


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
        if not pd.isna(row["Local"]):
            name_map[row["Local"]] = row["Local_Name"]
        if not pd.isna(row["Visitor"]):
            name_map[row["Visitor"]] = row["Visitor_Name"]
    df_stand["ClubName"] = df_stand["Team"].map(name_map)

    df_stand = df_stand.sort_values(by=["W", "L", "Diff", "PF", "ClubName"], ascending=[False, True, False, False, True])

    i = 0
    resolved = []
    while i < len(df_stand):
        tied = [df_stand.iloc[i]["Team"]]
        j = i + 1
        while j < len(df_stand) and df_stand.iloc[j]["W"] == df_stand.iloc[i]["W"]:
            tied.append(df_stand.iloc[j]["Team"])
            j += 1

        if len(tied) > 1:
            group = df_stand[df_stand["Team"].isin(tied)].copy()
            group["Sanctioned"] = group["Team"].isin(sanctioned_teams) if sanctioned_teams else False
            group["Games"] = group["Total"]
            group = group.sort_values(by=["Sanctioned", "Games", "Diff", "PF", "ClubName"], ascending=[True, False, False, False, True])

            h2h = head_to_head_bylaws(df, tied)
            resolved += list(h2h.index) if h2h is not None else list(group["Team"])
        else:
            resolved.append(tied[0])
        i = j
        
    final_df = df_stand.set_index("Team").loc[resolved].reset_index()
    final_df = final_df.sort_values(
    by=["W", "L", "Diff", "PF", "ClubName"],
    ascending=[False, True, False, False, True],
    key=lambda col: col.str.lower() if col.name == "ClubName" else col
).reset_index(drop=True)

    return final_df


def generate_txt_standings_output(df_standings, filename="euroleague_standings_export.txt", label="A"):
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
        line = f'C;{label};{row["Rank"]};{row["Team"]};{row["GP"]};{row["W"]};{row["L"]};{pf};{pa};{diff};{row["Team"]}'
        lines.append(line)

    path = Path(os.getcwd()) / filename
    with path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return path


def run_eurocup_group_standings():
    df_a, df_b = eurocup_calendar_2025()

    standings_a = resolve_tiebreakers_with_bylaws(df_a)
    path_a = generate_txt_standings_output(standings_a, filename="Group_A_Standings_EC.txt", label="A")
    print(f"Grupo A guardado en: {path_a}")

    standings_b = resolve_tiebreakers_with_bylaws(df_b)
    path_b = generate_txt_standings_output(standings_b, filename="Group_B_Standings_EC.txt", label="B")
    print(f"Grupo B guardado en: {path_b}")

    
run_eurocup_group_standings()