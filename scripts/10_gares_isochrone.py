"""
10 - Effet des gares (H3) et carte isochrone autour de la gare Saint-Charles.

1. Isochrones à pied (5, 10 et 15 min) autour de Marseille Saint-Charles, calculées
   sur le réseau réel des rues et chemins piétons d'OpenStreetMap par le service
   libre Valhalla (https://valhalla1.openstreetmap.de, sans clé). Pour chaque
   anneau : nombre de kebabs, habitants (carreaux Insee) et kebabs pour 10 000 hab.
2. Test H3 : les kebabs sont-ils plus proches des gares que les habitants ?
   Distance de chaque kebab à la gare / station la plus proche, comparée à celle
   de kebabs fictifs placés au hasard chez les habitants (999 simulations, même
   principe que le test H1 du script 08). Deux définitions de la « gare » :
   gares SNCF seules, puis toutes les stations (train, métro, tram).

Sorties :
    donnees/brutes/isochrones_saint_charles.json    réponse brute de Valhalla (cache)
    donnees/traitees/resultats_isochrone.csv        kebabs et habitants par anneau
    donnees/traitees/resultats_gares.csv            test H3
    rapport/figures/fig10_isochrone_saint_charles.png
    rapport/figures/fig11_gares_kebabs.png
"""
import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy.spatial import cKDTree

from config import CRS_GPS, CRS_INSEE, DONNEES_BRUTES, DONNEES_TRAITEES, FIGURES, HEADERS
from utils import FICHIER_ZONES

VALHALLA = "https://valhalla1.openstreetmap.de/isochrone"
MINUTES = [5, 10, 15]
GRAINE = 2026
N_SIMULATIONS = 999
RAYON_PROCHE = 500  # m : « à proximité d'une station »

FOND, TEXTE, TEXTE_2 = "#fcfcfb", "#0b0b0b", "#52514e"
GRIS_ZONE, LIMITE = "#f0efec", "#a3a29c"
KEBAB = "#eb6834"
PROCHE = "#cfccc2"   # zone à moins de 500 m d'une station
ANNEAUX = {5: "#6da7ec", 10: "#9ec5f4", 15: "#cde2fb"}   # du plus foncé (proche) au plus clair
STATIONS = {"train": ("s", TEXTE, "Gare SNCF / TER"), "metro": ("^", "#2a78d6", "Station de métro"),
            "tram": ("D", "#1baf7a", "Arrêt de tram")}
SOURCE = "Sources : OpenStreetMap, Valhalla, Insee (SIRENE, Filosofi 2019), IGN. Traitement : SAÉ kebabs."
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "text.color": TEXTE,
                     "figure.facecolor": FOND, "axes.facecolor": FOND, "savefig.facecolor": FOND})


# --- Données ---------------------------------------------------------------------------
def charger():
    k = pd.read_csv(DONNEES_TRAITEES / "kebabs.csv")
    kebabs = gpd.GeoDataFrame(k, geometry=gpd.points_from_xy(k["lon"], k["lat"]), crs=CRS_GPS)
    g = pd.read_csv(DONNEES_BRUTES / "gares.csv")
    gares = gpd.GeoDataFrame(g, geometry=gpd.points_from_xy(g["lon"], g["lat"]), crs=CRS_GPS)
    zones = gpd.read_file(FICHIER_ZONES)
    carreaux = gpd.read_file(DONNEES_BRUTES / "insee_carreaux_200m_metropole.gpkg")
    return kebabs, gares, zones, carreaux


