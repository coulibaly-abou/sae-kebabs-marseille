"""
08 - Croisement des kebabs avec les variables socio-démographiques (Insee).

Unité d'analyse : le carreau de la grille (200 m ou 1 km, voir TAILLE_CARREAU dans
config.py), fichier donnees/traitees/carreaux_kebabs.gpkg produit par le script 07.
On ne garde que les carreaux NON IMPUTÉS (i_est_200 ou i_est_1km = 0) : pour les carreaux de
moins de 11 ménages, l'Insee remplace les valeurs par des estimations (secret
statistique), inutilisables pour un croisement.

Tests réalisés (hypothèses du rapport) :
    H1  répartition non homogène : les kebabs sont-ils plus groupés que la
        population ? (test par simulation des plus proches voisins)
    H2  lien avec la population : corrélations de Spearman entre le nombre de
        kebabs du carreau et 7 indicateurs, avec correction de Holm
        (comparaisons multiples) ; comparaison des carreaux avec / sans kebab
        (Mann-Whitney) ; corrélations partielles à distance du centre égale
        (effet confondant centre / périphérie), à Marseille.
    H4  fracture Nord / Sud à Marseille : test binomial exact sur les taux de
        kebabs par habitant.

Sorties :
    donnees/traitees/carreaux_indicateurs.gpkg   carreaux + indicateurs (pour la modélisation)
    donnees/traitees/resultats_spearman.csv      tableau des corrélations
    donnees/traitees/resultats_tests.csv         autres tests (H1, H4, Mann-Whitney)
    rapport/figures/fig06_niveau_vie_kebabs.png  carte : niveau de vie et kebabs (Marseille)
    rapport/figures/fig07_correlations.png       corrélations de Spearman (graphique)
    rapport/figures/fig08_jeunes_adultes_kebabs.png carte : part des 18-39 ans et kebabs
    rapport/figures/fig09_structure_ages.png     structure par âge, carreaux avec / sans kebab
    donnees/traitees/resultats_ages.csv          analyse détaillée par tranche d'âge
"""
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy import stats
from scipy.spatial import cKDTree

from config import (CRS_GPS, CRS_INSEE, DONNEES_BRUTES, DONNEES_TRAITEES, ECHELLE, FIGURES,
                    TAILLE_CARREAU)
from utils import FICHIER_ZONES

# Le Vieux-Port : point de référence pour la distance au centre de Marseille
VIEUX_PORT = (5.3740, 43.2951)  # lon, lat
GRAINE = 2026                   # simulations reproductibles
N_SIMULATIONS = 999

# Indicateurs construits : nom -> (libellé pour les tableaux et graphiques)
INDICATEURS = {
    "densite_hab_km2": "Densité de population (hab./km²)",
    "niveau_vie_moyen": "Niveau de vie moyen (€/an)",
    "taux_pauvrete": "Taux de pauvreté des ménages",
    "part_logement_social": "Part de logements sociaux",
    "part_18_39": "Part des 18-39 ans",
    "part_65_plus": "Part des 65 ans et plus",
    "dist_gare_m": "Distance à la gare / station la plus proche (m)",
}

# Charte graphique (identique au script 07)
FOND, TEXTE, TEXTE_2 = "#fcfcfb", "#0b0b0b", "#52514e"
GRIS_ZONE, LIMITE = "#f0efec", "#a3a29c"
SERIE = {"Métropole": "#2a78d6", "Marseille": "#eb6834"}
BLEUS = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SOURCE = "Sources : OpenStreetMap, Insee (SIRENE, Filosofi 2019), IGN. Traitement : SAÉ kebabs."
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "text.color": TEXTE,
                     "figure.facecolor": FOND, "axes.facecolor": FOND, "savefig.facecolor": FOND})


