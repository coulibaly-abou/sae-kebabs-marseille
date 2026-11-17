"""
04 - Collecte des gares et stations de l'agglomération depuis OpenStreetMap.

On distingue 3 types (la définition de "gare" est un choix méthodologique
discuté dans le rapport) :
    - "train" : gares SNCF / TER (railway=station ou halt, hors métro)
    - "metro" : stations de métro (station=subway)
    - "tram"  : arrêts de tramway (railway=tram_stop) - Marseille et Aubagne

On garde aussi les stations juste en dehors du périmètre (bbox) : un kebab
au bord de la métropole peut avoir sa gare la plus proche à l'extérieur.

Sorties :
    donnees/brutes/osm_gares_brut.json   réponse brute d'Overpass (cache)
    donnees/brutes/gares.csv             une ligne par station
"""
import geopandas as gpd
import pandas as pd

from config import CRS_GPS, DONNEES_BRUTES
from utils import FICHIER_ZONES, bbox_overpass, elements_osm_vers_lignes, requete_overpass


def type_station(ligne) -> str:
    if ligne.get("railway") == "tram_stop":
        return "tram"
    if ligne.get("station") == "subway" or ligne.get("subway") == "yes":
        return "metro"
    return "train"


def main():
    print("[04] Gares et stations - OpenStreetMap")
    bbox = bbox_overpass(marge=0.03)  # ~3 km de marge autour du périmètre
    requete = f"""
    [out:json][timeout:180];
    (
      nwr["railway"~"^(station|halt)$"]({bbox});
      node["railway"="tram_stop"]({bbox});
    );
    out center;
    """
    data = requete_overpass(requete, DONNEES_BRUTES / "osm_gares_brut.json")
    df = pd.DataFrame(elements_osm_vers_lignes(data["elements"]))
    df = df[df["name"].notna()].copy()  # une station sans nom est inexploitable
    df["type"] = df.apply(type_station, axis=1)

    # Les arrêts de tram / stations ont souvent plusieurs points (un par quai) :
    # on fusionne les points de même nom et même type (coordonnées moyennes).
    df = (df.groupby(["name", "type"], as_index=False)
            .agg(lat=("lat", "mean"), lon=("lon", "mean"), operator=("operator", "first"),
                 nb_points_osm=("osm_id", "count")))

    # Commune de la station (vide si hors périmètre) et indicateur "dans le périmètre"
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=CRS_GPS)
    zones = gpd.read_file(FICHIER_ZONES)[["code_zone", "commune", "arrondissement", "geometry"]]
    gdf = gpd.sjoin(gdf, zones, how="left", predicate="within").drop(columns="index_right")
    gdf = gdf.drop_duplicates(["name", "type"])  # un point sur une frontière = 2 zones
    gdf["dans_perimetre"] = gdf["commune"].notna()

    sortie = pd.DataFrame(gdf.drop(columns="geometry"))
    sortie = sortie.sort_values(["type", "commune", "name"])
    sortie.to_csv(DONNEES_BRUTES / "gares.csv", index=False, encoding="utf-8")
    print(f"  -> gares.csv ({len(sortie)} stations)")
    print(pd.crosstab(sortie["type"], sortie["dans_perimetre"]).to_string())


if __name__ == "__main__":
    main()
