"""
Configuration commune à tous les scripts du projet.
Étude de l'implantation des kebabs dans l'agglomération marseillaise - SAE 5 EMS 01.
"""
from pathlib import Path

# --- Chemins -----------------------------------------------------------------
RACINE = Path(__file__).resolve().parent.parent
DONNEES_BRUTES = RACINE / "donnees" / "brutes"
DONNEES_TRAITEES = RACINE / "donnees" / "traitees"
FIGURES = RACINE / "rapport" / "figures"

for dossier in (DONNEES_BRUTES, DONNEES_TRAITEES, FIGURES):
    dossier.mkdir(parents=True, exist_ok=True)

# --- Périmètre d'étude -------------------------------------------------------
# Agglomération = Métropole d'Aix-Marseille-Provence (EPCI) : 92 communes,
# ~1,9 million d'habitants (Bouches-du-Rhône + Pertuis (84) + Saint-Zacharie (83)).
CODE_EPCI = "200054807"
NOM_PERIMETRE = "Métropole d'Aix-Marseille-Provence"
CODE_INSEE_MARSEILLE = "13055"   # commune de Marseille
CODE_DEPARTEMENT = "13"          # Bouches-du-Rhône
# Marseille est analysée via ses 16 arrondissements (codes 13201 -> 13216),
# plus fins que la commune (voir 01_collecte_limites.py).

# --- Échelle d'analyse -------------------------------------------------------
# Taille des carreaux de la grille statistique, en mètres : 200 (carreaux Insee
# d'origine) ou 1000 (carreaux de 1 km, sommes de 25 carreaux de 200 m).
# Relancer ensuite les scripts 07, 08 et suivants.
TAILLE_CARREAU = 200
ECHELLE = "200 m" if TAILLE_CARREAU == 200 else "1 km"

# --- Systèmes de coordonnées -------------------------------------------------
CRS_GPS = "EPSG:4326"       # latitude / longitude (WGS84)
CRS_METRIQUE = "EPSG:2154"  # Lambert 93 : distances en mètres (France)
CRS_INSEE = "EPSG:3035"     # projection des carreaux Insee (LAEA Europe)

# --- Sources -----------------------------------------------------------------
# API Overpass (OpenStreetMap). Plusieurs serveurs : si l'un est saturé on essaie le suivant.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Les requêtes Overpass se font sur l'emprise (bbox) du périmètre, calculée à
# partir des contours (voir utils.bbox_overpass) : plus légères que par "area".
# On filtre ensuite précisément avec les contours des communes.

# API Recherche d'entreprises (base SIRENE de l'Insee), gratuite, sans clé
API_ENTREPRISES = "https://recherche-entreprises.api.gouv.fr/search"
# Mots-clés recherchés dans le nom / l'enseigne des établissements.
#  - principaux : le nom désigne explicitement un kebab
#  - secondaires : nom à connotation turque / kebab, à valider au nettoyage
#    ("grill", "snack", "tacos" ont été testés puis écartés : trop de bruit)
MOTS_CLES_KEBAB = ["kebab", "doner", "döner", "durum"]
MOTS_CLES_SECONDAIRES = ["istanbul", "bosphore", "anatolie", "antalya", "ankara",
                         "izmir", "berliner", "shawarma"]
# Codes NAF : 56.10A restauration traditionnelle, 56.10C restauration rapide
CODES_NAF_RESTAURATION = "56.10A,56.10C"

# API Découpage administratif (geo.api.gouv.fr)
GEO_API = "https://geo.api.gouv.fr"

# Insee - Filosofi 2019, données carroyées à 200 m (France métropolitaine)
URL_FILOSOFI_200M = (
    "https://www.insee.fr/fr/statistiques/fichier/7655475/"
    "Filosofi2019_carreaux_200m_gpkg.zip"
)

# User-Agent poli pour les API publiques
HEADERS = {"User-Agent": "SAE-BUT3-SD-kebabs-marseille (projet etudiant)"}
