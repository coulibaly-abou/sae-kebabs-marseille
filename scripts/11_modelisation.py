"""
11 - Modélisation : qu'est-ce qui explique la présence d'un kebab dans un carreau ?

Modèle : régression logistique. Variable à expliquer : présence d'au moins un kebab
dans le carreau (oui / non). Variables explicatives (centrées-réduites, pour que les
effets soient comparables entre eux) :
    densité de population (log), niveau de vie moyen, part de logements sociaux,
    part des 25-39 ans, part des 65 ans et plus, distance à la station la plus
    proche (log), carreau situé à Marseille (oui / non).
Le taux de pauvreté n'est pas retenu : il est très lié au niveau de vie (rho = -0,69)
et les deux ensemble rendraient les effets difficiles à interpréter.

Effets : odds ratio pour une hausse d'un écart-type (statsmodels), avec IC à 95 %.
Évaluation : validation croisée stratifiée répétée (5 blocs x 10 répétitions) :
    AUC, et au seuil qui maximise le F1 sur l'échantillon d'apprentissage :
    précision, rappel, F1, matrice de confusion.
Comparaison avec un modèle « densité seule » pour mesurer l'apport des autres variables,
et analyse de sensibilité sur les seuls kebabs « certains ».

Sorties :
    donnees/traitees/resultats_modele.csv          odds ratios, IC, p-valeurs
    donnees/traitees/resultats_validation.csv      performances en validation croisée
    rapport/figures/fig12_effets_modele.png
"""
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_curve, roc_auc_score
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from config import DONNEES_TRAITEES, ECHELLE, FIGURES, TAILLE_CARREAU

VARIABLES = {
    "log_densite": "Densité de population",
    "niveau_vie_moyen": "Niveau de vie moyen",
    "part_logement_social": "Part de logements sociaux",
    "part_25_39": "Part des 25-39 ans",
    "part_65_plus": "Part des 65 ans et plus",
    "log_dist_station": "Distance à la station la plus proche",
    "marseille": "Carreau situé à Marseille",
}
GRAINE = 2026

FOND, TEXTE, TEXTE_2, LIMITE = "#fcfcfb", "#0b0b0b", "#52514e", "#a3a29c"
BLEU, GRIS_NS = "#2a78d6", "#a3a29c"
SOURCE = "Sources : OpenStreetMap, Insee (SIRENE, Filosofi 2019). Traitement : SAÉ kebabs."
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "text.color": TEXTE,
                     "figure.facecolor": FOND, "axes.facecolor": FOND, "savefig.facecolor": FOND})


def preparer() -> pd.DataFrame:
    c = gpd.read_file(DONNEES_TRAITEES / "carreaux_indicateurs.gpkg")
    col_imput = "i_est_200" if TAILLE_CARREAU == 200 else "i_est_1km"
    d = pd.DataFrame(c[c["habite"] & (c[col_imput] == 0)].drop(columns="geometry"))
    d["log_densite"] = np.log(d["densite_hab_km2"])
    d["log_dist_station"] = np.log(d["dist_gare_m"] + 50)  # +50 m : évite log(0) au pied d'une station
    d["part_25_39"] = d["ind_25_39"] / d["ind"]
    d["marseille"] = (d["commune"] == "Marseille").astype(int)
    d["presence_certain"] = (d["nb_kebabs_certains"] > 0).astype(int)
    return d.dropna(subset=list(VARIABLES))


def ajuster(d: pd.DataFrame, cible: str) -> pd.DataFrame:
    """Régression logistique sur variables centrées-réduites : odds ratios par écart-type."""
    X = d[list(VARIABLES)]
    Z = (X - X.mean()) / X.std()
    modele = sm.Logit(d[cible], sm.add_constant(Z)).fit(disp=False)
    ic = np.exp(modele.conf_int())
    res = pd.DataFrame({
        "variable": list(VARIABLES), "libelle": list(VARIABLES.values()),
        "odds_ratio": np.exp(modele.params[list(VARIABLES)]).values,
        "ic_bas": ic.loc[list(VARIABLES), 0].values, "ic_haut": ic.loc[list(VARIABLES), 1].values,
        "p": modele.pvalues[list(VARIABLES)].values,
        "ecart_type": X.std().values,
    })
    res.attrs["pseudo_r2"] = modele.prsquared
    res.attrs["n"] = int(modele.nobs)
    res.attrs["n_positifs"] = int(d[cible].sum())
    return res


