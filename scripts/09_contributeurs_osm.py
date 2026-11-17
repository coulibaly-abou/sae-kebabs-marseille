"""
09 - Qui renseigne les kebabs dans OpenStreetMap ?

OpenStreetMap est une carte collaborative : chaque objet garde la trace du dernier
contributeur qui l'a modifié, de la date de cette modification et de son numéro
de version (nombre de modifications). On récupère ces métadonnées pour les 85
kebabs OSM, afin de discuter la fiabilité et la fraîcheur de cette source.

Limite : l'API ne donne que le DERNIER contributeur de chaque objet, pas
l'historique complet (qui a créé l'objet, qui l'a corrigé ensuite...).

Sorties :
    donnees/brutes/osm_kebabs_meta_brut.json   réponse brute d'Overpass (cache)
    donnees/traitees/kebabs_osm_meta.csv       une ligne par kebab OSM
"""
import pandas as pd

from config import DONNEES_BRUTES, DONNEES_TRAITEES
from utils import requete_overpass


def main():
    print("[09] Contributeurs OpenStreetMap des kebabs")
    osm = pd.read_csv(DONNEES_BRUTES / "kebabs_osm.csv")
    types = osm["osm_id"].str.split("/").str[0]
    ids = osm["osm_id"].str.split("/").str[1]
    selection = "".join(f"{t}(id:{','.join(ids[types == t])});" for t in ("node", "way", "relation")
                        if (types == t).any())
    data = requete_overpass(f"[out:json][timeout:120];({selection});out meta;",
                            DONNEES_BRUTES / "osm_kebabs_meta_brut.json")

    meta = pd.DataFrame([{
        "osm_id": f"{e['type']}/{e['id']}",
        "dernier_contributeur": e.get("user"),
        "derniere_modification": e.get("timestamp"),
        "nb_versions": e.get("version"),
    } for e in data["elements"]])
    meta = osm[["osm_id", "name", "commune"]].merge(meta, on="osm_id", how="left")
    meta["derniere_modification"] = pd.to_datetime(meta["derniere_modification"])
    meta["annee_modification"] = meta["derniere_modification"].dt.year
    meta.to_csv(DONNEES_TRAITEES / "kebabs_osm_meta.csv", index=False, encoding="utf-8")

    # --- Bilan ---
    n = len(meta)
    contrib = meta["dernier_contributeur"].value_counts()
    print(f"  {n} kebabs OSM, {contrib.size} contributeurs différents (dernière modification)")
    print(f"  les 3 plus actifs : {contrib.head(3).to_dict()} "
          f"({contrib.head(3).sum() / n:.0%} des fiches)")
    print(f"  fiches jamais modifiées depuis leur création (version 1) : "
          f"{(meta['nb_versions'] == 1).sum()} ({(meta['nb_versions'] == 1).mean():.0%})")
    print(f"  versions : médiane {meta['nb_versions'].median():.0f}, max {meta['nb_versions'].max()}")
    print("  année de la dernière modification :")
    print(meta["annee_modification"].value_counts().sort_index().to_string())
    recentes = (meta["derniere_modification"] >= pd.Timestamp("2024-01-01", tz="UTC")).mean()
    print(f"  modifiées depuis 2024 : {recentes:.0%}")


if __name__ == "__main__":
    main()
