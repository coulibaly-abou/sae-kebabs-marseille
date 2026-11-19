"""
16 - Carte interactive 2D (version « à plat » du tableau de bord, sans toucher à la 3D).

Reprend les remarques faites en séance :
  - carte des kebabs dans le carroyage, avec une palette sans jaune pâle (illisible),
  - les points des kebabs par-dessus les carreaux,
  - les grandes rues (autoroutes, axes primaires et secondaires),
  - des isochrones à pied de 5, 10 et 15 minutes autour de plusieurs lieux
    (centre, gare, facs, parc des expositions...), et autour de n'importe quel
    point cliqué sur la carte.

Les isochrones sont calculées par nos soins sur le réseau piéton d'OpenStreetMap
(rues, trottoirs, escaliers, chemins), extrait de Marseille fourni par BBBike
(le service Valhalla utilisé au script 10 n'est pas joignable depuis tous les
réseaux). On marche à 5 km/h, deux fois moins vite dans les escaliers. Le calcul
est un plus court chemin (Dijkstra) : en Python pour le tableau des lieux, et
directement dans le navigateur pour le point cliqué.

Sortie : dashboard/kebabs_2d.html (fichier autonome, à partir du modèle
dashboard/modele_carte_2d.html).
"""
import json
import urllib.request

import geopandas as gpd
import numpy as np
import pandas as pd
import statsmodels.api as sm
from pyproj import Transformer
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from shapely.geometry import LineString

from config import CRS_GPS, CRS_METRIQUE, DONNEES_BRUTES, DONNEES_TRAITEES, RACINE

URL_BBBIKE = "https://download.bbbike.org/osm/bbbike/Marseille/Marseille.osm.shp.zip"
ZIP_OSM = DONNEES_BRUTES / "bbbike_marseille_shp.zip"
DOSSIER = RACINE / "dashboard"

VITESSE = 5000 / 3600            # m/s, marche « normale »
FACTEUR_ESCALIERS = 2.0          # un escalier se monte deux fois moins vite
MINUTES = [5, 10, 15]
TAMPON_M = 2000                  # le réseau couvre Marseille et 2 km autour

PIETON = {"footway", "residential", "path", "track", "tertiary", "steps", "secondary",
          "unclassified", "primary", "pedestrian", "cycleway", "living_street", "service",
          "tertiary_link", "secondary_link", "primary_link", "bridleway", "elevator",
          "corridor", "platform", "road"}
GRANDES_RUES = {"motorway": 0, "trunk": 0, "primary": 1, "secondary": 2}

# Lieux de comparaison (coordonnées des stations OSM, sinon entrée du site)
LIEUX = [
    ("Gare Saint-Charles", "gare", 5.3811927, 43.3032635),
    ("Vieux-Port", "centre", 5.3743186, 43.295543),
    ("Noailles / Canebière", "centre", 5.3811958, 43.2968497),
    ("Castellane", "centre", 5.3839803, 43.2858617),
    ("Joliette", "centre", 5.3678756, 43.3039964),
    ("Fac Saint-Charles", "fac", 5.3793, 43.3058),
    ("Fac de médecine, La Timone", "fac", 5.4004528, 43.2911917),
    ("Campus de Luminy", "fac", 5.4389, 43.2324),
    ("Campus de Saint-Jérôme", "fac", 5.4049, 43.3404),
    ("Parc Chanot (expositions)", "expo", 5.3934, 43.2700),
    ("Stade Vélodrome", "expo", 5.3958, 43.2698),
]


# Noms de quartiers affichés quand on zoome (position approximative du centre du quartier)
QUARTIERS = [("Le Panier", 5.3685, 43.2990), ("Belsunce", 5.3772, 43.2996), ("Noailles", 5.3822, 43.2963),
             ("Cours Julien", 5.3850, 43.2938), ("La Plaine", 5.3897, 43.2952), ("La Joliette", 5.3655, 43.3052),
             ("Castellane", 5.3840, 43.2858), ("Le Prado", 5.3925, 43.2712), ("Vieux-Port", 5.3718, 43.2948),
             ("Saint-Charles", 5.3810, 43.3045), ("La Timone", 5.4025, 43.2898), ("Notre-Dame-de-la-Garde", 5.3713, 43.2840),
             ("La Canebière", 5.3790, 43.2975), ("Euroméditerranée", 5.3680, 43.3110), ("Les Chartreux", 5.3990, 43.3070),
             ("Saint-Just", 5.4040, 43.3170), ("Malpassé", 5.4150, 43.3275), ("La Rose", 5.4260, 43.3340),
             ("Saint-Antoine", 5.3720, 43.3700), ("L'Estaque", 5.3200, 43.3620), ("Mazargues", 5.4040, 43.2470),
             ("Luminy", 5.4389, 43.2324), ("Saint-Loup", 5.4300, 43.2780), ("La Valentine", 5.4850, 43.2950)]


