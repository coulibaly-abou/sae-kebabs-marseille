# Guide du projet : les kebabs de l'agglomération marseillaise

Ce guide sert à trois choses : retrouver vite chaque livrable, utiliser la scène 3D pendant la
soutenance, et répondre aux questions du jury. Il complète le [README](README.md), qui décrit
les fichiers un par un.

## 1. Les liens à avoir sous la main

| Quoi | Où |
|---|---|
| Rapport (PDF à rendre) | [`rapport/AMAVIGAN_COULIBALY_rapport_SAE5EMS01.pdf`](rapport/AMAVIGAN_COULIBALY_rapport_SAE5EMS01.pdf) |
| Rapport Word (modifiable) | [`rapport/AMAVIGAN_COULIBALY_rapport_SAE5EMS01.docx`](rapport/AMAVIGAN_COULIBALY_rapport_SAE5EMS01.docx) |
| Source Quarto du rapport | [`rapport/AMAVIGAN_COULIBALY_rapport_SAE5EMS01.qmd`](rapport/AMAVIGAN_COULIBALY_rapport_SAE5EMS01.qmd) |
| Lien du tableau de bord (fichier .txt demandé) | [`rapport/AMAVIGAN_COULIBALY_dashboard_SAE5EMS01.txt`](rapport/AMAVIGAN_COULIBALY_dashboard_SAE5EMS01.txt) |
| Scène 3D en ligne | https://coulibaly-abou.github.io/sae-kebabs-marseille/dashboard/kebabs_3d.html |
| Carte 2D interactive (carroyage, grandes rues, isochrones au clic) | https://coulibaly-abou.github.io/sae-kebabs-marseille/dashboard/kebabs_2d.html |
| Scène 3D hors ligne | `dashboard/kebabs_3d.html` : double-clic, elle s'ouvre dans le navigateur |
| Dépôt complet | https://github.com/coulibaly-abou/sae-kebabs-marseille |

Conseil pour la soutenance : ouvrez la scène 3D **avant** de commencer, dans Chrome ou Edge,
et gardez la version hors ligne en secours si le Wi-Fi de la salle est mauvais.

## 2. Se servir de la scène 3D

**Commandes.** Glisser avec la souris pour déplacer la carte ; molette pour zoomer ;
Ctrl + glisser (ou clic droit + glisser) pour faire pivoter et incliner. Les flèches ← et →
du clavier passent d'une étape à l'autre. Survoler un objet affiche ses informations.

**La console de droite.** Le bouton « Habitants / Modèle » change ce que représente la hauteur
des carreaux. Les cases à cocher affichent ou masquent chaque couche. « Tourner » lance une
rotation lente, « Vue globale » revient sur toute la métropole.

**Les huit étapes, et ce qu'on peut dire à chacune :**

| Étape | Ce qu'on voit | Le message |
|---|---|---|
| 1. Une métropole, 144 kebabs | Toute la métropole en relief | Le relief suit la population, les kebabs non : 95 sur 144 sont à Marseille. |
| 2. La fracture Nord-Sud | Marseille, tours roses au nord, bleues au sud | 2,2 kebabs pour 10 000 habitants au centre, 0,9 au Nord, 0,45 au Sud. |
| 3. L'hypercentre | Belsunce, Noailles, la Canebière | Le 1er arrondissement : 23 kebabs, le taux le plus élevé de la métropole. |
| 4. Saint-Charles | Isochrones de 5, 10 et 15 min | 25 kebabs sur 95 à moins de 15 min à pied, pour 7 % des habitants. |
| 5. L'isochrone en mouvement | 57 piétons sortent de la gare, les rames circulent | Presque rien avant 5 min (la gare est sur une butte), puis les kebabs s'allument entre 10 et 15 min. |
| 6. Le fil des stations | Arcs kebab → station la plus proche | Distance médiane : 327 m ; 60 % des kebabs à moins de 500 m d'une station. |
| 7. Simulation | Bouton « Placer les kebabs comme la population » | Sur 1 000 tirages au hasard, aucun ne place les kebabs aussi près des stations (327 m contre 960 à 1 870 m). |
| 8. Le modèle | Relief = probabilité, anneaux verts et rouges | AUC 0,93 ; bat la forêt aléatoire et le gradient boosting ; ratés en bord de mer et en zone commerciale. |

L'étape 7 est la plus parlante à l'oral : cliquez sur le bouton, laissez les kebabs se
disperser, commentez l'histogramme, puis cliquez sur « Revenir aux vrais kebabs ».

## 3. Les chiffres à connaître par cœur

- **144 kebabs** dans la base (92 certains, 52 probables), dont **95 à Marseille** ; les deux
  sources n'en ont que **14 en commun**, ce qui suggère qu'on en a trouvé environ **un tiers**
  (capture-recapture : environ 440).
- **9 790 carreaux de 200 m** aux données réelles, dont **110 avec un kebab**.
- Distance moyenne au kebab le plus proche : **812 m**, contre **1 572 m** si les kebabs
  suivaient la population (p = 0,001).
- À Marseille, **78 %** des kebabs sont à moins de 500 m d'une station, contre **39 %** des
  habitants.
- Carreaux avec kebab contre carreaux sans kebab : niveau de vie médian **19 400 €** contre
  **24 500 €**, densité **16 600** contre **4 500 hab./km²**.
- Ce sont les **25-39 ans** qui comptent, pas les 18-24 ans.
- Modèle : niveau de vie **× 0,27** par écart-type, densité **× 2,3**, distance à la station
  **× 0,44**. AUC **0,932** (forêt aléatoire 0,916, gradient boosting 0,914).

