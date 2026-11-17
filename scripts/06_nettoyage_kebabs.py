"""
06 - Nettoyage et fusion des kebabs OSM + SIRENE -> une base unique.

Étapes (chaque règle est documentée dans le rapport, section 3.3) :

1. VALIDATION : chaque établissement reçoit une fiabilité
     "certain"  : c'est clairement un kebab
     "probable" : vend sans doute des kebabs, mais pas seulement / nom ambigu
     "exclu"    : faux positif (gardé dans un fichier à part, avec la raison)
   - OSM    : certain si le tag cuisine vaut uniquement "kebab" ou si le nom contient
              un mot-clé kebab ; probable si kebab est une cuisine parmi d'autres
              (snack généraliste) ; exclu si ce n'est pas un restaurant/fast-food/café.
   - SIRENE : certain si un mot-clé principal (kebab, döner...) est dans le nom ;
              probable si seul un mot-clé secondaire (istanbul, shawarma...) y est ;
              exclu si aucun mot-clé n'est réellement dans le nom (recherche "floue"
              de l'API) ou exclusion manuelle justifiée (EXCLUSIONS_MANUELLES).

2. DOUBLONS INTERNES : deux établissements d'une même source à moins de 30 m
   et dont les noms se ressemblent = un seul lieu (cas typique dans SIRENE :
   un même local repris par plusieurs exploitants restés "actifs").

3. APPARIEMENT OSM <-> SIRENE : même établissement si
     a. même SIRET (tag OSM ref:FR:SIRET), ou
     b. distance < 100 m ET noms qui se ressemblent, ou
     c. distance < 10 m (même adresse : local repris sous un autre nom).
   Au-delà de 10 m, la distance seule ne suffit pas : des kebabs distincts
   sont parfois voisins (ex. deux boutiques côte à côte cours Belsunce).

4. FUSION : une ligne par kebab. Coordonnées OSM en priorité (point posé sur
   le bâtiment), sinon SIRENE (adresse géocodée). La fiabilité retenue est la
   meilleure des deux sources.

Sorties :
    donnees/traitees/kebabs.csv         base finale (certain + probable)
    donnees/traitees/kebabs_exclus.csv  faux positifs écartés, avec la raison
"""
import re
import unicodedata
from difflib import SequenceMatcher

import geopandas as gpd
import numpy as np
import pandas as pd

from config import CRS_GPS, CRS_METRIQUE, DONNEES_BRUTES, DONNEES_TRAITEES
from utils import rattacher_zone

# --- Paramètres des règles ----------------------------------------------------
DIST_DOUBLON = 30          # m : doublons à l'intérieur d'une même source
DIST_APPARIEMENT = 100     # m : appariement OSM <-> SIRENE si noms proches
DIST_MEME_LIEU = 10        # m : appariement OSM <-> SIRENE même si noms différents
SEUIL_NOM = 0.7            # similarité de noms (0 à 1) jugée suffisante

MOTIF_KEBAB = r"kebab|kebap|kabab|doner|durum|berliner"
# Mots trop génériques pour prouver que deux noms désignent le même lieu
MOTS_GENERIQUES = {
    "kebab", "kebap", "kabab", "doner", "durum", "snack", "restaurant", "resto", "grill",
    "food", "fast", "chez", "sarl", "sas", "sasu", "eurl", "the", "les", "des", "aux",
    "city", "house", "best", "delice", "delices", "marseille", "original", "das",
}
# Faux positifs repérés à la lecture des noms (SIRET -> raison)
EXCLUSIONS_MANUELLES = {
    "85102177400019": "pâtisserie (Istanbul Baklava), pas un kebab",
}


# --- Outils sur les noms --------------------------------------------------------
def normaliser(texte) -> str:
    """minuscules, sans accents ni ponctuation : "L'Ô Döner" -> "l o doner"."""
    if not isinstance(texte, str):
        return ""
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", texte.lower()).strip()