def isochrones(lon: float, lat: float) -> gpd.GeoDataFrame:
    """Isochrones piétonnes (Valhalla), mises en cache. Renvoie un polygone par durée."""
    cache = DONNEES_BRUTES / "isochrones_saint_charles.json"
    if cache.exists():
        print("  -> cache utilisé : isochrones_saint_charles.json")
        data = json.loads(cache.read_text(encoding="utf-8"))
    else:
        # radius : le point de la gare est sur les voies ; on cherche le chemin piéton
        # le plus proche dans un rayon de 300 m
        requete = {"locations": [{"lat": lat, "lon": lon, "radius": 300}], "costing": "pedestrian",
                   "contours": [{"time": m} for m in MINUTES], "polygons": True}
        for essai in range(3):  # le service public est parfois saturé
            try:
                # JSON sans espaces : un espace encodé en "+" dans l'URL est refusé par Valhalla
                r = requests.get(VALHALLA, params={"json": json.dumps(requete, separators=(",", ":"))},
                                 headers=HEADERS, timeout=120)
                r.raise_for_status()
                data = r.json()
                break
            except (requests.RequestException, ValueError) as e:
                print(f"     échec Valhalla ({e}), nouvel essai")
        else:
            raise RuntimeError("Le service Valhalla ne répond pas. Réessayer plus tard.")
        cache.write_text(json.dumps(data), encoding="utf-8")
    iso = gpd.GeoDataFrame.from_features(data["features"], crs=CRS_GPS)
    iso["minutes"] = iso["contour"].astype(int)
    return iso[["minutes", "geometry"]].sort_values("minutes").reset_index(drop=True)


# --- 1. Kebabs et habitants par anneau d'isochrone -------------------------------------------
def bilan_anneaux(iso, kebabs, carreaux, marseille_geom):
    """Anneaux 0-5, 5-10, 10-15 min, puis le reste de Marseille."""
    centres = carreaux.set_geometry(carreaux.centroid)
    lignes, deja = [], None
    for _, ligne in iso.iterrows():
        anneau = ligne.geometry if deja is None else ligne.geometry.difference(deja)
        lignes.append((f"{ligne['minutes'] - 5} à {ligne['minutes']} min", anneau))
        deja = ligne.geometry if deja is None else deja.union(ligne.geometry)
    lignes.append(("Reste de Marseille", marseille_geom.difference(deja)))

    res = []
    for nom, geom in lignes:
        g = gpd.GeoSeries([geom], crs=CRS_INSEE)[0]
        nb_k = kebabs.within(g).sum()
        hab = centres.loc[centres.within(g), "ind"].sum()
        res.append({"zone": nom, "kebabs": nb_k, "habitants": round(hab),
                    "surface_km2": g.area / 1e6,
                    "kebabs_pour_10000_hab": nb_k / hab * 1e4 if hab else np.nan,
                    "kebabs_par_km2": nb_k / (g.area / 1e6)})
    res = pd.DataFrame(res)
    res.to_csv(DONNEES_TRAITEES / "resultats_isochrone.csv", index=False, encoding="utf-8")
    return res


# --- 2. Test H3 : distance aux gares, kebabs contre habitants ------------------------------------
def test_gares(kebabs, gares, carreaux, rng):
    lignes = []
    for terr, k, c in [("Marseille", kebabs[kebabs["commune"] == "Marseille"],
                        carreaux[carreaux["commune"] == "Marseille"]),
                       ("Métropole", kebabs, carreaux)]:
        poids = (c["ind"] / c["ind"].sum()).values
        b = c.geometry.bounds
        coins = np.column_stack([b["minx"], b["miny"]])
        cote = (b["maxx"] - b["minx"]).values
        xy_k = np.column_stack([k.geometry.x, k.geometry.y])
        centres = np.column_stack([c.geometry.centroid.x, c.geometry.centroid.y])
        for definition, sel in [("Gares SNCF / TER", gares["type"] == "train"),
                                ("Toutes les stations (train, métro, tram)", gares.index == gares.index)]:
            arbre = cKDTree(np.column_stack([gares[sel].geometry.x, gares[sel].geometry.y]))
            d_k = arbre.query(xy_k)[0]
            simulees = []
            for _ in range(N_SIMULATIONS):
                t = rng.choice(len(c), size=len(k), p=poids)
                pts = coins[t] + rng.uniform(0, 1, (len(k), 2)) * cote[t][:, None]
                simulees.append(np.median(arbre.query(pts)[0]))
            simulees = np.array(simulees)
            d_hab = arbre.query(centres)[0]
            lignes.append({
                "territoire": terr, "definition_gare": definition,
                "distance_mediane_kebabs_m": np.median(d_k),
                "distance_mediane_si_comme_population_m": np.median(simulees),
                "p_valeur": (np.sum(simulees <= np.median(d_k)) + 1) / (N_SIMULATIONS + 1),
                f"part_kebabs_moins_{RAYON_PROCHE}m": np.mean(d_k < RAYON_PROCHE),
                f"part_habitants_moins_{RAYON_PROCHE}m": c.loc[d_hab < RAYON_PROCHE, "ind"].sum() / c["ind"].sum(),
            })
    res = pd.DataFrame(lignes)
    res.to_csv(DONNEES_TRAITEES / "resultats_gares.csv", index=False, encoding="utf-8")
    return res