## 4. Plan de soutenance proposé (10 à 12 minutes)

1. **La question** (1 min) : la vidéo des Échos sur Paris, le dicton de la gare, notre
   problématique et nos cinq hypothèses.
2. **L'article de référence** (1 min) : Pearce et al. (2007), la figure 1 et ce que nous en
   avons retenu.
3. **Les données** (2 min) : pas de liste officielle, donc OpenStreetMap + SIRENE ; le
   nettoyage ; les limites (capture-recapture, contributeurs OSM, secret statistique).
4. **La démonstration 3D** (4 min) : étapes 2, 3, 5 et 7 en direct.
5. **Le modèle** (2 min) : les effets, la comparaison avec les deux autres modèles, les ratés.
6. **Conclusion et limites** (1 min) : la carte des kebabs comme portrait social de Marseille ;
   ce qu'on ferait avec plus de temps.

## 5. Questions probables du jury, et nos réponses

**Pourquoi des carreaux de 200 m et pas les arrondissements ?** C'est l'échelle la plus fine
diffusée par l'Insee : elle sépare une rue commerçante du quartier résidentiel voisin. Nous
avons refait les calculs avec des carreaux de 1 km : mêmes conclusions.

**Votre base est incomplète, vos résultats tiennent-ils ?** Elle couvre environ un tiers des
kebabs. Mais les tests portent sur la répartition, pas sur le total, et les effets du modèle
restent les mêmes quand on ne garde que les 92 kebabs certains.

**Pourquoi Spearman et pas Pearson ?** Le nombre de kebabs par carreau vaut presque toujours
0 : la distribution est très déséquilibrée. Spearman travaille sur les rangs et supporte ces
données.

**Pourquoi avoir écarté 62 % des carreaux ?** Pour ces carreaux, l'Insee remplace les valeurs
réelles par des estimations (secret statistique). Ils ne contiennent que 7 kebabs sur 141.

**Pourquoi une régression logistique ?** Elle se lit facilement (chaque effet est un
multiplicateur de chances), et elle est aussi la plus performante : AUC 0,932, contre 0,916 et
0,914 pour la forêt aléatoire et le gradient boosting. Avec 110 carreaux positifs, les modèles
plus souples apprennent du bruit.

**Le F1-score est faible (0,22), le modèle est-il mauvais ?** Non : à peine plus d'un carreau
sur cent a un kebab, ce qui rend toute prédiction exacte très difficile, et beaucoup de
« fausses alertes » sont sans doute de vrais kebabs absents de notre base. L'AUC montre que
le modèle classe très bien les carreaux.

**Où le modèle se trompe-t-il ?** Sur des kebabs en bord de mer (Ensuès, La Ciotat, sud du
8e) ou en zone commerciale (Vitrolles) : leur clientèle vient d'ailleurs, et nos données ne
décrivent que les habitants.

**Les kebabs s'installent-ils parce que les gens sont pauvres ?** Nous mesurons une
association, pas une cause. Loyers commerciaux plus bas, clientèle de passage, habitudes de
consommation : plusieurs explications restent possibles.

**Le dicton de la gare est-il vrai ?** Nos données ne le disent pas : il faudrait les notes
Google, payantes. Le protocole est prêt (section 5.7). À Paris, une analyse de 400 kebabs
trouve une corrélation de seulement 0,09 entre note et distance à la gare.

**Comment avez-vous fait les isochrones ?** Avec le service libre Valhalla, qui calcule les
temps de marche sur le vrai réseau de rues et d'escaliers d'OpenStreetMap. Les trajets des
piétons de la scène 3D viennent du même service.

## 6. Tout relancer

```bash
pip install -r requirements.txt
cd scripts
python 00_lancer_collecte.py       # collecte (OSM, SIRENE, Insee, gares) : réponses mises en cache
python 06_nettoyage_kebabs.py      # base finale des 144 kebabs
python 07_cartes_exploratoires.py  # cartes de la partie 4
python 08_croisement_insee.py      # tests de la partie 5
python 09_contributeurs_osm.py     # historique des fiches OSM
python 10_gares_isochrone.py       # gares et isochrones
python 11_modelisation.py          # régression logistique
python 14_collecte_mouvement.py    # tracés métro / tram, trajets à pied (scène animée)
python 15_comparaison_modeles.py   # forêt aléatoire, gradient boosting, ratés du modèle
python 12_scene_3d.py              # scène 3D -> dashboard/kebabs_3d.html
python 16_carte_2d.py              # carte 2D + isochrones -> dashboard/kebabs_2d.html
python 13_figures_rapport.py       # figure de l'article, Gantt, captures de la scène
python 98_livrables.py             # rapport .qmd, .docx (Pandoc) et PDF (Word)
```

La première collecte prend quelques minutes (serveurs publics). Les suivantes relisent le
cache de `donnees/brutes/` et sont presque instantanées. Le script 13 utilise Chrome (Selenium) pour les captures ; le script 98 utilise Pandoc
(paquet pypandoc_binary) pour le .docx et Microsoft Word pour le sommaire et le PDF.

Pour modifier le texte du rapport : éditer `rapport/rapport.md`, puis relancer
`python 98_livrables.py`. Pour modifier la scène 3D : éditer `dashboard/modele_scene.html`
(mise en page et récit), puis relancer `python 12_scene_3d.py`.

## 7. Mettre à jour le dépôt GitHub

```bash
git add -A
git commit -m "Ce qui a changé"
git push
```

La scène 3D en ligne se met à jour toute seule une minute environ après le `push`
(GitHub Pages).