def variantes_sirene(ligne) -> list[str]:
    """Les différents noms d'un établissement SIRENE : raison sociale, nom entre
    parenthèses (souvent le nom commercial) et enseigne."""
    noms = [ligne["nom_entreprise"], ligne["enseigne"]]
    noms += re.findall(r"\(([^)]*)\)", str(ligne["nom_entreprise"]))
    noms.append(re.sub(r"\([^)]*\)", "", str(ligne["nom_entreprise"])))
    return [n for n in {normaliser(x) for x in noms} if n]


def mots_distinctifs(noms: list[str]) -> set[str]:
    return {m for n in noms for m in n.split() if len(m) >= 3 and m not in MOTS_GENERIQUES}


def noms_proches(noms_a: list[str], noms_b: list[str]) -> bool:
    """Vrai si un mot distinctif est commun, ou si deux variantes sont très proches."""
    if mots_distinctifs(noms_a) & mots_distinctifs(noms_b):
        return True
    return any(SequenceMatcher(None, a, b).ratio() >= SEUIL_NOM for a in noms_a for b in noms_b)


# --- 1. Validation ---------------------------------------------------------------
def valider_osm(df: pd.DataFrame) -> pd.DataFrame:
    cuisine = df["cuisine"].fillna("").str.lower()
    nom_kebab = df["noms"].apply(lambda ns: any(re.search(MOTIF_KEBAB, n) for n in ns))
    df["fiabilite"] = np.where((cuisine == "kebab") | nom_kebab, "certain", "probable")
    df["raison_exclusion"] = None
    pas_resto = ~df["amenity"].isin(["fast_food", "restaurant", "cafe"])
    df.loc[pas_resto, "raison_exclusion"] = "pas un restaurant (tag amenity absent ou autre)"
    df.loc[pas_resto, "fiabilite"] = "exclu"
    return df


def valider_sirene(df: pd.DataFrame) -> pd.DataFrame:
    nom_kebab = df["noms"].apply(lambda ns: any(re.search(MOTIF_KEBAB, n) for n in ns))
    df["fiabilite"] = np.where(nom_kebab, "certain", "probable")
    df["raison_exclusion"] = None
    # mot_cle_dans_nom (script 03) : un mot-clé est-il vraiment dans le nom ?
    absent = ~df["mot_cle_dans_nom"]
    df.loc[absent, "raison_exclusion"] = "aucun mot-clé dans le nom (résultat flou de l'API)"
    manuel = df["siret"].isin(EXCLUSIONS_MANUELLES)
    df.loc[manuel, "raison_exclusion"] = df.loc[manuel, "siret"].map(EXCLUSIONS_MANUELLES)
    df.loc[absent | manuel, "fiabilite"] = "exclu"
    return df


# --- 2. Doublons internes -------------------------------------------------------------
def regrouper_doublons(gdf: gpd.GeoDataFrame) -> np.ndarray:
    """Numéro de groupe : les doublons (proches ET noms proches) ont le même numéro."""
    groupe = np.arange(len(gdf))

    def racine(i):
        while groupe[i] != i:
            i = groupe[i]
        return i

    paires = gpd.sjoin(gdf, gdf, predicate="dwithin", distance=DIST_DOUBLON)
    for i, j in zip(paires.index, paires["index_right"]):
        if i < j and noms_proches(gdf.at[i, "noms"], gdf.at[j, "noms"]):
            groupe[racine(j)] = racine(i)
    return np.array([racine(i) for i in range(len(gdf))])


def dedoublonner(gdf: gpd.GeoDataFrame, colonne_id: str, tri: list[str],
                 croissant: list[bool]) -> gpd.GeoDataFrame:
    """Garde un établissement par groupe (le premier selon `tri`) et liste les autres."""
    gdf = gdf.reset_index(drop=True)
    gdf["groupe"] = regrouper_doublons(gdf)
    autres = gdf.groupby("groupe")[colonne_id].agg(lambda s: ",".join(s.astype(str)))
    gdf = gdf.sort_values(tri, ascending=croissant).drop_duplicates("groupe")
    gdf[f"{colonne_id}_regroupes"] = gdf["groupe"].map(autres)
    gdf["nb_doublons"] = gdf[f"{colonne_id}_regroupes"].str.count(",")
    return gdf.drop(columns="groupe").reset_index(drop=True)


