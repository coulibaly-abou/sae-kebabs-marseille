"""
Scène 3D interactive des résultats (tableau de bord du projet).

Prépare toutes les données de la scène (carreaux, kebabs, stations, isochrones,
prédictions du modèle, simulation de Monte-Carlo) puis les injecte dans le modèle
HTML `dashboard/modele_scene.html` pour produire un fichier autonome :
`dashboard/kebabs_3d.html` (s'ouvre dans n'importe quel navigateur).

La simulation répond à la question de H1 de façon visuelle : « et si les 144 kebabs
s'étaient installés comme la population ? ». On tire 1 000 fois 144 positions au
hasard, chaque carreau ayant une chance proportionnelle à son nombre d'habitants,
et on compare ces placements fictifs aux vrais kebabs.
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.neighbors import BallTree

from config import CRS_GPS, CRS_METRIQUE, DONNEES_BRUTES, DONNEES_TRAITEES, RACINE

VARIABLES = ["log_densite", "niveau_vie_moyen", "part_logement_social", "part_25_39",
             "part_65_plus", "log_dist_station", "marseille"]
GRAINE = 2026
N_SIMULATIONS = 1000
R_TERRE = 6_371_000
DOSSIER = RACINE / "dashboard"


def r(x, n):
    return None if pd.isna(x) else round(float(x), n)


# --- Carreaux : population, niveau de vie, kebabs, probabilité du modèle -------------
c = gpd.read_file(DONNEES_TRAITEES / "carreaux_indicateurs.gpkg")
c = c[c["habite"] & (c["ind"] > 0)].copy()
centres = c.geometry.centroid.to_crs(CRS_GPS)
c["lon"], c["lat"] = centres.x, centres.y

d = pd.DataFrame(c.drop(columns="geometry"))
d["log_densite"] = np.log(d["densite_hab_km2"])
d["log_dist_station"] = np.log(d["dist_gare_m"] + 50)
d["part_25_39"] = d["ind_25_39"] / d["ind"]
d["marseille"] = (d["commune"] == "Marseille").astype(int)
apprentissage = d[(d["i_est_200"] == 0)].dropna(subset=VARIABLES)
X = apprentissage[VARIABLES]
moy, et = X.mean(), X.std()
modele = sm.Logit(apprentissage["presence_kebab"], sm.add_constant((X - moy) / et)).fit(disp=False)
d["proba"] = np.nan
d.loc[apprentissage.index, "proba"] = modele.predict(sm.add_constant((X - moy) / et))
print(f"modèle : {len(apprentissage)} carreaux, {int(apprentissage['presence_kebab'].sum())} avec kebab")

carreaux = [[r(l.lon, 5), r(l.lat, 5), int(l.ind), r(l.niveau_vie_moyen, -2), int(l.nb_kebabs),
             r(l.proba, 4), r(l.dist_gare_m, -1)] for l in d.itertuples()]

# Les « emplacements favorables » : forte probabilité prédite, mais aucun kebab connu.
zones_noms = gpd.read_file(DONNEES_BRUTES / "zones.geojson")[["code_zone", "nom_zone"]]
d = d.merge(zones_noms, on="code_zone", how="left").set_index(d.index)
favorables = (d[(d["nb_kebabs"] == 0) & d["proba"].notna()]
              .sort_values("proba", ascending=False).head(12))
opportunites = [{"lon": r(l.lon, 5), "lat": r(l.lat, 5), "proba": r(l.proba, 3),
                 "zone": l.nom_zone.replace(" Arrondissement", ""), "pop": int(l.ind),
                 "nv": r(l.niveau_vie_moyen, -2), "station_m": r(l.dist_gare_m, -1)}
                for l in favorables.itertuples()]

# --- Kebabs et stations ------------------------------------------------------------
k = pd.read_csv(DONNEES_TRAITEES / "kebabs.csv")
g = pd.read_csv(DONNEES_BRUTES / "gares.csv")
arbre = BallTree(np.radians(g[["lat", "lon"]].values), metric="haversine")
dist, idx = arbre.query(np.radians(k[["lat", "lon"]].values), k=1)
k["station"] = g["name"].values[idx[:, 0]]
k["station_type"] = g["type"].values[idx[:, 0]]
k["station_lon"], k["station_lat"] = g["lon"].values[idx[:, 0]], g["lat"].values[idx[:, 0]]
k["station_m"] = dist[:, 0] * R_TERRE

# --- Simulation de Monte-Carlo : des kebabs placés « comme la population » ------------
rng = np.random.default_rng(GRAINE)
poids = d["ind"].values / d["ind"].sum()
lat0 = np.radians(43.3)


def tirage(n):
    i = rng.choice(len(d), size=n, p=poids)
    # position au hasard dans le carreau de 200 m
    lat = d["lat"].values[i] + rng.uniform(-100, 100, n) / 111_320
    lon = d["lon"].values[i] + rng.uniform(-100, 100, n) / (111_320 * np.cos(lat0))
    return lon, lat


def indicateurs(lon, lat):
    dist_st = arbre.query(np.radians(np.c_[lat, lon]), k=1)[0][:, 0] * R_TERRE
    pts = np.radians(np.c_[lat, lon])
    voisins = BallTree(pts, metric="haversine").query(pts, k=2)[0][:, 1] * R_TERRE
    return {"station_mediane_m": float(np.median(dist_st)),
            "part_500m_station": float(np.mean(dist_st < 500)),
            "voisin_moyen_m": float(np.mean(voisins))}


reel = indicateurs(k["lon"].values, k["lat"].values)
sims = pd.DataFrame([indicateurs(*tirage(len(k))) for _ in range(N_SIMULATIONS)])
sim_lon, sim_lat = tirage(len(k))                      # un placement fictif pour l'animation
simulation = {
    "n": N_SIMULATIONS, "reel": reel,
    "sim_mediane": sims.median().to_dict(),
    "sim_min_max": {c_: [float(sims[c_].min()), float(sims[c_].max())] for c_ in sims},
    "nb_sims_aussi_proches_station": int((sims["station_mediane_m"] <= reel["station_mediane_m"]).sum()),
    "nb_sims_aussi_groupes": int((sims["voisin_moyen_m"] <= reel["voisin_moyen_m"]).sum()),
    "histo_station": np.histogram(sims["station_mediane_m"], bins=30)[0].tolist(),
    "histo_bords": np.histogram(sims["station_mediane_m"], bins=30)[1].round(0).tolist(),
}
print("simulation :", {x: simulation[x] for x in ("reel", "sim_mediane", "nb_sims_aussi_proches_station",
                                                    "nb_sims_aussi_groupes")})

kebabs = [{"lon": r(l.lon, 6), "lat": r(l.lat, 6), "nom": l.nom.title() if l.nom.isupper() else l.nom,
           "fiab": l.fiabilite, "src": l.source, "commune": l.commune,
           "arr": None if pd.isna(l.arrondissement) else int(l.arrondissement),
           "st": l.station, "st_type": l.station_type, "st_lon": r(l.station_lon, 6),
           "st_lat": r(l.station_lat, 6), "st_m": int(round(l.station_m)),
           "sim_lon": r(sl, 6), "sim_lat": r(sa, 6)}
          for l, sl, sa in zip(k.itertuples(), sim_lon, sim_lat)]
stations = [{"lon": r(l.lon, 6), "lat": r(l.lat, 6), "nom": l.name, "type": l.type}
            for l in g.itertuples() if l.dans_perimetre]

# --- Contours : zones (communes + arrondissements) avec leurs statistiques -----------
stats = pd.read_csv(DONNEES_TRAITEES / "stats_zones.csv", dtype={"code_zone": str})
z = gpd.read_file(DONNEES_BRUTES / "zones.geojson").merge(
    stats[["code_zone", "nb_kebabs", "kebabs_pour_10000_hab"]], on="code_zone", how="left")
z["geometry"] = z.to_crs(CRS_METRIQUE).geometry.simplify(60).to_crs(CRS_GPS)
zones = json.loads(z[["nom_zone", "population", "nb_kebabs", "kebabs_pour_10000_hab", "geometry"]]
                   .to_json(drop_id=True))
for f in zones["features"]:
    f["properties"]["nom_zone"] = f["properties"]["nom_zone"].replace(" Arrondissement", "")
    f["geometry"]["coordinates"] = json.loads(json.dumps(f["geometry"]["coordinates"]),
                                              parse_float=lambda x: round(float(x), 5))

iso = json.loads((DONNEES_BRUTES / "isochrones_saint_charles.json").read_text(encoding="utf-8"))
isochrones = [{"minutes": int(f["properties"]["contour"]), "contour": f["geometry"]["coordinates"]}
              for f in iso["features"]]

res = pd.read_csv(DONNEES_TRAITEES / "resultats_modele.csv")
effets = [{"libelle": l.libelle, "or": r(l.odds_ratio, 2), "bas": r(l.ic_bas, 2), "haut": r(l.ic_haut, 2),
           "p": float(l.p)} for l in res.itertuples()]
valid = pd.read_csv(DONNEES_TRAITEES / "resultats_validation.csv").iloc[0]

# --- Mouvement : rames de métro / tram et piétons sortant de Saint-Charles (script 14) -----------
from shapely.geometry import LineString  # noqa: E402

lignes = []
for l in json.loads((DONNEES_TRAITEES / "lignes_metro_tram.json").read_text(encoding="utf-8")):
    trace = LineString(l["trace"]).simplify(0.00008)          # ~8 m : assez fin pour l'animation
    lignes.append({"ref": l["ref"], "type": l["type"],
                   "trace": [[round(x, 5), round(y, 5)] for x, y in trace.coords]})
trajets = json.loads((DONNEES_BRUTES / "trajets_pietons_saint_charles.json").read_text(encoding="utf-8"))
index_kebab = {i: n for n, i in enumerate(k["id_kebab"])}
pietons = [{"k": index_kebab[i], "secondes": round(t["secondes"]),
            "trace": [[round(x, 5), round(y, 5)] for x, y in LineString(t["trace"]).simplify(0.00003).coords]}
           for i, t in trajets.items() if i in index_kebab]

# --- Ratés et comparaison des modèles (script 15) -----------------------------------------------
rates = pd.read_csv(DONNEES_TRAITEES / "rates_modele.csv")
centres_carreaux = c.set_index("idcar_200m")[["lon", "lat"]]
rates = rates.join(centres_carreaux, on="idcar_200m").head(10)
rates_liste = [{"lon": r(l.lon, 5), "lat": r(l.lat, 5), "zone": str(l.commune), "proba": float(l.proba_hors_echantillon),
                "rang": int(l.rang_sur_carreaux)} for l in rates.itertuples()]
comparaison = [{"modele": l.modele, "auc": r(l.auc_moyenne, 3)}
               for l in pd.read_csv(DONNEES_TRAITEES / "resultats_comparaison_modeles.csv").itertuples()]

donnees = {"lignes": lignes, "pietons": pietons, "gare": [5.3811927, 43.3032635],
           "rates": rates_liste, "comparaison": comparaison,
           "carreaux": carreaux, "kebabs": kebabs, "stations": stations, "zones": zones,
           "isochrones": isochrones, "opportunites": opportunites, "simulation": simulation,
           "effets": effets, "auc": r(valid.auc_moyenne, 2),
           "n_carreaux_modele": len(apprentissage)}
texte = json.dumps(donnees, ensure_ascii=False, separators=(",", ":"))
modele_html = (DOSSIER / "modele_scene.html").read_text(encoding="utf-8")
(DOSSIER / "kebabs_3d.html").write_text(modele_html.replace("/*__DONNEES__*/null", texte), encoding="utf-8")
print(f"dashboard/kebabs_3d.html écrit ({len(texte) / 1e6:.1f} Mo de données)")
