"""
Fonctions utilitaires partagées par les scripts de collecte.
"""
import json
import time

import geopandas as gpd
import requests

from config import CRS_GPS, DONNEES_BRUTES, HEADERS, OVERPASS_URLS

# Fichiers produits par 01_collecte_limites.py
FICHIER_PERIMETRE = DONNEES_BRUTES / "perimetre.geojson"
FICHIER_ZONES = DONNEES_BRUTES / "zones.geojson"


def bbox_overpass(marge: float = 0.01) -> str:
    """Emprise du périmètre au format Overpass "sud,ouest,nord,est" (en degrés).

    `marge` élargit un peu la boîte (0,01° ~ 1 km) pour ne rien couper au bord.
    """
    ouest, sud, est, nord = gpd.read_file(FICHIER_PERIMETRE).total_bounds
    return f"{sud - marge},{ouest - marge},{nord + marge},{est + marge}"


def rattacher_zone(df, colonne_lat: str = "lat", colonne_lon: str = "lon") -> gpd.GeoDataFrame:
    """Ajoute à chaque point sa zone (commune, ou arrondissement pour Marseille).

    Jointure spatiale avec zones.geojson ; les points hors périmètre sont retirés.
    Colonnes ajoutées : code_zone, commune, arrondissement.
    """
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[colonne_lon], df[colonne_lat]), crs=CRS_GPS)
    zones = gpd.read_file(FICHIER_ZONES)[["code_zone", "commune", "arrondissement", "geometry"]]
    return gpd.sjoin(gdf, zones, how="inner", predicate="within").drop(columns="index_right")


def requete_overpass(requete: str, fichier_cache=None) -> dict:
    """Envoie une requête Overpass QL et renvoie le JSON.

    - Si `fichier_cache` existe déjà, on le relit (pas de nouvel appel réseau).
    - Sinon on essaie chaque serveur Overpass jusqu'à ce que l'un réponde,
      puis on sauvegarde la réponse brute dans `fichier_cache`.
    """
    if fichier_cache is not None and fichier_cache.exists():
        print(f"  -> cache utilisé : {fichier_cache.name}")
        return json.loads(fichier_cache.read_text(encoding="utf-8"))

    for url in OVERPASS_URLS:
        for essai in range(1, 3):
            try:
                print(f"  -> requête Overpass ({url}, essai {essai})")
                r = requests.post(url, data={"data": requete}, headers=HEADERS, timeout=180)
                r.raise_for_status()
                resultat = r.json()
                if fichier_cache is not None:
                    fichier_cache.write_text(json.dumps(resultat, ensure_ascii=False), encoding="utf-8")
                return resultat
            except (requests.RequestException, ValueError) as e:
                print(f"     échec : {e}")
                time.sleep(5 * essai)
    raise RuntimeError("Aucun serveur Overpass n'a répondu. Réessayer plus tard.")


def elements_osm_vers_lignes(elements: list) -> list[dict]:
    """Transforme les éléments OSM (node / way / relation) en lignes simples.

    Pour les `way` et `relation` (bâtiments), Overpass renvoie un `center`
    grâce à `out center;` : on l'utilise comme coordonnée du point.
    """
    lignes = []
    for el in elements:
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            centre = el.get("center", {})
            lat, lon = centre.get("lat"), centre.get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        lignes.append({"osm_id": f"{el['type']}/{el['id']}", "lat": lat, "lon": lon, **tags})
    return lignes