# --- Préparation ----------------------------------------------------------------------
def construire_indicateurs(car: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Indicateurs par carreau (ratios Insee) + distances aux gares et au centre."""
    logements = car[["log_av45", "log_45_70", "log_70_90", "log_ap90", "log_inc"]].sum(axis=1)
    ind = car["ind"].where(car["ind"] > 0)
    car["densite_hab_km2"] = car["ind"] / (car.geometry.area / 1e6)  # surface du carreau en km²
    car["niveau_vie_moyen"] = car["ind_snv"] / ind
    car["taux_pauvrete"] = car["men_pauv"] / car["men"].where(car["men"] > 0)
    car["part_logement_social"] = car["log_soc"] / logements.where(logements > 0)
    car["part_18_39"] = (car["ind_18_24"] + car["ind_25_39"]) / ind
    car["part_65_plus"] = (car["ind_65_79"] + car["ind_80p"]) / ind
    car["presence_kebab"] = (car["nb_kebabs"] > 0).astype(int)

    # Distances (en m) depuis le centre du carreau
    centres = car.geometry.centroid
    xy = np.column_stack([centres.x, centres.y])
    gares = pd.read_csv(DONNEES_BRUTES / "gares.csv")
    gares = gpd.GeoDataFrame(gares, geometry=gpd.points_from_xy(gares["lon"], gares["lat"]),
                             crs=CRS_GPS).to_crs(CRS_INSEE)
    car["dist_gare_m"] = cKDTree(np.column_stack([gares.geometry.x, gares.geometry.y])).query(xy)[0]
    trains = gares[gares["type"] == "train"]
    car["dist_gare_sncf_m"] = cKDTree(np.column_stack([trains.geometry.x, trains.geometry.y])).query(xy)[0]
    vp = gpd.GeoSeries(gpd.points_from_xy([VIEUX_PORT[0]], [VIEUX_PORT[1]]), crs=CRS_GPS).to_crs(CRS_INSEE)[0]
    car["dist_vieux_port_m"] = np.hypot(xy[:, 0] - vp.x, xy[:, 1] - vp.y)
    return car


# --- Outils statistiques ----------------------------------------------------------------
def holm(p: pd.Series) -> pd.Series:
    """Correction de Holm-Bonferroni des p-valeurs (comparaisons multiples)."""
    ordre = p.sort_values()
    m = len(p)
    ajust = np.minimum(1, np.maximum.accumulate(ordre.values * (m - np.arange(m))))
    return pd.Series(ajust, index=ordre.index).reindex(p.index)


def spearman_ic(x, y, niveau=0.95):
    """rho de Spearman, p-valeur et intervalle de confiance (transformation de Fisher)."""
    ok = x.notna() & y.notna()
    rho, p = stats.spearmanr(x[ok], y[ok])
    n = ok.sum()
    z, se = np.arctanh(rho), 1.06 / np.sqrt(n - 3)  # erreur type de Fieller pour Spearman
    q = stats.norm.ppf(0.5 + niveau / 2)
    return rho, p, np.tanh(z - q * se), np.tanh(z + q * se), n


def correlation_partielle(x, y, controle):
    """Spearman partiel : corrélation des résidus des rangs de x et y après
    régression linéaire sur le rang de la variable de contrôle."""
    ok = x.notna() & y.notna() & controle.notna()
    rx, ry, rc = (stats.rankdata(v[ok]) for v in (x, y, controle))
    res = lambda r: r - np.polyval(np.polyfit(rc, r, 1), rc)
    return stats.pearsonr(res(rx), res(ry))


def fmt_p(p):
    return "< 0,001" if p < 0.001 else f"{p:.3f}".replace(".", ",")


# --- H1 : les kebabs sont-ils plus groupés que la population ? -----------------------------
def test_regroupement(kebabs_xy, car, rng):
    """Distance moyenne au plus proche voisin des kebabs, comparée à celle de
    kebabs fictifs placés au hasard CHEZ LES HABITANTS (tirage des carreaux
    proportionnel à la population, position uniforme dans le carreau).
    Si les vrais kebabs sont plus proches entre eux : regroupement au-delà de
    ce qu'explique la répartition de la population."""
    def dist_ppv(xy):
        return cKDTree(xy).query(xy, k=2)[0][:, 1].mean()

    observe = dist_ppv(kebabs_xy)
    poids = (car["ind"] / car["ind"].sum()).values
    bornes = car.geometry.bounds
    coins = np.column_stack([bornes["minx"], bornes["miny"]])
    cote = (bornes["maxx"] - bornes["minx"]).values  # côté du carreau (m)
    simules = []
    for _ in range(N_SIMULATIONS):
        tirage = rng.choice(len(car), size=len(kebabs_xy), p=poids)
        decalage = rng.uniform(0, 1, (len(kebabs_xy), 2)) * cote[tirage][:, None]
        simules.append(dist_ppv(coins[tirage] + decalage))
    simules = np.array(simules)
    p = (np.sum(simules <= observe) + 1) / (N_SIMULATIONS + 1)
    return observe, np.median(simules), p


# --- Figures ------------------------------------------------------------------------------
def figure_correlations(sp: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 4.6))
    variables = list(INDICATEURS)
    y = np.arange(len(variables))[::-1]
    decalage = {"Métropole": 0.14, "Marseille": -0.14}
    for terr, coul in SERIE.items():
        d = sp[sp["territoire"] == terr].set_index("variable").loc[variables]
        yy = y + decalage[terr]
        ax.hlines(yy, d["ic_bas"], d["ic_haut"], color=coul, lw=2)
        ax.scatter(d["rho"], yy, s=40, color=coul, edgecolor=FOND, linewidth=1, zorder=3,
                   label=f"{terr} (n = {int(d['n'].iloc[0]):,} carreaux)".replace(",", " "))
        # Valeur écrite au bout de l'intervalle, du côté opposé à zéro
        for yi, r, bas, haut, sig in zip(yy, d["rho"], d["ic_bas"], d["ic_haut"], d["p_holm"] < 0.05):
            x, ha = (haut + 0.006, "left") if r >= 0 else (bas - 0.006, "right")
            ax.text(x, yi, f"{r:+.2f}".replace(".", ",") + ("" if sig else " (ns)"),
                    ha=ha, va="center", fontsize=7.5, color=TEXTE_2)
    ax.axvline(0, color=TEXTE_2, lw=0.8)
    # Axe symétrique autour de 0, avec de la place pour les valeurs écrites
    borne = max(abs(sp["ic_bas"].min()), sp["ic_haut"].max()) + 0.1
    ax.set_xlim(-borne, borne)
    ax.set_yticks(y, [INDICATEURS[v] for v in variables], fontsize=8.5)
    ax.set_xlabel("Corrélation de Spearman avec le nombre de kebabs du carreau", color=TEXTE_2)
    ax.grid(axis="x", color="#e6e5e0", lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(LIMITE)
    ax.tick_params(colors=TEXTE_2, length=0)
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    ax.set_title(f"Corrélations entre kebabs et caractéristiques des carreaux de {ECHELLE}",
                 loc="left", fontsize=11, fontweight="bold", pad=22)
    ax.text(0, 1.02, "Point = rho de Spearman ; trait = intervalle de confiance à 95 % ; "
            "(ns) = non significatif après correction de Holm", transform=ax.transAxes,
            fontsize=8, color=TEXTE_2)
    fig.text(0.01, -0.02, SOURCE + " Carreaux habités non imputés.", fontsize=7, color=TEXTE_2)
    fig.savefig(FIGURES / "fig07_correlations.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("  -> figures/fig07_correlations.png")


def carte_indicateur(car_m, kebabs_m, zones, colonne, seuils, etiquettes, titre_legende,
                     titre, fichier):
    """Carte d'un indicateur par carreau (classes, dégradé de bleus) avec les kebabs, à Marseille."""
    couleurs = BLEUS[:len(etiquettes)]
    fig, ax = plt.subplots(figsize=(8, 7.5))
    zones.plot(ax=ax, color=GRIS_ZONE, edgecolor=LIMITE, linewidth=0.4)
    car_m.plot(ax=ax, column=colonne, cmap=ListedColormap(couleurs),
               norm=BoundaryNorm(seuils, len(couleurs)), linewidth=0)
    marseille = zones[zones["est_marseille"]]
    marseille.plot(ax=ax, color="none", edgecolor=TEXTE_2, linewidth=0.7)
    ax.scatter(kebabs_m.geometry.x, kebabs_m.geometry.y, s=22, color="#eb6834",
               edgecolor=FOND, linewidth=0.8, zorder=5)
    b = marseille.total_bounds
    ax.set_xlim(b[0] - 800, b[2] + 800); ax.set_ylim(b[1] - 800, b[3] + 800)
    ax.set_axis_off()
    poignees = [Patch(color=c, label=e) for c, e in zip(couleurs, etiquettes)]
    poignees.append(Line2D([], [], marker="o", ls="", markersize=6, color="#eb6834",
                           markeredgecolor=FOND, label=f"Kebab ({len(kebabs_m)})"))
    ax.legend(handles=poignees, loc="lower left", frameon=False, fontsize=8,
              title=titre_legende, title_fontsize=8.5)
    ax.set_title(titre, loc="left", fontsize=12, fontweight="bold", pad=18)
    ax.text(0, 1.01, f"Carreaux de {ECHELLE} non imputés (Filosofi 2019) ; points = kebabs",
            transform=ax.transAxes, fontsize=9, color=TEXTE_2, va="bottom")
    ax.text(0, -0.02, SOURCE, transform=ax.transAxes, fontsize=7, color=TEXTE_2, va="top")
    fig.savefig(FIGURES / fichier, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> figures/{fichier}")


def figure_niveau_vie(car_m, kebabs_m, zones):
    carte_indicateur(
        car_m, kebabs_m, zones, "niveau_vie_moyen",
        [0, 13_000, 16_000, 20_000, 25_000, 32_000, 1e9],
        ["moins de 13 000 €", "13 000 à 16 000 €", "16 000 à 20 000 €",
         "20 000 à 25 000 €", "25 000 à 32 000 €", "32 000 € et plus"],
        "Niveau de vie moyen par habitant",
        "Niveau de vie et implantation des kebabs à Marseille", "fig06_niveau_vie_kebabs.png")


def figure_jeunes_adultes(car_m, kebabs_m, zones):
    # Classes calées sur la distribution marseillaise (déciles 10 % / médiane / 90 %) :
    # 200 m : 17 % / 24 % / 34 % ; 1 km : 20 % / 25 % / 30 %
    if TAILLE_CARREAU == 200:
        seuils = [0, 0.18, 0.21, 0.24, 0.28, 0.33, 1.01]
    else:
        seuils = [0, 0.20, 0.22, 0.24, 0.26, 0.29, 1.01]
    etiquettes = [f"moins de {seuils[1]:.0%}"] + [
        f"{a:.0%} à {b:.0%}" for a, b in zip(seuils[1:-2], seuils[2:-1])] + [f"{seuils[-2]:.0%} et plus"]
    carte_indicateur(
        car_m, kebabs_m, zones, "part_18_39", seuils,
        [e.replace("%", " %") for e in etiquettes],
        "Part des 18-39 ans dans la population",
        "Jeunes adultes et implantation des kebabs à Marseille", "fig08_jeunes_adultes_kebabs.png")


# --- Analyse détaillée par tranche d'âge -----------------------------------------------------
TRANCHES_AGE = {"ind_0_3": "0-3 ans", "ind_4_5": "4-5 ans", "ind_6_10": "6-10 ans",
                "ind_11_17": "11-17 ans", "ind_18_24": "18-24 ans", "ind_25_39": "25-39 ans",
                "ind_40_54": "40-54 ans", "ind_55_64": "55-64 ans", "ind_65_79": "65-79 ans",
                "ind_80p": "80 ans et plus"}


def analyse_ages(territoires: dict) -> pd.DataFrame:
    """Pour chaque tranche d'âge : sa part dans la population des carreaux avec /
    sans kebab, et la corrélation de Spearman (part de la tranche dans le carreau
    vs nombre de kebabs), corrigée par Holm sur les 20 tests."""
    lignes = []
    for t, d in territoires.items():
        total = d[list(TRANCHES_AGE)].sum(axis=1)
        avec, sans = d[d["presence_kebab"] == 1], d[d["presence_kebab"] == 0]
        for col, lib in TRANCHES_AGE.items():
            part = d[col] / total.where(total > 0)
            rho, p, bas, haut, n = spearman_ic(part, d["nb_kebabs"])
            lignes.append({
                "territoire": t, "tranche": lib,
                "part_carreaux_avec_kebab": avec[col].sum() / avec[list(TRANCHES_AGE)].sum().sum(),
                "part_carreaux_sans_kebab": sans[col].sum() / sans[list(TRANCHES_AGE)].sum().sum(),
                "rho": rho, "ic_bas": bas, "ic_haut": haut, "p": p, "n": n})
    res = pd.DataFrame(lignes)
    res["ecart_points"] = (res["part_carreaux_avec_kebab"] - res["part_carreaux_sans_kebab"]) * 100
    res["p_holm"] = holm(res["p"])
    res.to_csv(DONNEES_TRAITEES / "resultats_ages.csv", index=False, encoding="utf-8")
    return res


def figure_structure_ages(res: pd.DataFrame):
    """Structure par âge des habitants, carreaux avec / sans kebab (Marseille)."""
    d = res[res["territoire"] == "Marseille"].reset_index(drop=True)
    y = np.arange(len(d))[::-1]
    h = 0.38
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(y + h / 2, d["part_carreaux_avec_kebab"] * 100, height=h - 0.04,
            color="#eb6834", label="Carreaux avec au moins un kebab")
    ax.barh(y - h / 2, d["part_carreaux_sans_kebab"] * 100, height=h - 0.04,
            color="#2a78d6", label="Carreaux sans kebab")
    # Écart en points, en gras quand la corrélation est significative après Holm
    xmax = d[["part_carreaux_avec_kebab", "part_carreaux_sans_kebab"]].max(axis=1) * 100
    for yi, e, xm, sig in zip(y, d["ecart_points"], xmax, d["p_holm"] < 0.05):
        texte = "0,0 pt" if abs(e) < 0.05 else f"{e:+.1f} pt".replace(".", ",")
        ax.text(xm + 0.4, yi, texte, va="center", fontsize=8,
                color=TEXTE if sig else TEXTE_2, fontweight="bold" if sig else "normal")
    ax.set_yticks(y, d["tranche"], fontsize=8.5)
    ax.set_xlabel("Part dans la population des carreaux (%)", color=TEXTE_2)
    ax.set_xlim(0, xmax.max() + 4)
    ax.grid(axis="x", color="#e6e5e0", lw=0.6)
    ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(LIMITE)
    ax.tick_params(colors=TEXTE_2, length=0)
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    ax.set_title("Âge des habitants : carreaux avec et sans kebab à Marseille",
                 loc="left", fontsize=11, fontweight="bold", pad=22)
    ax.text(0, 1.02, "Écart en points ; en gras : corrélation de Spearman significative "
            "après correction de Holm", transform=ax.transAxes, fontsize=8, color=TEXTE_2)
    fig.text(0.01, -0.02, SOURCE + " Carreaux habités non imputés.", fontsize=7, color=TEXTE_2)
    fig.savefig(FIGURES / "fig09_structure_ages.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("  -> figures/fig09_structure_ages.png")


# --- Programme principal ------------------------------------------------------------------------
def main():
    print("[08] Croisement kebabs x Insee")
    rng = np.random.default_rng(GRAINE)
    car = construire_indicateurs(gpd.read_file(DONNEES_TRAITEES / "carreaux_kebabs.gpkg"))
    car.to_file(DONNEES_TRAITEES / "carreaux_indicateurs.gpkg", driver="GPKG")

    col_imput = "i_est_200" if TAILLE_CARREAU == 200 else "i_est_1km"
    fiables = car[car["habite"] & (car[col_imput] == 0)]
    territoires = {"Métropole": fiables, "Marseille": fiables[fiables["commune"] == "Marseille"]}
    for t, d in territoires.items():
        print(f"  {t} : {len(d)} carreaux non imputés, {d['nb_kebabs'].sum()} kebabs "
              f"({d['presence_kebab'].sum()} carreaux avec kebab)")

    # H2 - Spearman + Holm (correction appliquée sur l'ensemble des tests)
    lignes = []
    for t, d in territoires.items():
        for v in INDICATEURS:
            rho, p, bas, haut, n = spearman_ic(d[v], d["nb_kebabs"])
            lignes.append({"territoire": t, "variable": v, "libelle": INDICATEURS[v],
                           "rho": rho, "ic_bas": bas, "ic_haut": haut, "p": p, "n": n})
    sp = pd.DataFrame(lignes)
    sp["p_holm"] = holm(sp["p"])

    # H2 - Spearman partiel à Marseille, à distance du Vieux-Port égale
    m = territoires["Marseille"]
    partiels = {v: correlation_partielle(m[v], m["nb_kebabs"], m["dist_vieux_port_m"])
                for v in INDICATEURS}
    sp["rho_partiel_centre"] = [partiels[v][0] if t == "Marseille" else np.nan
                                for t, v in zip(sp["territoire"], sp["variable"])]
    sp["p_partiel_centre"] = [partiels[v][1] if t == "Marseille" else np.nan
                              for t, v in zip(sp["territoire"], sp["variable"])]
    sp.to_csv(DONNEES_TRAITEES / "resultats_spearman.csv", index=False, encoding="utf-8")
    affiche = sp.assign(p_holm=sp["p_holm"].map(fmt_p))
    print(affiche[["territoire", "variable", "rho", "ic_bas", "ic_haut", "p_holm",
                   "rho_partiel_centre"]].round(3).to_string(index=False))

    # H2 - carreaux avec / sans kebab : médianes et Mann-Whitney
    tests = []
    for t, d in territoires.items():
        for v in INDICATEURS:
            avec, sans = d.loc[d["presence_kebab"] == 1, v].dropna(), d.loc[d["presence_kebab"] == 0, v].dropna()
            u, p = stats.mannwhitneyu(avec, sans)
            tests.append({"test": "Mann-Whitney avec/sans kebab", "territoire": t, "variable": v,
                          "mediane_avec": avec.median(), "mediane_sans": sans.median(), "p": p,
                          "taille_effet_r": 1 - 2 * u / (len(avec) * len(sans))})

    # H1 - regroupement des kebabs au-delà de la population (Marseille et métropole)
    k = pd.read_csv(DONNEES_TRAITEES / "kebabs.csv")
    k = gpd.GeoDataFrame(k, geometry=gpd.points_from_xy(k["lon"], k["lat"]), crs=CRS_GPS).to_crs(CRS_INSEE)
    habites = car[car["habite"]]
    for t, kk, cc in [("Métropole", k, habites),
                      ("Marseille", k[k["commune"] == "Marseille"], habites[habites["commune"] == "Marseille"])]:
        obs, sim, p = test_regroupement(np.column_stack([kk.geometry.x, kk.geometry.y]), cc, rng)
        tests.append({"test": "Regroupement (plus proche voisin vs population)", "territoire": t,
                      "variable": "distance moyenne au plus proche kebab (m)",
                      "observe": obs, "attendu_si_comme_population": sim, "p": p})
        print(f"  H1 {t} : distance moyenne au plus proche kebab {obs:.0f} m, "
              f"attendue si répartis comme la population {sim:.0f} m (p = {fmt_p(p)})")

    # H4 - Nord (13e-16e) / Sud et Est (7e-12e) de Marseille : test binomial exact
    st = pd.read_csv(DONNEES_TRAITEES / "stats_zones.csv")
    sm = st[st["est_marseille"]]
    groupes = {"Nord (13e-16e)": [13, 14, 15, 16], "Sud et Est (7e-12e)": [7, 8, 9, 10, 11, 12],
               "Centre (1er-6e)": [1, 2, 3, 4, 5, 6]}
    g = {n: sm[sm["arrondissement"].isin(a)][["nb_kebabs", "population"]].sum() for n, a in groupes.items()}
    for a, b in [("Nord (13e-16e)", "Sud et Est (7e-12e)"), ("Centre (1er-6e)", "Nord (13e-16e)")]:
        n_tot = g[a]["nb_kebabs"] + g[b]["nb_kebabs"]
        part_pop = g[a]["population"] / (g[a]["population"] + g[b]["population"])
        p = stats.binomtest(int(g[a]["nb_kebabs"]), int(n_tot), part_pop).pvalue
        taux = [g[x]["nb_kebabs"] / g[x]["population"] * 1e4 for x in (a, b)]
        tests.append({"test": "Binomial exact (taux par habitant)", "territoire": "Marseille",
                      "variable": f"{a} vs {b}", "observe": taux[0], "attendu_si_comme_population": taux[1],
                      "p": p})
        print(f"  H4 {a} {taux[0]:.2f} vs {b} {taux[1]:.2f} kebabs / 10 000 hab. (p = {fmt_p(p)})")

    res = pd.DataFrame(tests)
    res.to_csv(DONNEES_TRAITEES / "resultats_tests.csv", index=False, encoding="utf-8")
    mw = res[res["test"].str.startswith("Mann")]
    print(mw[["territoire", "variable", "mediane_avec", "mediane_sans", "p"]].round(3).to_string(index=False))

    # Figures
    figure_correlations(sp)
    zones = gpd.read_file(FICHIER_ZONES).to_crs(CRS_INSEE)
    figure_niveau_vie(territoires["Marseille"], k[k["commune"] == "Marseille"], zones)

    # Âges : analyse par tranche, carte des jeunes adultes, structure par âge
    ages = analyse_ages(territoires)
    print(ages[["territoire", "tranche", "part_carreaux_avec_kebab", "part_carreaux_sans_kebab",
                "ecart_points", "rho", "p_holm"]].round(3).to_string(index=False))
    figure_jeunes_adultes(territoires["Marseille"], k[k["commune"] == "Marseille"], zones)
    figure_structure_ages(ages)


if __name__ == "__main__":
    main()
