"""
00 - Lance toute la collecte de données, dans l'ordre.

Usage (depuis le dossier scripts/) :
    python 00_lancer_collecte.py

Les réponses brutes des API sont mises en cache dans donnees/brutes/ :
supprimer un fichier pour forcer sa re-collecte.
"""
import importlib
import time

ETAPES = [
    "01_collecte_limites",
    "02_collecte_kebabs_osm",
    "03_collecte_kebabs_sirene",
    "04_collecte_gares",
    "05_collecte_insee_carreaux",
]

if __name__ == "__main__":
    debut = time.time()
    for nom in ETAPES:
        importlib.import_module(nom).main()
        print()
    print(f"Collecte terminée en {time.time() - debut:.0f} s.")