def r(x, n):
    return None if pd.isna(x) else round(float(x), n)


# --- 1. Réseau OSM --------------------------------------------------------------------------
def charger_routes() -> gpd.GeoDataFrame:
    if not ZIP_OSM.exists():
        print(f"  -> téléchargement de l'extrait OSM BBBike ({URL_BBBIKE})")
        req = urllib.request.Request(URL_BBBIKE, headers={"User-Agent": "SAE-BUT3-SD (projet etudiant)"})
        with urllib.request.urlopen(req, timeout=600) as rep:
            ZIP_OSM.write_bytes(rep.read())
    else:
        print(f"  -> cache utilisé : {ZIP_OSM.name}")
    routes = gpd.read_file(f"zip://{ZIP_OSM.as_posix()}!Marseille-shp/shape/roads.shp")
    return routes.explode(index_parts=False).reset_index(drop=True)


def grandes_rues(routes, emprise):
    g = routes[routes["type"].isin(GRANDES_RUES)].to_crs(CRS_METRIQUE)
    g = g[g.intersects(emprise)]
    g["geometry"] = g.geometry.simplify(8)
    g = g.to_crs(CRS_GPS)
    return [{"n": (l.name or l.ref or "") if isinstance(l.name, str) or isinstance(l.ref, str) else "",
             "c": GRANDES_RUES[l.type],
             "p": [[round(x, 5), round(y, 5)] for x, y in l.geometry.coords]}
            for l in g.itertuples()]


def graphe_pieton(routes, emprise):
    """Graphe contracté : on ne garde comme sommets que les carrefours et les impasses ;
    chaque arête est une suite de rues entre deux carrefours, avec son temps de marche."""
    p = routes[routes["type"].isin(PIETON)].to_crs(CRS_METRIQUE)
    p = p[p.intersects(emprise)]
    idx_de, voisins, cout_de = {}, [], []          # sommet -> liste de (voisin, coût, longueur)
    coords = []

    def sommet(x, y):
        k = (round(x, 2), round(y, 2))
        i = idx_de.get(k)
        if i is None:
            i = idx_de[k] = len(coords)
            coords.append(k)
            voisins.append({})
        return i

    for l in p.itertuples():
        pts = list(l.geometry.coords)
        facteur = FACTEUR_ESCALIERS if l.type == "steps" else 1.0
        prec = sommet(*pts[0][:2])
        for x, y, *_ in pts[1:]:
            cour = sommet(x, y)
            if cour != prec:
                (x0, y0), (x1, y1) = coords[prec], coords[cour]
                d = float(np.hypot(x1 - x0, y1 - y0))
                voisins[prec][cour] = (d * facteur, d)
                voisins[cour][prec] = (d * facteur, d)
            prec = cour

    # On ne garde que la plus grande composante connexe : sinon un quai de métro souterrain
    # ou un chemin isolé « capture » un lieu et l'isole du reste de la ville.
    from scipy.sparse.csgraph import connected_components
    lig = [i for i, v in enumerate(voisins) for _ in v]
    col = [j for v in voisins for j in v]
    ncomp, etiq = connected_components(csr_matrix((np.ones(len(lig)), (lig, col)),
                                                  shape=(len(coords), len(coords))), directed=False)
    principale = np.bincount(etiq).argmax()
    hors = set(np.flatnonzero(etiq != principale).tolist())
    for i in hors:
        voisins[i] = {}
    xy = np.array(coords)
    deg = np.array([len(v) for v in voisins])
    garde = (deg != 2) & (deg > 0)
    num = -np.ones(len(coords), dtype=int)
    num[garde] = np.arange(garde.sum())
    sur_arete = {}                                  # sommet de degré 2 -> (arête, coût depuis u)
    aretes, vus = [], set()
    for u in np.flatnonzero(garde):
        for v0 in voisins[u]:
            if (u, v0) in vus:
                continue
            chemin, cout, long_ = [u], 0.0, 0.0
            prec, cour = u, v0
            c, d = voisins[prec][cour]
            cout += c; long_ += d
            internes = []
            while not garde[cour]:
                chemin.append(cour)
                internes.append((cour, cout))
                suiv = next(w for w in voisins[cour] if w != prec)
                c, d = voisins[cour][suiv]
                cout += c; long_ += d
                prec, cour = cour, suiv
            chemin.append(cour)
            vus.add((cour, prec))                   # même arête parcourue dans l'autre sens
            if cour == u and len(chemin) <= 2:
                continue
            e = len(aretes)
            for s, c_s in internes:
                sur_arete[s] = (e, c_s / cout if cout else 0.0)
            aretes.append((u, cour, cout, chemin))
    print(f"  graphe piéton : {garde.sum()} carrefours, {len(aretes)} tronçons "
          f"({len(coords)} points avant contraction)")
    return xy, num, sur_arete, aretes


