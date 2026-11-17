"""
02 - Collecte des kebabs de l'agglomération depuis OpenStreetMap (API Overpass).

Critères retenus (documentés pour le rapport) :
    1. tag cuisine contenant kebab / doner / döner / shawarma
    2. OU fast-food / restaurant dont le NOM contient "kebab" ou "döner"
On garde uniquement les points situés dans le périmètre (métropole), avec leur
commune (et leur arrondissement pour Marseille).

Sorties :
    donnees/brutes/osm_kebabs_brut.json   réponse brute d'Overpass (cache)
    donnees/brutes/kebabs_osm.csv         une ligne par établissement
"""
import pandas as pd

from config import DONNEES_BRUTES
from utils import bbox_overpass, elements_osm_vers_lignes, rattacher_zone, requete_overpass

COLONNES = [
    "osm_id", "name", "lat", "lon", "amenity", "cuisine",
    "addr:housenumber", "addr:street", "addr:postcode", "addr:city",
    "opening_hours", "phone", "website", "ref:FR:SIRET",
    "critere", "code_zone", "commune", "arrondissement",
]


def main():
    print("[02] Kebabs - OpenStreetMap")
    bbox = bbox_overpass()
    requete = f"""
    [out:json][timeout:180];
    (
      nwr["cuisine"~"kebab|doner|döner|shawarma"]({bbox});
      nwr["amenity"~"^(fast_food|restaurant)$"]["name"~"[Kk][EeÉé][Bb][Aa][Bb]|[Dd][ÖöOo][Nn][Ee][Rr]"]({bbox});
    );
    out center;
    """
    data = requete_overpass(requete, DONNEES_BRUTES / "osm_kebabs_brut.json")
    df = pd.DataFrame(elements_osm_vers_lignes(data["elements"]))
    print(f"  éléments reçus (bbox) : {len(df)}")

    # Pourquoi l'établissement a été retenu (utile pour discuter des biais)
    cuisine = df.get("cuisine", pd.Series("", index=df.index)).fillna("").str.lower()
    tag_kebab = cuisine.str.contains("kebab|doner|döner|shawarma")
    df["critere"] = tag_kebab.map({True: "tag_cuisine", False: "nom"})

    # Filtre spatial : uniquement les points du périmètre, avec leur commune
    gdf = rattacher_zone(df)
    print(f"  dans le périmètre : {len(gdf)}")

    sortie = pd.DataFrame(gdf.drop(columns="geometry"))
    sortie = sortie[[c for c in COLONNES if c in sortie.columns]]
    sortie = sortie.sort_values(["commune", "arrondissement", "name"])
    sortie.to_csv(DONNEES_BRUTES / "kebabs_osm.csv", index=False, encoding="utf-8")
    print(f"  -> kebabs_osm.csv ({len(sortie)} lignes)")
    print(sortie["critere"].value_counts().to_string())
    print(f"  dont Marseille : {(sortie['commune'] == 'Marseille').sum()}")


if __name__ == "__main__":
    main()
