"""
05 - Données socio-démographiques Insee carroyées à 200 m (Filosofi 2019).

Un carreau = un carré de 200 m x 200 m. Variables utiles (doc Insee) :
    ind        nombre d'individus           men_pauv  ménages pauvres
    men        nombre de ménages            ind_snv   somme des niveaux de vie
    log_soc    logements sociaux            ind_0_3 ... ind_80p : individus par âge
    men_prop   ménages propriétaires        men_coll  ménages en logement collectif

Étapes :
    1. téléchargement du zip Insee (~210 Mo, une seule fois)
    2. extraction du fichier France métropolitaine (.7z -> .gpkg, ~1,1 Go)
    3. lecture des seuls carreaux dans l'emprise de la métropole,
       puis garde des carreaux qui touchent le périmètre
    4. chaque carreau est rattaché à la zone (commune / arrondissement)
       qui contient son centre
    5. suppression des gros fichiers intermédiaires (on garde le zip)

Sortie :
    donnees/brutes/insee_carreaux_200m_metropole.gpkg
"""
import zipfile

import geopandas as gpd
import py7zr
import pyogrio
import requests

from config import CRS_INSEE, DONNEES_BRUTES, URL_FILOSOFI_200M
from utils import FICHIER_PERIMETRE, FICHIER_ZONES

ZIP = DONNEES_BRUTES / "Filosofi2019_carreaux_200m_gpkg.zip"
ARCHIVE_7Z = DONNEES_BRUTES / "Filosofi2019_carreaux_200m_gpkg.7z"
GPKG_FRANCE = DONNEES_BRUTES / "carreaux_200m_met.gpkg"
SORTIE = DONNEES_BRUTES / "insee_carreaux_200m_metropole.gpkg"


def telecharger():
    if ZIP.exists():
        print("  -> zip Insee déjà présent")
        return
    print("  -> téléchargement du zip Insee (~210 Mo, quelques minutes)...")
    with requests.get(URL_FILOSOFI_200M, stream=True, timeout=600,
                      headers={"User-Agent": "Mozilla/5.0"}) as r:
        r.raise_for_status()
        # On écrit dans un fichier temporaire, renommé seulement à la fin :
        # un téléchargement interrompu ne laisse pas un zip incomplet "valide".
        partiel = ZIP.with_suffix(".part")
        with open(partiel, "wb") as f:
            for bloc in r.iter_content(chunk_size=1 << 20):
                f.write(bloc)
        partiel.replace(ZIP)


def extraire():
    if GPKG_FRANCE.exists():
        return
    print("  -> extraction du fichier France métropolitaine (~1,1 Go)...")
    with zipfile.ZipFile(ZIP) as z:
        z.extract(ARCHIVE_7Z.name, DONNEES_BRUTES)
    with py7zr.SevenZipFile(ARCHIVE_7Z) as archive:
        archive.extract(path=DONNEES_BRUTES, targets=[GPKG_FRANCE.name])


def main():
    print("[05] Insee - carreaux Filosofi 200 m")
    if not SORTIE.exists():
        telecharger()
        extraire()

        # On lit la projection du fichier Insee pour exprimer l'emprise dans la même
        crs_fichier = pyogrio.read_info(GPKG_FRANCE)["crs"]
        perimetre = gpd.read_file(FICHIER_PERIMETRE).to_crs(crs_fichier)
        # Lecture filtrée par l'emprise : on ne charge pas toute la France en mémoire
        carreaux = gpd.read_file(GPKG_FRANCE, bbox=tuple(perimetre.total_bounds))
        carreaux = carreaux[carreaux.intersects(perimetre.geometry.iloc[0])].reset_index(drop=True)
        if carreaux.empty:
            raise RuntimeError("Aucun carreau trouvé : vérifier la projection / l'emprise.")

        # Zone du carreau = celle qui contient son centre (un carreau à cheval
        # sur la limite du périmètre peut avoir son centre dehors -> zone vide)
        zones = gpd.read_file(FICHIER_ZONES).to_crs(crs_fichier)[["code_zone", "commune", "geometry"]]
        centres = carreaux[[]].set_geometry(carreaux.centroid)
        centres = gpd.sjoin(centres, zones, how="left", predicate="within")
        centres = centres[~centres.index.duplicated()]
        carreaux[["code_zone", "commune"]] = centres[["code_zone", "commune"]]
        carreaux.to_crs(CRS_INSEE).to_file(SORTIE, driver="GPKG")

        # Ménage : les fichiers intermédiaires sont trop lourds pour être conservés
        ARCHIVE_7Z.unlink(missing_ok=True)
        GPKG_FRANCE.unlink(missing_ok=True)
    else:
        print("  -> fichier métropole déjà présent")

    carreaux = gpd.read_file(SORTIE)
    print(f"  -> {SORTIE.name} : {len(carreaux)} carreaux, "
          f"{carreaux['ind'].sum():,.0f} habitants")
    print(f"     dont Marseille : {(carreaux['commune'] == 'Marseille').sum()} carreaux, "
          f"{carreaux.loc[carreaux['commune'] == 'Marseille', 'ind'].sum():,.0f} habitants")
    print(f"     colonnes : {', '.join(carreaux.columns)}")


if __name__ == "__main__":
    main()
