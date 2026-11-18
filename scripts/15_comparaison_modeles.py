"""
15 - Pourquoi la régression logistique ? Comparaison avec deux modèles plus souples,
et analyse des ratés du modèle retenu.

- Même protocole que le script 11 : validation croisée stratifiée 5 plis, répétée 10 fois,
  sur les 9 790 carreaux aux données réelles ; mêmes 7 variables.
- Modèles : régression logistique (retenue), forêt aléatoire, gradient boosting.
- Ratés : probabilités « hors échantillon » (chaque carreau est prédit par un modèle qui ne
  l'a pas vu). On liste les kebabs que le modèle n'attendait pas (faible probabilité).

Sorties : donnees/traitees/resultats_comparaison_modeles.csv, rates_modele.csv
"""
import importlib

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from config import DONNEES_TRAITEES

m11 = importlib.import_module("11_modelisation")
d = m11.preparer()
variables = list(m11.VARIABLES)
X, y = d[variables].values, d["presence_kebab"].values

MODELES = {
    "Régression logistique (retenue)": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
    "Forêt aléatoire": lambda: RandomForestClassifier(n_estimators=300, min_samples_leaf=5,
                                                      class_weight="balanced_subsample", n_jobs=-1,
                                                      random_state=m11.GRAINE),
    "Gradient boosting": lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300,
                                                                random_state=m11.GRAINE),
}
cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=m11.GRAINE)
lignes = []
for nom, fabrique in MODELES.items():
    aucs, aps = [], []
    for app, test in cv.split(X, y):
        modele = fabrique().fit(X[app], y[app])
        p = modele.predict_proba(X[test])[:, 1]
        aucs.append(roc_auc_score(y[test], p))
        aps.append(average_precision_score(y[test], p))
    lignes.append({"modele": nom, "auc_moyenne": np.mean(aucs), "auc_ecart_type": np.std(aucs),
                   "precision_moyenne_ap": np.mean(aps), "ap_ecart_type": np.std(aps)})
    print(f"{nom:35s} AUC {np.mean(aucs):.3f} ± {np.std(aucs):.3f}   AP {np.mean(aps):.3f}")
res = pd.DataFrame(lignes)
res["taux_base"] = y.mean()
res.to_csv(DONNEES_TRAITEES / "resultats_comparaison_modeles.csv", index=False)

# --- Ratés du modèle retenu (probabilités hors échantillon) -----------------------------------
oof = cross_val_predict(MODELES["Régression logistique (retenue)"](), X, y,
                        cv=StratifiedKFold(5, shuffle=True, random_state=m11.GRAINE), method="predict_proba")[:, 1]
d = d.assign(proba_hors_echantillon=oof)
rang = d["proba_hors_echantillon"].rank(ascending=False)
d["rang_sur_carreaux"] = rang.astype(int)
avec = d[d["presence_kebab"] == 1].sort_values("proba_hors_echantillon")
colonnes = ["idcar_200m", "commune", "code_zone", "nb_kebabs", "proba_hors_echantillon", "rang_sur_carreaux",
            "densite_hab_km2", "niveau_vie_moyen", "dist_gare_m", "part_25_39"]
avec[colonnes].to_csv(DONNEES_TRAITEES / "rates_modele.csv", index=False)
seuil = np.quantile(oof, 0.80)            # un carreau « attendu » est dans les 20 % les plus probables
print(f"kebabs dans les 20 % de carreaux les plus probables : {(avec['proba_hors_echantillon'] >= seuil).mean():.0%}")
print("kebabs les moins attendus :")
print(avec[colonnes].head(8).to_string(index=False))