def valider(d: pd.DataFrame, variables: list) -> dict:
    """Validation croisée : AUC + précision / rappel / F1 au seuil choisi sur l'apprentissage."""
    X, y = d[variables].values, d["presence_kebab"].values
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=GRAINE)
    aucs, f1s, mc = [], [], np.zeros((2, 2), dtype=int)
    for app, test in cv.split(X, y):
        modele = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
        modele.fit(X[app], y[app])
        # Seuil : celui qui maximise le F1 sur l'échantillon d'apprentissage
        prec, rapp, seuils = precision_recall_curve(y[app], modele.predict_proba(X[app])[:, 1])
        f1 = 2 * prec * rapp / np.maximum(prec + rapp, 1e-9)
        seuil = seuils[np.argmax(f1[:-1])]
        proba = modele.predict_proba(X[test])[:, 1]
        pred = (proba >= seuil).astype(int)
        aucs.append(roc_auc_score(y[test], proba))
        f1s.append(f1_score(y[test], pred))
        mc += confusion_matrix(y[test], pred, labels=[0, 1])
    mc = mc // 10  # moyenne sur les 10 répétitions : chaque carreau compté une fois
    vn, fp, fn, vp = mc.ravel()
    return {"auc_moyenne": np.mean(aucs), "auc_ecart_type": np.std(aucs),
            "f1_moyen": np.mean(f1s), "precision": vp / (vp + fp), "rappel": vp / (vp + fn),
            "vrais_positifs": vp, "faux_positifs": fp, "faux_negatifs": fn, "vrais_negatifs": vn}


def figure_effets(res: pd.DataFrame):
    r = res.iloc[::-1].reset_index(drop=True)
    y = np.arange(len(r))
    fig, ax = plt.subplots(figsize=(8, 4.3))
    for yi, l in r.iterrows():
        sig = l["p"] < 0.05
        coul = BLEU if sig else GRIS_NS
        ax.hlines(yi, l["ic_bas"], l["ic_haut"], color=coul, lw=2)
        ax.scatter(l["odds_ratio"], yi, s=45, color=coul, edgecolor=FOND, linewidth=1, zorder=3)
        txt = f"x {l['odds_ratio']:.2f}".replace(".", ",") + ("" if sig else " (ns)")
        ax.text(l["ic_haut"] * 1.06, yi, txt, va="center", fontsize=8, color=TEXTE if sig else TEXTE_2)
    ax.axvline(1, color=TEXTE_2, lw=0.8)
    ax.set_xscale("log")
    ticks = [0.25, 0.5, 1, 2, 4]
    ax.set_xticks(ticks, [f"{t:g}".replace(".", ",") for t in ticks])
    ax.set_xlim(0.2, max(6, r["ic_haut"].max() * 1.6))
    ax.set_yticks(y, r["libelle"], fontsize=8.5)
    ax.grid(axis="x", color="#e6e5e0", lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(LIMITE)
    ax.tick_params(colors=TEXTE_2, length=0)
    ax.set_xlabel("Effet sur les chances d'avoir un kebab (odds ratio, échelle logarithmique)",
                  color=TEXTE_2)
    ax.set_title("Ce qui explique la présence d'un kebab, toutes choses égales par ailleurs",
                 loc="left", fontsize=11, fontweight="bold", pad=22)
    ax.text(0, 1.02, f"Régression logistique, carreaux de {ECHELLE} ; effet d'une hausse d'un écart-type "
            "(x 2 = chances doublées) ; (ns) = non significatif", transform=ax.transAxes,
            fontsize=7.8, color=TEXTE_2)
    fig.text(0.01, -0.03, SOURCE + f" {res.attrs['n']:,} carreaux habités non imputés de la métropole."
             .replace(",", " "), fontsize=7, color=TEXTE_2)
    fig.savefig(FIGURES / "fig12_effets_modele.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("  -> figures/fig12_effets_modele.png")


def main():
    print("[11] Modélisation (régression logistique)")
    d = preparer()
    res = ajuster(d, "presence_kebab")
    print(f"  {res.attrs['n']} carreaux, {res.attrs['n_positifs']} avec kebab ; "
          f"pseudo-R² de McFadden = {res.attrs['pseudo_r2']:.3f}")
    print(res[["libelle", "odds_ratio", "ic_bas", "ic_haut", "p", "ecart_type"]].round(3).to_string(index=False))

    # Sensibilité : seuls les kebabs « certains »
    sens = ajuster(d, "presence_certain")
    res["odds_ratio_kebabs_certains"] = sens["odds_ratio"].values
    res["p_kebabs_certains"] = sens["p"].values
    res.to_csv(DONNEES_TRAITEES / "resultats_modele.csv", index=False, encoding="utf-8")
    print("  sensibilité (kebabs certains) :",
          dict(zip(sens["libelle"], sens["odds_ratio"].round(2))))

    # Validation croisée : modèle complet contre densité seule
    lignes = []
    for nom, variables in [("Modèle complet", list(VARIABLES)), ("Densité seule", ["log_densite"])]:
        v = valider(d, variables)
        lignes.append({"modele": nom, **v})
        print(f"  {nom} : AUC = {v['auc_moyenne']:.3f} (± {v['auc_ecart_type']:.3f}), "
              f"F1 = {v['f1_moyen']:.3f}, précision = {v['precision']:.2f}, rappel = {v['rappel']:.2f}, "
              f"VP {v['vrais_positifs']} FP {v['faux_positifs']} FN {v['faux_negatifs']} VN {v['vrais_negatifs']}")
    pd.DataFrame(lignes).to_csv(DONNEES_TRAITEES / "resultats_validation.csv", index=False, encoding="utf-8")

    figure_effets(res)


if __name__ == "__main__":
    main()