def encoder_graphe(xy, num, aretes):
    """Coordonnées en lon/lat x 1e5 (entiers), tronçons simplifiés à 5 m.
    Pour alléger le fichier, chaque coordonnée est donnée en écart à la précédente."""
    vers_gps = Transformer.from_crs(CRS_METRIQUE, CRS_GPS, always_xy=True)
    lon, lat = vers_gps.transform(xy[:, 0], xy[:, 1])
    E = []
    for u, v, cout, chemin in aretes:
        ligne = LineString(xy[chemin]).simplify(5)
        pts = list(ligne.coords)
        inter = []
        if len(pts) > 2:
            mx, my = vers_gps.transform([a for a, _ in pts], [b for _, b in pts])
            ix, iy = np.round(np.array(mx) * 1e5).astype(int), np.round(np.array(my) * 1e5).astype(int)
            for a in range(1, len(pts) - 1):                 # écart au point précédent
                inter += [int(ix[a] - ix[a - 1]), int(iy[a] - iy[a - 1])]
        E.append([int(num[u]), int(num[v]), round(cout / VITESSE, 1), inter])
    garde = num >= 0
    ix = np.round(lon[garde] * 1e5).astype(int)
    iy = np.round(lat[garde] * 1e5).astype(int)
    N = [int(ix[0]), int(iy[0])] + [int(v_) for pair in zip(np.diff(ix), np.diff(iy)) for v_ in pair]
    return N, E


def accrocher(xy, num, sur_arete, aretes, lon, lat):
    """Rattache des points (kebabs, carreaux, lieux) au réseau : sommet le plus proche,
    exprimé comme (arête, fraction du coût depuis u) + distance d'accès à pied."""
    vers_m = Transformer.from_crs(CRS_GPS, CRS_METRIQUE, always_xy=True)
    px, py = vers_m.transform(np.asarray(lon), np.asarray(lat))
    actifs = np.flatnonzero((num >= 0) | np.isin(np.arange(len(xy)), list(sur_arete)))
    d, j = cKDTree(xy[actifs]).query(np.c_[px, py])
    i = actifs[j]
    sortie = []
    for s, dist in zip(i, d):
        if num[s] >= 0:
            sortie.append([-1, int(num[s]), round(float(dist), 0)])    # directement un carrefour
        elif s in sur_arete:
            e, f = sur_arete[s]
            sortie.append([e, round(f, 4), round(float(dist), 0)])
        else:
            sortie.append([-2, 0, 0])                                  # hors réseau
    return sortie


def temps_points(t_noeuds, aretes_np, accroches):
    """Temps de marche (s) jusqu'à chaque point accroché, à partir des temps aux carrefours."""
    out = np.full(len(accroches), np.inf)
    for k, (e, f, dist) in enumerate(accroches):
        if e == -2:
            continue
        if e == -1:
            t = t_noeuds[int(f)]
        else:
            u, v, c = aretes_np[e]
            t = min(t_noeuds[int(u)] + f * c, t_noeuds[int(v)] + (1 - f) * c)
        out[k] = t + dist / VITESSE
    return out


