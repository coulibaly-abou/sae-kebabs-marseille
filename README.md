# Étude de l'implantation des kebabs dans l'agglomération marseillaise

SAÉ 5.EMS.01 : Mener une étude statistique dans un domaine d'application (BUT3 SD, 2026-2027).

> Comment expliquer la répartition spatiale des kebabs dans l'agglomération marseillaise,
> et cette répartition révèle-t-elle d'autres fractures socio-spatiales du territoire ?

**Périmètre :** Métropole d'Aix-Marseille-Provence (92 communes, ~1,9 M d'habitants).
Marseille est découpée en 16 arrondissements, soit 107 zones de travail (modifiable dans
`scripts/config.py`, variable `CODE_EPCI`).

## Organisation des dossiers

```
etude implantation des kebabs en marseille/
├── scripts/                 code Python (à lancer depuis ce dossier)
│   ├── config.py            chemins, périmètre, URLs des sources, mots-clés
│   ├── utils.py             fonctions partagées (Overpass, emprise, rattachement aux zones)
│   ├── 00_lancer_collecte.py  lance toute la collecte
│   ├── 01_collecte_limites.py       92 communes, 16 arrondissements, zones, périmètre
│   ├── 02_collecte_kebabs_osm.py    kebabs OpenStreetMap
│   ├── 03_collecte_kebabs_sirene.py kebabs base SIRENE (Insee)
│   ├── 04_collecte_gares.py         gares SNCF, métro, tram (OSM)
│   ├── 05_collecte_insee_carreaux.py  carreaux Insee Filosofi 200 m
│   ├── 06_nettoyage_kebabs.py       validation, dédoublonnage, fusion OSM + SIRENE
│   ├── 07_cartes_exploratoires.py   cartes (points, carroyage, chaleur, taux)
│   ├── 08_croisement_insee.py       indicateurs Insee, Spearman, tests H1 / H2 / H4
│   ├── 09_contributeurs_osm.py      historique des fiches kebabs OSM (qui les renseigne)
│   ├── 10_gares_isochrone.py        distance aux gares (H3), isochrones de Saint-Charles
│   ├── 11_modelisation.py           régression logistique, validation croisée
│   └── 99_apercu_rapport.py         aperçu HTML du rapport (images affichées)
├── donnees/
│   ├── brutes/              sorties de la collecte (non modifiées à la main)
│   └── traitees/            données nettoyées / fusionnées
└── rapport/
    ├── rapport.md           rapport (Markdown)
    └── figures/             cartes et graphiques
```

## Installation et exécution

```bash
pip install -r requirements.txt
cd scripts
python 00_lancer_collecte.py   # collecte (scripts 01 à 05)
python 06_nettoyage_kebabs.py  # nettoyage -> donnees/traitees/
python 07_cartes_exploratoires.py  # cartes -> rapport/figures/
python 08_croisement_insee.py      # tests statistiques -> donnees/traitees/
python 09_contributeurs_osm.py     # historique OSM
python 10_gares_isochrone.py       # gares et isochrones (service Valhalla, sans clé)
python 11_modelisation.py          # modèle explicatif
python 99_apercu_rapport.py        # aperçu lisible -> rapport/rapport_apercu.html
```

L'échelle de la grille (200 m ou 1 km) se règle avec `TAILLE_CARREAU` dans `config.py`.

Les réponses des API sont mises en cache dans `donnees/brutes/`. Pour relancer une collecte,
il suffit de supprimer le fichier concerné. Le zip Insee (~210 Mo) n'est pas versionné :
il est re-téléchargé automatiquement.

## Données collectées