# --- Figures ------------------------------------------------------------------------------------------
def legende_texte(ax, titre, sous_titre):
    ax.set_axis_off()
    ax.set_title(titre, loc="left", fontsize=12, fontweight="bold", pad=18)
    ax.text(0, 1.01, sous_titre, transform=ax.transAxes, fontsize=9, color=TEXTE_2, va="bottom")
    ax.text(0, -0.02, SOURCE, transform=ax.transAxes, fontsize=7, color=TEXTE_2, va="top")


def echelle(ax, longueur):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x = x1 - (x1 - x0) * 0.05 - longueur
    y = y0 + (y1 - y0) * 0.04
    ax.plot([x, x + longueur], [y, y], color=TEXTE, lw=2, solid_capstyle="butt")
    ax.text(x + longueur / 2, y + (y1 - y0) * 0.012,
            f"{longueur / 1000:g} km".replace(".", ","), ha="center", va="bottom", fontsize=8)


def figure_isochrone(iso, bilan, kebabs, gares, zones, gare_sc):
    fig, ax = plt.subplots(figsize=(8, 7.5))
    zones.plot(ax=ax, color=GRIS_ZONE, edgecolor=LIMITE, linewidth=0.5)
    for _, l in iso.sort_values("minutes", ascending=False).iterrows():
        gpd.GeoSeries([l.geometry], crs=CRS_INSEE).plot(ax=ax, color=ANNEAUX[l["minutes"]],
                                                        edgecolor=FOND, linewidth=1)
    zones[zones["est_marseille"]].boundary.plot(ax=ax, color=TEXTE_2, linewidth=0.7)
    ax.scatter(kebabs.geometry.x, kebabs.geometry.y, s=26, color=KEBAB, edgecolor=FOND,
               linewidth=0.8, zorder=5)
    ax.scatter([gare_sc.x], [gare_sc.y], s=180, marker="*", color=TEXTE, edgecolor=FOND,
               linewidth=1, zorder=6)
    ax.annotate("Gare Saint-Charles", (gare_sc.x, gare_sc.y), xytext=(10, 10),
                textcoords="offset points", fontsize=8.5, fontweight="bold")
    b = iso.total_bounds
    marge = 700
    ax.set_xlim(b[0] - marge, b[2] + marge); ax.set_ylim(b[1] - marge, b[3] + marge)
    poignees = [Patch(color=ANNEAUX[m], label=f"{lib} à pied ({int(n)} kebab{'s' if n > 1 else ''})")
                for m, lib, n in zip(MINUTES, bilan["zone"][:3], bilan["kebabs"][:3])]
    poignees.append(Line2D([], [], marker="o", ls="", markersize=6, color=KEBAB,
                           markeredgecolor=FOND, label="Kebab"))
    ax.legend(handles=poignees, loc="lower left", frameon=True, facecolor=FOND, edgecolor="none",
              framealpha=0.9, fontsize=8.5, title="Temps de marche depuis la gare", title_fontsize=8.5)
    legende_texte(ax, "Isochrones à pied autour de la gare Saint-Charles",
                  "Zones atteignables en 5, 10 et 15 minutes de marche par le réseau des rues")
    echelle(ax, 500)
    fig.savefig(FIGURES / "fig10_isochrone_saint_charles.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("  -> figures/fig10_isochrone_saint_charles.png")


def figure_gares(kebabs, gares, zones):
    marseille = zones[zones["est_marseille"]]
    fig, ax = plt.subplots(figsize=(8, 7.5))
    zones.plot(ax=ax, color=GRIS_ZONE, edgecolor=LIMITE, linewidth=0.4)
    # Zone à moins de 500 m d'une station (toutes stations confondues)
    proche = gpd.GeoSeries([gares.buffer(RAYON_PROCHE).union_all()], crs=CRS_INSEE)
    proche.intersection(marseille.union_all()).plot(ax=ax, color=PROCHE, linewidth=0)
    marseille.plot(ax=ax, color="none", edgecolor=TEXTE_2, linewidth=0.7)
    k = kebabs[kebabs["commune"] == "Marseille"]
    ax.scatter(k.geometry.x, k.geometry.y, s=20, color=KEBAB, edgecolor=FOND, linewidth=0.7, zorder=4)
    poignees = [Patch(color=PROCHE, label=f"Moins de {RAYON_PROCHE} m d'une station")]
    for t, (marqueur, couleur, lib) in STATIONS.items():
        g = gares[gares["type"] == t]
        ax.scatter(g.geometry.x, g.geometry.y, s=30 if t == "train" else 22, marker=marqueur,
                   color=couleur, edgecolor=FOND, linewidth=0.7, zorder=5)
        poignees.append(Line2D([], [], marker=marqueur, ls="", markersize=6, color=couleur,
                               markeredgecolor=FOND, label=lib))
    poignees.append(Line2D([], [], marker="o", ls="", markersize=6, color=KEBAB,
                           markeredgecolor=FOND, label=f"Kebab ({len(k)})"))
    b = marseille.total_bounds
    ax.set_xlim(b[0] - 800, b[2] + 800); ax.set_ylim(b[1] - 800, b[3] + 800)
    ax.legend(handles=poignees, loc="lower left", frameon=False, fontsize=8.5)
    legende_texte(ax, "Gares, stations et kebabs à Marseille",
                  "En gris : zone à moins de 500 m d'une gare, d'une station de métro ou de tram")
    echelle(ax, 5000)
    fig.savefig(FIGURES / "fig11_gares_kebabs.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("  -> figures/fig11_gares_kebabs.png")


def main():
    print("[10] Gares (H3) et isochrone Saint-Charles")
    rng = np.random.default_rng(GRAINE)
    kebabs, gares, zones, carreaux = charger()
    sc = gares[gares["name"] == "Marseille Saint-Charles"].iloc[0]
    iso = isochrones(sc["lon"], sc["lat"]).to_crs(CRS_INSEE)

    kebabs, gares, zones, carreaux = (x.to_crs(CRS_INSEE) for x in (kebabs, gares, zones, carreaux))
    marseille_geom = zones[zones["est_marseille"]].union_all()
    bilan = bilan_anneaux(iso, kebabs, carreaux, marseille_geom)
    print(bilan.round(2).to_string(index=False))
    dans15 = bilan["kebabs"][:3].sum()
    print(f"  à moins de 15 min à pied de Saint-Charles : {dans15} kebabs sur "
          f"{(kebabs['commune'] == 'Marseille').sum()} à Marseille, pour "
          f"{bilan['habitants'][:3].sum() / bilan['habitants'].sum():.1%} des habitants")

    h3 = test_gares(kebabs, gares, carreaux, rng)
    print(h3.round(3).to_string(index=False))

    gare_sc = gares[gares["name"] == "Marseille Saint-Charles"].geometry.iloc[0]
    figure_isochrone(iso, bilan, kebabs, gares, zones, gare_sc)
    figure_gares(kebabs, gares, zones)


if __name__ == "__main__":
    main()
