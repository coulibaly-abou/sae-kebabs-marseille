"""
07 - Analyse exploratoire spatiale : premières cartes et carroyage.

L'unité d'analyse est le carreau de la grille statistique, de 200 m (par défaut)
ou de 1 km selon TAILLE_CARREAU dans config.py. L'Insee diffuse Filosofi en
carreaux de 200 m ; chacun porte l'identifiant du carreau de 1 km qui le contient
(idcar_1km) : pour la grille de 1 km, on additionne les 25 petits carreaux.

Entrées : donnees/traitees/kebabs.csv (script 06), zones, carreaux Insee (scripts 01, 05)

Sorties (cartes PNG pour le rapport) :
    rapport/figures/fig01_kebabs_metropole.png   kebabs de la métropole (points)
    rapport/figures/fig02_kebabs_marseille.png   zoom Marseille, 16 arrondissements
    rapport/figures/fig03_carroyage_marseille.png nombre de kebabs par carreau
    rapport/figures/fig04_chaleur_marseille.png  carte de chaleur (densité lissée)
    rapport/figures/fig05_kebabs_par_habitant.png kebabs pour 10 000 habitants par zone
Sorties (tables pour les analyses suivantes) :
    donnees/traitees/carreaux_kebabs.gpkg  carreaux + nombre de kebabs
    donnees/traitees/stats_zones.csv       kebabs, population, densités par zone

Toutes les cartes sont en projection Insee (EPSG:3035, en mètres) : les
carreaux restent des carrés et les distances sont justes.
"""
import re

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap, ListedColormap
from matplotlib import patheffects
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy.stats import gaussian_kde
from shapely.geometry import box

from config import (CRS_GPS, CRS_INSEE, DONNEES_BRUTES, DONNEES_TRAITEES, ECHELLE, FIGURES,
                    TAILLE_CARREAU)
from utils import FICHIER_ZONES

# --- Charte graphique (palette de référence, validée daltonisme) ----------------
FOND = "#fcfcfb"
TEXTE = "#0b0b0b"
TEXTE_2 = "#52514e"
GRIS_ZONE = "#f0efec"        # zones / fond neutre
GRIS_HABITE = "#dcdad3"      # carreaux habités (contexte)
LIMITE = "#a3a29c"           # limites administratives
COULEUR_FIAB = {"certain": "#2a78d6", "probable": "#eb6834"}   # catégoriel, slots 1-2
BLEUS = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SOURCE = "Sources : OpenStreetMap, Insee (SIRENE, Filosofi 2019), IGN. Traitement : SAÉ kebabs."

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "text.color": TEXTE,
    "figure.facecolor": FOND, "axes.facecolor": FOND, "savefig.facecolor": FOND,
})
# Colonne identifiant du carreau dans les fichiers Insee, selon l'échelle
COL_ID = "idcar_200m" if TAILLE_CARREAU == 200 else "idcar_1km"
# Décalage (en points) des étiquettes de communes sur la carte de la métropole
DECALAGES = {"Marseille": (75, -45), "Aix-en-Provence": (45, 25), "Aubagne": (55, -25),
             "Vitrolles": (-20, 30), "Marignane": (-55, -20), "Gardanne": (55, 10),
             "Les Pennes-Mirabeau": (95, 20), "Salon-de-Provence": (0, -20)}


# --- Chargement ------------------------------------------------------------------------
def charger():
    k = pd.read_csv(DONNEES_TRAITEES / "kebabs.csv", dtype={"code_zone": str})
    kebabs = gpd.GeoDataFrame(k, geometry=gpd.points_from_xy(k["lon"], k["lat"]),
                              crs=CRS_GPS).to_crs(CRS_INSEE)
    zones = gpd.read_file(FICHIER_ZONES).to_crs(CRS_INSEE)
    communes = gpd.read_file(DONNEES_BRUTES / "metropole_communes.geojson").to_crs(CRS_INSEE)
    carreaux = gpd.read_file(DONNEES_BRUTES / "insee_carreaux_200m_metropole.gpkg").to_crs(CRS_INSEE)
    return kebabs, zones, communes, carreaux