# --- 2. Carreaux, modèle, kebabs -------------------------------------------------------------
def carreaux_et_modele():
    VARIABLES = ["log_densite", "niveau_vie_moyen", "part_logement_social", "part_25_39",
                 "part_65_plus", "log_dist_station", "marseille"]
    c = gpd.read_file(DONNEES_TRAITEES / "carreaux_indicateurs.gpkg")
    c = c[c["habite"] & (c["ind"] > 0)].copy()
    centres = c.geometry.centroid.to_crs(CRS_GPS)
    c["lon"], c["lat"] = centres.x, centres.y
    d = pd.DataFrame(c.drop(columns="geometry"))
    d["log_densite"] = np.log(d["densite_hab_km2"])
    d["log_dist_station"] = np.log(d["dist_gare_m"] + 50)
    d["part_25_39"] = d["ind_25_39"] / d["ind"]
    d["marseille"] = (d["commune"] == "Marseille").astype(int)
    app = d[d["i_est_200"] == 0].dropna(subset=VARIABLES)
    X = app[VARIABLES]
    Xs = sm.add_constant((X - X.mean()) / X.std())
    modele = sm.Logit(app["presence_kebab"], Xs).fit(disp=False)
    d["proba"] = np.nan
    d.loc[app.index, "proba"] = modele.predict(Xs)
    # angle des carreaux Insee (projection LAEA) une fois affichés en lon/lat
    g = c.geometry.iloc[0]
    (x0, y0), (x1, y1) = list(g.exterior.coords)[:2]
    a = gpd.GeoSeries.from_xy([x0, x1], [y0, y1], crs=c.crs).to_crs(CRS_METRIQUE)
    angle = float(np.degrees(np.arctan2(a.y.iloc[1] - a.y.iloc[0], a.x.iloc[1] - a.x.iloc[0])))
    return d, angle