# --- 3. Appariement OSM <-> SIRENE -------------------------------------------------------
def apparier(osm: gpd.GeoDataFrame, sir: gpd.GeoDataFrame) -> pd.DataFrame:
    """Paires (index OSM, index SIRENE, règle). Chaque établissement apparaît au plus une fois."""
    candidats = []
    siret_osm = osm["ref:FR:SIRET"].fillna("")
    for i in osm.index:
        for j in sir.index:
            d = osm.geometry[i].distance(sir.geometry[j])
            if siret_osm[i] and siret_osm[i] in sir.at[j, "siret_regroupes"].split(","):
                candidats.append((0, d, i, j, "siret"))
            elif d < DIST_APPARIEMENT and noms_proches(osm.at[i, "noms"], sir.at[j, "noms"]):
                candidats.append((1, d, i, j, "distance+nom"))
            elif d < DIST_MEME_LIEU:
                candidats.append((2, d, i, j, "meme_lieu"))
    # Appariement glouton : SIRET d'abord, puis du plus proche au plus lointain
    pris_o, pris_s, paires = set(), set(), []
    for _, d, i, j, regle in sorted(candidats):
        if i not in pris_o and j not in pris_s:
            pris_o.add(i), pris_s.add(j)
            paires.append({"i_osm": i, "i_sirene": j, "regle_appariement": regle,
                           "distance_osm_sirene_m": round(d)})
    return pd.DataFrame(paires, columns=["i_osm", "i_sirene", "regle_appariement",
                                         "distance_osm_sirene_m"])


