"""
03 - Collecte des kebabs de l'agglomération depuis la base SIRENE (Insee).

Source : API Recherche d'entreprises (https://recherche-entreprises.api.gouv.fr),
gratuite et sans clé. Elle renvoie les établissements avec adresse,
enseigne, code NAF, état (actif / fermé) et coordonnées GPS.

Protocole :
    - une recherche par mot-clé sur la métropole (filtre EPCI de l'API)
    - restreinte aux codes NAF de la restauration (56.10A et 56.10C)
    - on garde les établissements ACTIFS situés dans une commune du périmètre
      (une entreprise peut avoir des établissements ailleurs en France)
    - niveau "principal" (kebab, doner...) ou "secondaire" (istanbul, ankara...)

Limite connue : un kebab dont le nom ne contient aucun mot-clé
(ex. "Snack du Port") n'est pas trouvé -> complété par OSM (script 02).

Sortie :
    donnees/brutes/kebabs_sirene.csv   une ligne par établissement (SIRET unique)
"""
import time

import geopandas as gpd
import pandas as pd
import requests

from config import (API_ENTREPRISES, CODE_EPCI, CODES_NAF_RESTAURATION, DONNEES_BRUTES,
                    HEADERS, MOTS_CLES_KEBAB, MOTS_CLES_SECONDAIRES)
from utils import FICHIER_ZONES

PAUSE = 0.3  # l'API autorise ~7 requêtes / seconde


def rechercher(mot_cle: str) -> list[dict]:
    """Toutes les pages de résultats pour un mot-clé, sur toute la métropole."""
    resultats, page = [], 1
    while True:
        params = {
            "q": mot_cle,
            "epci": CODE_EPCI,
            "activite_principale": CODES_NAF_RESTAURATION,
            "per_page": 25,
            "page": page,
        }
        r = requests.get(API_ENTREPRISES, params=params, headers=HEADERS, timeout=60)
        if r.status_code == 429:  # trop de requêtes : on patiente
            time.sleep(2)
            continue
        r.raise_for_status()
        data = r.json()
        resultats.extend(data["results"])
        if page >= data["total_pages"]:
            return resultats
        page += 1
        time.sleep(PAUSE)


def etablissements(entreprise: dict, zones: dict) -> list[dict]:
    """Établissements actifs d'une entreprise situés dans le périmètre.

    `zones` : {code commune (ou arrondissement) -> (commune, arrondissement)}
    """
    lignes = []
    for etab in entreprise.get("matching_etablissements", []):
        code = etab.get("commune")
        if (etab.get("etat_administratif") != "A"
                or code not in zones
                or etab.get("activite_principale") not in CODES_NAF_RESTAURATION.split(",")):
            continue
        enseignes = etab.get("liste_enseignes") or []
        lignes.append({
            "siret": etab["siret"],
            "nom_entreprise": entreprise.get("nom_complet"),
            "enseigne": " / ".join(enseignes) if enseignes else None,
            "adresse": etab.get("adresse"),
            "code_postal": etab.get("code_postal"),
            "code_zone": code,
            "commune": zones[code][0],
            "arrondissement": zones[code][1],
            "lat": etab.get("latitude"),
            "lon": etab.get("longitude"),
            "naf": etab.get("activite_principale"),
            "date_creation": etab.get("date_creation"),
            "tranche_effectif": etab.get("tranche_effectif_salarie"),
        })
    return lignes


def main():
    print("[03] Kebabs - SIRENE (API Recherche d'entreprises)")
    z = gpd.read_file(FICHIER_ZONES)
    zones = {code: (commune, None if pd.isna(a) else int(a))
             for code, commune, a in zip(z["code_zone"], z["commune"], z["arrondissement"])}
    lignes = []
    for niveau, mots in [("principal", MOTS_CLES_KEBAB), ("secondaire", MOTS_CLES_SECONDAIRES)]:
        for mot in mots:
            trouves = [e for ent in rechercher(mot) for e in etablissements(ent, zones)]
            for e in trouves:
                e.update(mot_cle=mot, niveau=niveau)
            lignes.extend(trouves)
            print(f"  '{mot}' ({niveau}) : {len(trouves)} établissements actifs")
            time.sleep(PAUSE)

    df = pd.DataFrame(lignes)
    # Un même établissement peut sortir avec plusieurs mots-clés :
    # on garde le niveau le plus sûr ("principal" < "secondaire" en ordre alphabétique)
    mots = df.groupby("siret")["mot_cle"].apply(lambda s: ",".join(sorted(set(s))))
    df = (df.sort_values("niveau").drop_duplicates("siret")
            .drop(columns="mot_cle").merge(mots, on="siret"))

    # La recherche plein texte est "floue" : on note si un mot-clé apparaît
    # vraiment dans le nom ou l'enseigne (à vérifier lors du nettoyage).
    motif = "|".join(MOTS_CLES_KEBAB + MOTS_CLES_SECONDAIRES + ["kebap", "dürüm"])
    texte = (df["nom_entreprise"].fillna("") + " " + df["enseigne"].fillna("")).str.lower()
    df["mot_cle_dans_nom"] = texte.str.contains(motif)

    df["arrondissement"] = df["arrondissement"].astype("Int64")
    df = df.sort_values(["commune", "arrondissement", "nom_entreprise"])
    df.to_csv(DONNEES_BRUTES / "kebabs_sirene.csv", index=False, encoding="utf-8")
    print(f"  -> kebabs_sirene.csv ({len(df)} établissements actifs uniques)")
    print(df["niveau"].value_counts().to_string())
    print(f"     mot-clé absent du nom/enseigne (à vérifier) : {(~df['mot_cle_dans_nom']).sum()}")
    print(f"     sans coordonnées GPS : {df['lat'].isna().sum()}")
    print(f"     dont Marseille : {(df['commune'] == 'Marseille').sum()}")


if __name__ == "__main__":
    main()