def main():
    print("Carte 2D : réseau piéton, isochrones, carroyage")
    zones = gpd.read_file(DONNEES_BRUTES / "zones.geojson")
    marseille = zones[zones["est_marseille"]].to_crs(CRS_METRIQUE).union_all()
    emprise = marseille.buffer(TAMPON_M)

    routes = charger_routes()
    rues = grandes_rues(routes, emprise)
    xy, num, sur_arete, aretes = graphe_pieton(routes, emprise)
    N, E = encoder_graphe(xy, num, aretes)
    n_noeuds = int((num >= 0).sum())
    aretes_np = np.array([[e[0], e[1], e[2]] for e in E])
    # matrice des temps ; deux tronçons parallèles entre les mêmes carrefours : on garde le plus court
    paires = pd.DataFrame({"u": np.r_[aretes_np[:, 0], aretes_np[:, 1]].astype(int),
                           "v": np.r_[aretes_np[:, 1], aretes_np[:, 0]].astype(int),
                           "c": np.r_[aretes_np[:, 2], aretes_np[:, 2]]})
    paires = paires[paires["u"] != paires["v"]].groupby(["u", "v"], as_index=False)["c"].min()
    M = csr_matrix((np.maximum(paires["c"], 0.1), (paires["u"], paires["v"])), shape=(n_noeuds, n_noeuds))

    d, angle = carreaux_et_modele()
    k = pd.read_csv(DONNEES_TRAITEES / "kebabs.csv")
    g = pd.read_csv(DONNEES_BRUTES / "gares.csv")
    g = g[g["dans_perimetre"]]
    acc_k = accrocher(xy, num, sur_arete, aretes, k["lon"], k["lat"])
    dans_res = d["lon"].between(5.18, 5.62) & d["lat"].between(43.13, 43.45)
    acc_c = accrocher(xy, num, sur_arete, aretes, d.loc[dans_res, "lon"], d.loc[dans_res, "lat"])
    acc_c_tout = [[-2, 0, 0]] * len(d)
    for pos, a in zip(np.flatnonzero(dans_res.values), acc_c):
        acc_c_tout[pos] = a
    acc_s = accrocher(xy, num, sur_arete, aretes, g["lon"], g["lat"])

    # --- Lieux : temps de marche depuis chacun (Dijkstra) ---------------------------------
    acc_l = accrocher(xy, num, sur_arete, aretes, [l[2] for l in LIEUX], [l[3] for l in LIEUX])
    pop = d["ind"].values
    marseille_k = (k["commune"] == "Marseille").values
    lieux = []
    for (nom, cat, lon, lat), a in zip(LIEUX, acc_l):
        e, f, dist = a
        if e == -1:
            sources, depart = [int(f)], [dist / VITESSE]
        else:
            u, v, c = aretes_np[e]
            sources, depart = [int(u), int(v)], [f * c + dist / VITESSE, (1 - f) * c + dist / VITESSE]
        t = np.full(n_noeuds, np.inf)
        for s, t0 in zip(sources, depart):
            t = np.minimum(t, dijkstra(M, indices=s, limit=15 * 60 + 1) + t0)
        tk = temps_points(t, aretes_np, acc_k)
        tc = temps_points(t, aretes_np, acc_c_tout)
        ligne = {"nom": nom, "cat": cat, "lon": lon, "lat": lat, "acc": a}
        for m in MINUTES:
            ligne[f"k{m}"] = int((tk <= m * 60).sum())
            ligne[f"h{m}"] = int(pop[tc <= m * 60].sum())
        lieux.append(ligne)
        print(f"  {nom:<30} kebabs à 5/10/15 min : {ligne['k5']:>2} / {ligne['k10']:>2} / {ligne['k15']:>2}"
              f"   habitants à 15 min : {ligne['h15']:>6}")

    # --- Données injectées dans la page ------------------------------------------------------
    carreaux = [[r(l.lon, 5), r(l.lat, 5), int(l.ind), r(l.niveau_vie_moyen, -2), int(l.nb_kebabs),
                 r(l.proba, 3), r(l.dist_gare_m, -1), int(l.i_est_200), int(l.commune == "Marseille")]
                for l in d.itertuples()]
    kebabs = [{"lon": r(l.lon, 6), "lat": r(l.lat, 6), "nom": l.nom.title() if l.nom.isupper() else l.nom,
               "fiab": l.fiabilite, "src": l.source, "commune": l.commune,
               "arr": None if pd.isna(l.arrondissement) else int(l.arrondissement),
               "adr": "" if pd.isna(l.adresse) else str(l.adresse).title()} for l in k.itertuples()]
    stations = [{"lon": r(l.lon, 6), "lat": r(l.lat, 6), "nom": l.name, "type": l.type} for l in g.itertuples()]

    stats = pd.read_csv(DONNEES_TRAITEES / "stats_zones.csv", dtype={"code_zone": str})
    z = zones.merge(stats[["code_zone", "nb_kebabs", "kebabs_pour_10000_hab"]], on="code_zone", how="left")
    z["geometry"] = z.to_crs(CRS_METRIQUE).geometry.simplify(40).to_crs(CRS_GPS)
    zj = json.loads(z[["nom_zone", "est_marseille", "population", "nb_kebabs", "kebabs_pour_10000_hab",
                       "geometry"]].to_json(drop_id=True))
    for f in zj["features"]:
        f["properties"]["nom_zone"] = f["properties"]["nom_zone"].replace(" Arrondissement", "")
        f["geometry"]["coordinates"] = json.loads(json.dumps(f["geometry"]["coordinates"]),
                                                  parse_float=lambda x: round(float(x), 5))

    etiquettes = []
    for l in zones.itertuples():
        p = l.geometry.representative_point()
        if l.est_marseille:
            n = int(l.arrondissement)
            etiquettes.append({"t": "1er" if n == 1 else f"{n}e", "lon": round(p.x, 5), "lat": round(p.y, 5), "k": "arr"})
        else:
            etiquettes.append({"t": l.nom_zone, "lon": round(p.x, 5), "lat": round(p.y, 5), "k": "commune"})
    etiquettes += [{"t": n, "lon": x, "lat": y, "k": "quartier"} for n, x, y in QUARTIERS]

    donnees = {"carreaux": carreaux, "etiquettes": etiquettes, "angle": round(angle, 2), "kebabs": kebabs, "stations": stations,
               "zones": zj, "rues": rues, "lieux": lieux,
               "graphe": {"N": N, "E": E, "vitesse": VITESSE},
               "acc": {"k": acc_k, "c": acc_c_tout, "s": acc_s}}
    texte = json.dumps(donnees, ensure_ascii=False, separators=(",", ":"))
    modele_html = (DOSSIER / "modele_carte_2d.html").read_text(encoding="utf-8")
    (DOSSIER / "kebabs_2d.html").write_text(modele_html.replace("/*__DONNEES__*/null", texte), encoding="utf-8")
    pd.DataFrame(lieux).drop(columns="acc").to_csv(DONNEES_TRAITEES / "resultats_isochrones_lieux.csv", index=False)
    print(f"dashboard/kebabs_2d.html écrit ({len(texte) / 1e6:.1f} Mo de données)")


if __name__ == "__main__":
    main()
