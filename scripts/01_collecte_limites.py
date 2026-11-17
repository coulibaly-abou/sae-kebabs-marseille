"""
01 - Collecte des limites administratives de l'agglomération marseillaise.

Périmètre : Métropole d'Aix-Marseille-Provence (92 communes, voir config.py).
Source : API Découpage administratif (https://geo.api.gouv.fr), données IGN/Insee.

Sorties :
    donnees/brutes/metropole_communes.geojson        les 92 communes (+ population, surface)
    donnees/brutes/marseille_arrondissements.geojson les 16 arrondissements de Marseille
    donnees/brutes/zones.geojson     découpage de travail : les 91 autres communes
                                     + les 16 arrondissements de Marseille (107 zones)
    donnees/brutes/perimetre.geojson contour global de la métropole
"""
import geopandas as gpd
import pandas as pd
import requests

from config import (CODE_DEPARTEMENT, CODE_EPCI, CODE_INSEE_MARSEILLE, CRS_GPS,
                    DONNEES_BRUTES, GEO_API, HEADERS, NOM_PERIMETRE)
from utils import FICHIER_PERIMETRE, FICHIER_ZONES

CHAMPS = "nom,code,population,surface"  # surface en hectares


def telecharger_geojson(url: str, params: dict) -> gpd.GeoDataFrame:
    r = requests.get(url, params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    data = r.json()
    # Une seule commune -> "Feature" ; une liste -> "FeatureCollection"
    features = data["features"] if data.get("type") == "FeatureCollection" else [data]
    return gpd.GeoDataFrame.from_features(features, crs=CRS_GPS)


def main():
    print(f"[01] Limites administratives - {NOM_PERIMETRE}")

    # Les communes de la métropole
    communes = telecharger_geojson(
        f"{GEO_API}/epcis/{CODE_EPCI}/communes",
        {"format": "geojson", "geometry": "contour", "fields": CHAMPS},
    ).sort_values("code").reset_index(drop=True)
    communes.to_file(DONNEES_BRUTES / "metropole_communes.geojson", driver="GeoJSON")
    print(f"  communes : {len(communes)} ({communes['population'].sum():,} hab.)")

    # Arrondissements municipaux de Marseille (codes 13201 à 13216)
    arr = telecharger_geojson(
        f"{GEO_API}/communes",
        {"codeDepartement": CODE_DEPARTEMENT, "type": "arrondissement-municipal",
         "format": "geojson", "geometry": "contour", "fields": CHAMPS},
    )
    arr = arr[arr["code"].str.startswith("132")].sort_values("code").reset_index(drop=True)
    arr["arrondissement"] = arr["code"].str[-2:].astype(int)  # 1 à 16
    arr.to_file(DONNEES_BRUTES / "marseille_arrondissements.geojson", driver="GeoJSON")
    print(f"  arrondissements de Marseille : {len(arr)} ({arr['population'].sum():,} hab.)")

    # Découpage de travail : Marseille est remplacée par ses 16 arrondissements
    autres = communes[communes["code"] != CODE_INSEE_MARSEILLE].assign(
        commune=lambda d: d["nom"], arrondissement=pd.NA)
    arr_zones = arr.assign(commune="Marseille")
    zones = pd.concat([arr_zones, autres], ignore_index=True)
    zones = zones.rename(columns={"code": "code_zone", "nom": "nom_zone"})
    zones["est_marseille"] = zones["commune"] == "Marseille"
    zones["arrondissement"] = zones["arrondissement"].astype("Int64")
    zones = gpd.GeoDataFrame(
        zones[["code_zone", "nom_zone", "commune", "arrondissement", "est_marseille",
               "population", "surface", "geometry"]], crs=CRS_GPS)
    zones.to_file(FICHIER_ZONES, driver="GeoJSON")
    print(f"  zones de travail : {len(zones)}")

    # Contour global (sert à calculer l'emprise des requêtes OpenStreetMap)
    perimetre = gpd.GeoDataFrame({"nom": [NOM_PERIMETRE]},
                                 geometry=[communes.union_all()], crs=CRS_GPS)
    perimetre.to_file(FICHIER_PERIMETRE, driver="GeoJSON")


if __name__ == "__main__":
    main()