| Fichier (`donnees/brutes/`) | Source | Contenu |
|---|---|---|
| `metropole_communes.geojson` | geo.api.gouv.fr | 92 communes + population, surface (ha) |
| `marseille_arrondissements.geojson` | geo.api.gouv.fr | 16 arrondissements + population |
| `zones.geojson` | construit (script 01) | 107 zones : 91 communes + 16 arrondissements |
| `perimetre.geojson` | construit (script 01) | contour global de la métropole |
| `kebabs_osm.csv` | OpenStreetMap (Overpass) | kebabs : nom, coordonnées, critère, commune, arrondissement |
| `kebabs_sirene.csv` | SIRENE (API Recherche d'entreprises) | établissements actifs : SIRET, enseigne, adresse, coordonnées, NAF, commune |
| `gares.csv` | OpenStreetMap (Overpass) | gares SNCF, métro, tram (+ quelques gares juste hors périmètre) |
| `insee_carreaux_200m_metropole.gpkg` | Insee Filosofi 2019 | population, âge, revenus, pauvreté, logement social (200 m), zone du carreau |

Toutes les tables de points ont les colonnes `code_zone`, `commune` et `arrondissement`
(rempli seulement pour Marseille) : on peut donc filtrer facilement sur Marseille seule.

## Données traitées

| Fichier (`donnees/traitees/`) | Contenu |
|---|---|
| `kebabs.csv` | **base finale** : 144 kebabs (OSM + SIRENE fusionnés), avec `fiabilite` (certain / probable), `source`, coordonnées, commune, arrondissement |
| `kebabs_exclus.csv` | faux positifs écartés et raison de l'exclusion |
| `carreaux_kebabs.gpkg` | carreaux de 200 m (ou 1 km selon `TAILLE_CARREAU` dans `config.py`) + `nb_kebabs` et `nb_kebabs_certains` (base des analyses statistiques) |
| `stats_zones.csv` | par commune / arrondissement : kebabs, population, kebabs pour 10 000 hab., par km² |
| `carreaux_indicateurs.gpkg` | carreaux + indicateurs (densité, niveau de vie, pauvreté, logement social, âges, distances gare / Vieux-Port) |
| `resultats_spearman.csv` | corrélations de Spearman (IC 95 %, p-valeurs corrigées Holm, corrélations partielles) |
| `resultats_tests.csv` | tests H1 (regroupement), H4 (Nord / Sud), Mann-Whitney avec / sans kebab |
| `resultats_ages.csv` | analyse par tranche d'âge : parts avec / sans kebab, Spearman, Holm |
| `kebabs_osm_meta.csv` | dernier contributeur, date de modification et nombre de versions des fiches OSM |
| `resultats_isochrone.csv` | kebabs et habitants à 5, 10, 15 min à pied de Saint-Charles |
| `resultats_gares.csv` | test H3 : distance des kebabs aux gares contre celle des habitants |
| `resultats_modele.csv` | odds ratios du modèle (et sensibilité aux seuls kebabs certains) |
| `resultats_validation.csv` | AUC, F1, précision, rappel en validation croisée |

## Figures (`rapport/figures/`)

| Fichier | Carte |
|---|---|
| `fig01_kebabs_metropole.png` | kebabs de la métropole |
| `fig02_kebabs_marseille.png` | kebabs de Marseille, encart sur l'hypercentre |
| `fig03_carroyage_marseille.png` | nombre de kebabs par carreau de 200 m |
| `fig04_chaleur_marseille.png` | carte de chaleur (densité lissée) |
| `fig05_kebabs_par_habitant.png` | kebabs pour 10 000 habitants (communes et arrondissements) |
| `fig06_niveau_vie_kebabs.png` | niveau de vie par carreau et kebabs (Marseille) |
| `fig07_correlations.png` | corrélations de Spearman (graphique à points et intervalles) |
| `fig08_jeunes_adultes_kebabs.png` | part des 18-39 ans par carreau et kebabs (Marseille) |
| `fig09_structure_ages.png` | structure par âge, carreaux avec / sans kebab |
| `fig10_isochrone_saint_charles.png` | isochrones à pied (5, 10, 15 min) autour de Saint-Charles |
| `fig11_gares_kebabs.png` | gares, stations et kebabs à Marseille |
| `fig12_effets_modele.png` | effets du modèle (odds ratios) |