# --- Carroyage : kebab -> carreau ------------------------------------------------------------
def id_carreau(x: float, y: float) -> str:
    """Identifiant Insee du carreau contenant le point (coin sud-ouest, EPSG:3035)."""
    x0 = int(x // TAILLE_CARREAU * TAILLE_CARREAU)
    y0 = int(y // TAILLE_CARREAU * TAILLE_CARREAU)
    return f"CRS3035RES{TAILLE_CARREAU}mN{y0}E{x0}"


def carre(id_car: str):
    """Polygone du carreau à partir de son identifiant."""
    y0, x0 = map(int, re.search(r"N(\d+)E(\d+)$", id_car).groups())
    return box(x0, y0, x0 + TAILLE_CARREAU, y0 + TAILLE_CARREAU)


def agreger_1km(c200: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Carreaux de 1 km à partir des carreaux de 200 m de l'Insee.

    - variables de comptage (individus, ménages, logements, revenus...) : somme ;
    - i_est_1km : 1 si l'Insee a dû estimer les valeurs du carreau de 1 km
      (moins de 11 ménages) ;
    - commune / code_zone : ceux où vit la majorité des habitants du carreau
      (un carreau de 1 km peut chevaucher deux communes).
    """
    comptages = [c for c in c200.columns if c.startswith(("ind", "men", "log"))]
    car = c200.groupby("idcar_1km")[comptages].sum()
    car["i_est_1km"] = c200.groupby("idcar_1km")["i_est_1km"].max()
    majoritaire = (c200.dropna(subset=["commune"])
                   .groupby(["idcar_1km", "code_zone", "commune"])["ind"].sum()
                   .reset_index().sort_values("ind").drop_duplicates("idcar_1km", keep="last")
                   .set_index("idcar_1km"))
    car = car.join(majoritaire[["code_zone", "commune"]]).reset_index()
    return gpd.GeoDataFrame(car, geometry=[carre(i) for i in car["idcar_1km"]], crs=CRS_INSEE)


def carroyer(kebabs, carreaux):
    """Nombre de kebabs par carreau. Un kebab situé dans un carreau sans
    habitant (zone commerciale, port...) n'a pas de carreau Insee : on crée son
    carreau à part (ind = 0) pour ne pas le perdre."""
    kebabs[COL_ID] = [id_carreau(p.x, p.y) for p in kebabs.geometry]
    compte = kebabs.groupby(COL_ID).agg(
        nb_kebabs=("id_kebab", "size"),
        nb_kebabs_certains=("fiabilite", lambda s: (s == "certain").sum()))
    car = carreaux.merge(compte, on=COL_ID, how="left")
    car[["nb_kebabs", "nb_kebabs_certains"]] = car[["nb_kebabs", "nb_kebabs_certains"]].fillna(0).astype(int)
    car["habite"] = True

    hors = compte[~compte.index.isin(carreaux[COL_ID])].reset_index()
    hors["commune"] = hors[COL_ID].map(kebabs.groupby(COL_ID)["commune"].first())
    if len(hors):
        hors = gpd.GeoDataFrame(hors, geometry=[carre(i) for i in hors[COL_ID]], crs=CRS_INSEE)
        hors["ind"], hors["habite"] = 0.0, False
        car = pd.concat([car, hors], ignore_index=True)
    return gpd.GeoDataFrame(car, crs=CRS_INSEE)


# --- Habillage des cartes ---------------------------------------------------------------
def habiller(ax, titre, sous_titre, bornes=None):
    ax.set_axis_off()
    if bornes is not None:
        ax.set_xlim(bornes[0], bornes[2])
        ax.set_ylim(bornes[1], bornes[3])
    ax.set_title(titre, loc="left", fontsize=12, fontweight="bold", color=TEXTE, pad=18)
    ax.text(0, 1.01, sous_titre, transform=ax.transAxes, fontsize=9, color=TEXTE_2, va="bottom")
    ax.text(0, -0.02, SOURCE, transform=ax.transAxes, fontsize=7, color=TEXTE_2, va="top")
    echelle(ax)


def echelle(ax):
    """Barre d'échelle en bas à droite (5 ou 10 km selon l'étendue)."""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    longueur = 10_000 if (x1 - x0) > 40_000 else 5_000
    x = x1 - (x1 - x0) * 0.05 - longueur
    y = y0 + (y1 - y0) * 0.04
    ax.plot([x, x + longueur], [y, y], color=TEXTE, lw=2, solid_capstyle="butt")
    ax.text(x + longueur / 2, y + (y1 - y0) * 0.012, f"{longueur // 1000} km",
            ha="center", va="bottom", fontsize=8, color=TEXTE)


def points_kebabs(ax, kebabs, taille=16):
    for fiab, couleur in COULEUR_FIAB.items():
        sel = kebabs[kebabs["fiabilite"] == fiab]
        ax.scatter(sel.geometry.x, sel.geometry.y, s=taille, color=couleur,
                   edgecolor=FOND, linewidth=0.6, zorder=5)


def legende_fiabilite(ax, kebabs, loc="upper left"):
    n = kebabs["fiabilite"].value_counts()
    poignees = [Line2D([], [], marker="o", ls="", markersize=6, color=c, markeredgecolor=FOND,
                       label=f"Kebab {f} ({n.get(f, 0)})") for f, c in COULEUR_FIAB.items()]
    ax.legend(handles=poignees, loc=loc, frameon=False, fontsize=8.5, labelcolor=TEXTE)


def sauver(fig, nom):
    fig.savefig(FIGURES / nom, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> figures/{nom}")


# --- Les cartes -------------------------------------------------------------------------
def carte_metropole(kebabs, zones, communes):
    fig, ax = plt.subplots(figsize=(8, 7))
    communes.plot(ax=ax, color=GRIS_ZONE, edgecolor=LIMITE, linewidth=0.4)
    marseille = communes[communes["nom"] == "Marseille"]
    marseille.boundary.plot(ax=ax, color=TEXTE_2, linewidth=1)
    points_kebabs(ax, kebabs, taille=14)
    # Étiquettes des communes ayant au moins 3 kebabs, décalées pour ne pas
    # masquer les points (trait fin vers le centre des kebabs de la commune)
    nb = kebabs["commune"].value_counts()
    centres = kebabs.groupby("commune").geometry.agg(lambda g: g.union_all().centroid)
    for nom in nb[nb >= 3].index:
        p = centres[nom]
        ax.annotate(f"{nom} ({nb[nom]})", (p.x, p.y), xytext=DECALAGES.get(nom, (0, 18)),
                    textcoords="offset points", ha="center", va="center", fontsize=7.5,
                    color=TEXTE, arrowprops=dict(arrowstyle="-", color=TEXTE_2, lw=0.5,
                                                 shrinkA=0, shrinkB=4))
    legende_fiabilite(ax, kebabs)
    habiller(ax, "Les kebabs de la métropole Aix-Marseille-Provence",
             f"{len(kebabs)} kebabs recensés dans 92 communes ; entre parenthèses, "
             "nombre de kebabs des communes qui en comptent au moins 3")
    sauver(fig, "fig01_kebabs_metropole.png")


def bornes_marseille(zones, marge=800):
    m = zones[zones["est_marseille"]].total_bounds
    return (m[0] - marge, m[1] - marge, m[2] + marge, m[3] + marge)


def fond_marseille(ax, zones):
    zones.plot(ax=ax, color=GRIS_ZONE, edgecolor=LIMITE, linewidth=0.4)
    zones[zones["est_marseille"]].plot(ax=ax, color="none", edgecolor=TEXTE_2, linewidth=0.7)


def numeros_arrondissements(ax, zones, kebabs=None):
    arr = zones[zones["est_marseille"]]
    nb = kebabs["code_zone"].value_counts() if kebabs is not None else None
    for _, z in arr.iterrows():
        p = z.geometry.representative_point()
        n = int(z["arrondissement"])
        txt = f"{n}e" if n > 1 else "1er"
        if nb is not None:
            txt += f"\n{nb.get(z['code_zone'], 0)}"
        ax.text(p.x, p.y, txt, ha="center", va="center", fontsize=7.5, color=TEXTE_2,
                fontweight="bold", zorder=3, clip_on=True,
                path_effects=[patheffects.withStroke(linewidth=2.5, foreground=FOND)])


def carte_marseille(kebabs, zones):
    fig, ax = plt.subplots(figsize=(8, 7.5))
    fond_marseille(ax, zones)
    km = kebabs[kebabs["commune"] == "Marseille"]
    numeros_arrondissements(ax, zones)
    points_kebabs(ax, kebabs, taille=20)
    legende_fiabilite(ax, km, loc="lower left")
    habiller(ax, "Les kebabs à Marseille",
             f"{len(km)} kebabs ; encart : zoom sur l'hypercentre (1er et 6e arrondissements)",
             bornes_marseille(zones))

    # Encart (placé dans la mer) : zoom sur l'hypercentre, où les points se superposent
    centre = zones[zones["arrondissement"].isin([1, 6])].total_bounds
    zoom = (centre[0] - 300, centre[1] - 300, centre[2] + 300, centre[3] + 300)
    enc = ax.inset_axes([0.0, 0.17, 0.36, 0.40])
    fond_marseille(enc, zones)
    numeros_arrondissements(enc, zones[zones["arrondissement"].isin([1, 2, 3, 4, 5, 6, 7])])
    points_kebabs(enc, kebabs, taille=22)
    enc.set_xlim(zoom[0], zoom[2]); enc.set_ylim(zoom[1], zoom[3])
    enc.set_xticks([]); enc.set_yticks([])
    enc.set_xlabel(""); enc.set_ylabel("")
    for bord in enc.spines.values():
        bord.set_edgecolor(TEXTE_2)
    ax.indicate_inset_zoom(enc, edgecolor=TEXTE_2, alpha=0.8)
    sauver(fig, "fig02_kebabs_marseille.png")


def carte_carroyage(car, zones):
    fig, ax = plt.subplots(figsize=(8, 7.5))
    fond_marseille(ax, zones)
    car[car["habite"]].plot(ax=ax, color=GRIS_HABITE, edgecolor=FOND,
                            linewidth=0 if TAILLE_CARREAU == 200 else 0.6)
    # Classes de nombre de kebabs (comptes de la légende : Marseille seulement)
    if TAILLE_CARREAU == 200:
        classes = [(1, 1, "1 kebab"), (2, 2, "2 kebabs"), (3, 999, "3 kebabs ou plus")]
        couleurs = [BLEUS[2], BLEUS[4], BLEUS[6]]
    else:
        classes = [(1, 1, "1 kebab"), (2, 3, "2 ou 3 kebabs"), (4, 9, "4 à 9 kebabs"),
                   (10, 999, "10 kebabs ou plus")]
        couleurs = [BLEUS[1], BLEUS[3], BLEUS[5], BLEUS[6]]
    avec = car[car["nb_kebabs"] > 0]
    avec_m = avec[avec["commune"] == "Marseille"]
    poignees = [Patch(color=GRIS_HABITE, label="Carreau habité, sans kebab")]
    for (bas, haut, lib), coul in zip(classes, couleurs):
        dans = avec["nb_kebabs"].between(bas, haut)
        bord = (coul, 0.8) if TAILLE_CARREAU == 200 else (FOND, 0.6)  # petits carreaux : bord plein
        avec[dans].plot(ax=ax, color=coul, edgecolor=bord[0], linewidth=bord[1], zorder=4)
        n = avec_m["nb_kebabs"].between(bas, haut).sum()
        poignees.append(Patch(color=coul, label=f"{lib} ({n} carreau{'x' if n > 1 else ''})"))
    zones[zones["est_marseille"]].plot(ax=ax, color="none", edgecolor=TEXTE_2, linewidth=0.7, zorder=5)
    ax.legend(handles=poignees, loc="lower left", frameon=False, fontsize=8.5, labelcolor=TEXTE)
    m = car[car["commune"] == "Marseille"]
    habiller(ax, f"Carroyage : nombre de kebabs par carreau de {ECHELLE} à Marseille",
             f"{(m['nb_kebabs'] > 0).sum()} carreaux sur {len(m)} contiennent au moins un kebab",
             bornes_marseille(zones))
    sauver(fig, "fig03_carroyage_marseille.png")


def carte_chaleur(kebabs, zones):
    bornes = bornes_marseille(zones)
    km = kebabs[kebabs["commune"] == "Marseille"]
    xy = np.vstack([km.geometry.x, km.geometry.y])
    # Lissage par noyau gaussien : écart-type ~ 400 m (quelques minutes à pied)
    kde = gaussian_kde(xy, bw_method=400 / xy.std(axis=1).mean())
    pas = 100
    gx, gy = np.meshgrid(np.arange(bornes[0], bornes[2], pas), np.arange(bornes[1], bornes[3], pas))
    dens = kde(np.vstack([gx.ravel(), gy.ravel()])).reshape(gx.shape)
    dens = dens * len(km) * 1e6  # -> kebabs par km²
    # Hors de Marseille ou densité négligeable : transparent
    dans = gpd.GeoSeries(gpd.points_from_xy(gx.ravel(), gy.ravel()), crs=CRS_INSEE).within(
        zones[zones["est_marseille"]].union_all()).values.reshape(gx.shape)
    dens = np.ma.masked_where(~dans | (dens < 0.25), dens)

    fig, ax = plt.subplots(figsize=(8, 7.5))
    fond_marseille(ax, zones)
    cmap = LinearSegmentedColormap.from_list("bleus", BLEUS)
    im = ax.imshow(dens, extent=(bornes[0], bornes[2], bornes[1], bornes[3]), origin="lower",
                   cmap=cmap, alpha=0.9, zorder=2)
    zones[zones["est_marseille"]].plot(ax=ax, color="none", edgecolor=TEXTE_2, linewidth=0.7, zorder=3)
    ax.scatter(km.geometry.x, km.geometry.y, s=3, color=TEXTE, zorder=4, linewidth=0)
    numeros_arrondissements(ax, zones)
    cb = fig.colorbar(im, ax=ax, shrink=0.45, pad=0.01)
    cb.set_label("Kebabs par km² (densité lissée)", color=TEXTE_2, fontsize=8)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=7.5, colors=TEXTE_2)
    habiller(ax, "Carte de chaleur des kebabs à Marseille",
             "Densité lissée (noyau gaussien de 400 m) ; points noirs = kebabs", bornes)
    sauver(fig, "fig04_chaleur_marseille.png")


def stats_par_zone(kebabs, zones):
    nb = kebabs.groupby("code_zone").agg(nb_kebabs=("id_kebab", "size"),
                                         nb_kebabs_certains=("fiabilite", lambda s: (s == "certain").sum()))
    st = zones.drop(columns="geometry").merge(nb, left_on="code_zone", right_index=True, how="left")
    st[["nb_kebabs", "nb_kebabs_certains"]] = st[["nb_kebabs", "nb_kebabs_certains"]].fillna(0).astype(int)
    st["surface_km2"] = st["surface"] / 100  # hectares -> km²
    st["kebabs_pour_10000_hab"] = st["nb_kebabs"] / st["population"] * 10_000
    st["habitants_par_kebab"] = (st["population"] / st["nb_kebabs"]).where(st["nb_kebabs"] > 0)
    st["kebabs_par_km2"] = st["nb_kebabs"] / st["surface_km2"]
    st = st.drop(columns="surface").sort_values("nb_kebabs", ascending=False)
    st.to_csv(DONNEES_TRAITEES / "stats_zones.csv", index=False, encoding="utf-8")
    return st


def carte_par_habitant(st, zones, communes):
    z = zones.merge(st[["code_zone", "kebabs_pour_10000_hab"]], on="code_zone")
    seuils = [0, 0.0001, 0.5, 1, 1.5, 2.5, 100]
    etiquettes = ["Aucun kebab", "moins de 0,5", "0,5 à 1", "1 à 1,5", "1,5 à 2,5", "2,5 et plus"]
    couleurs = [GRIS_ZONE, BLEUS[0], BLEUS[2], BLEUS[3], BLEUS[5], BLEUS[6]]
    norm = BoundaryNorm(seuils, len(couleurs))

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.4), gridspec_kw={"width_ratios": [1.45, 1]})
    for ax, titre, bornes in [(axes[0], "Métropole (communes)", None),
                              (axes[1], "Marseille (arrondissements)", bornes_marseille(zones))]:
        z.plot(ax=ax, column="kebabs_pour_10000_hab", cmap=ListedColormap(couleurs), norm=norm,
               edgecolor=FOND, linewidth=0.5)
        communes.boundary.plot(ax=ax, color=LIMITE, linewidth=0.3)
        ax.set_axis_off()
        ax.set_title(titre, loc="left", fontsize=10, color=TEXTE)
        if bornes:
            ax.set_xlim(bornes[0], bornes[2]); ax.set_ylim(bornes[1], bornes[3])
            numeros_arrondissements(ax, zones)
    axes[0].legend(handles=[Patch(color=c, label=e) for c, e in zip(couleurs, etiquettes)],
                   title="Kebabs pour 10 000 hab.", title_fontsize=8.5, loc="upper left",
                   frameon=False, fontsize=8, labelcolor=TEXTE)
    fig.suptitle("Nombre de kebabs pour 10 000 habitants", x=0.02, y=0.99, ha="left",
                 fontsize=12, fontweight="bold", color=TEXTE)
    fig.text(0.02, 0.0, SOURCE + " Population : recensement Insee.", fontsize=7, color=TEXTE_2)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.86, bottom=0.04, wspace=0.02)
    sauver(fig, "fig05_kebabs_par_habitant.png")


def main():
    print("[07] Cartes exploratoires")
    kebabs, zones, communes, carreaux = charger()

    base = carreaux if TAILLE_CARREAU == 200 else agreger_1km(carreaux)
    car = carroyer(kebabs, base)
    car.to_file(DONNEES_TRAITEES / "carreaux_kebabs.gpkg", driver="GPKG")
    hors = car[~car["habite"]]
    print(f"  carroyage : {(car['nb_kebabs'] > 0).sum()} carreaux avec au moins 1 kebab, "
          f"dont {len(hors)} sans habitant ({hors['nb_kebabs'].sum()} kebabs) ; "
          f"max {car['nb_kebabs'].max()} kebabs dans un carreau")

    st = stats_par_zone(kebabs, zones)
    print("  -> stats_zones.csv ; zones les plus dotées :")
    print(st.head(8)[["nom_zone", "nb_kebabs", "population", "kebabs_pour_10000_hab"]]
          .round(2).to_string(index=False))

    carte_metropole(kebabs, zones, communes)
    carte_marseille(kebabs, zones)
    carte_carroyage(car, zones)
    carte_chaleur(kebabs, zones)
    carte_par_habitant(st, zones, communes)


if __name__ == "__main__":
    main()