# --- 4. Fusion ----------------------------------------------------------------------
def main():
    print("[06] Nettoyage et fusion des kebabs")
    osm = pd.read_csv(DONNEES_BRUTES / "kebabs_osm.csv", dtype={"ref:FR:SIRET": str})
    sir = pd.read_csv(DONNEES_BRUTES / "kebabs_sirene.csv", dtype={"siret": str, "code_zone": str})
    osm["ref:FR:SIRET"] = osm["ref:FR:SIRET"].str.replace(r"\D", "", regex=True)
    osm["noms"] = osm["name"].apply(lambda n: [normaliser(n)] if normaliser(n) else [])
    sir["noms"] = sir.apply(variantes_sirene, axis=1)

    # 1. Validation
    osm, sir = valider_osm(osm), valider_sirene(sir)
    exclus = pd.concat([
        osm[osm["fiabilite"] == "exclu"].assign(source="osm", nom=osm["name"]),
        sir[sir["fiabilite"] == "exclu"].assign(source="sirene", nom=sir["nom_entreprise"]),
    ]).reindex(columns=["source", "osm_id", "siret", "nom", "commune", "raison_exclusion"])
    osm = osm[osm["fiabilite"] != "exclu"]
    sir = sir[sir["fiabilite"] != "exclu"]
    print(f"  validation : OSM {len(osm)} gardés, SIRENE {len(sir)} gardés, {len(exclus)} exclus")

    # 2. Doublons internes (en mètres -> projection Lambert 93)
    def en_metres(df):
        return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]),
                                crs=CRS_GPS).to_crs(CRS_METRIQUE)
    rang = {"certain": 0, "probable": 1}
    osm = en_metres(osm).assign(r=lambda d: d["fiabilite"].map(rang))
    sir = en_metres(sir).assign(r=lambda d: d["fiabilite"].map(rang))
    osm = dedoublonner(osm, "osm_id", ["r"], [True])
    # SIRENE : on garde le plus fiable, puis le plus récemment créé (exploitant actuel)
    sir = dedoublonner(sir, "siret", ["r", "date_creation"], [True, False])
    print(f"  après dédoublonnage : OSM {len(osm)}, SIRENE {len(sir)} "
          f"({sir['nb_doublons'].sum()} doublons SIRENE regroupés)")

    # 3. Appariement
    paires = apparier(osm, sir)
    print(f"  appariés OSM <-> SIRENE : {len(paires)} "
          f"({(paires['regle_appariement'] == 'siret').sum()} par SIRET)")

    # 4. Fusion : une ligne par kebab
    o = osm.drop(columns=["geometry", "r", "noms"]).add_suffix("_osm")
    s = sir.drop(columns=["geometry", "r", "noms"]).add_suffix("_sir")
    fus = (paires.merge(o, left_on="i_osm", right_index=True)
                 .merge(s, left_on="i_sirene", right_index=True))
    seuls_osm = o.drop(index=paires["i_osm"])
    seuls_sir = s.drop(index=paires["i_sirene"])
    base = pd.concat([fus.assign(source="osm+sirene"),
                      seuls_osm.assign(source="osm"),
                      seuls_sir.assign(source="sirene")], ignore_index=True)

    def priorite(col_osm, col_sir):
        a = base[col_osm] if col_osm in base else pd.Series(np.nan, index=base.index)
        return a.where(a.notna(), base[col_sir] if col_sir in base else np.nan)

    base["lat"] = priorite("lat_osm", "lat_sir")
    base["lon"] = priorite("lon_osm", "lon_sir")
    base["nom"] = priorite("name_osm", "nom_entreprise_sir").fillna("(sans nom)")
    base["siret"] = priorite("siret_sir", "ref:FR:SIRET_osm")
    base["fiabilite"] = np.where((base["fiabilite_osm"] == "certain")
                                 | (base["fiabilite_sir"] == "certain"), "certain", "probable")
    base = base.rename(columns={"osm_id_osm": "osm_id", "adresse_sir": "adresse", "naf_sir": "naf",
                                "date_creation_sir": "date_creation",
                                "siret_regroupes_sir": "sirets_regroupes"})

    # Zone (commune / arrondissement) recalculée avec les coordonnées retenues
    base = pd.DataFrame(rattacher_zone(base).drop(columns="geometry"))
    base = base.sort_values(["commune", "arrondissement", "nom"]).reset_index(drop=True)
    base.insert(0, "id_kebab", [f"K{i:03d}" for i in range(1, len(base) + 1)])
    colonnes = ["id_kebab", "nom", "fiabilite", "source", "lat", "lon", "code_zone", "commune",
                "arrondissement", "siret", "osm_id", "adresse", "naf", "date_creation",
                "cuisine_osm", "regle_appariement", "distance_osm_sirene_m", "sirets_regroupes"]
    base = base[colonnes]

    base.to_csv(DONNEES_TRAITEES / "kebabs.csv", index=False, encoding="utf-8")
    exclus.to_csv(DONNEES_TRAITEES / "kebabs_exclus.csv", index=False, encoding="utf-8")

    # --- Bilan ---
    print(f"  -> kebabs.csv : {len(base)} kebabs "
          f"(dont {(base['commune'] == 'Marseille').sum()} à Marseille)")
    print(pd.crosstab(base["source"], base["fiabilite"], margins=True, margins_name="total").to_string())
    # Capture-recapture (Lincoln-Petersen) : estimation du nombre réel de kebabs
    n_osm = (base["source"] != "sirene").sum()
    n_sir = (base["source"] != "osm").sum()
    n_commun = (base["source"] == "osm+sirene").sum()
    if n_commun:
        print(f"  capture-recapture : N ≈ {n_osm} x {n_sir} / {n_commun} = {n_osm * n_sir / n_commun:.0f}")
    print(f"  -> kebabs_exclus.csv : {len(exclus)} établissements écartés")


if __name__ == "__main__":
    main()
