"""
14 - Données de mouvement pour la scène 3D animée.

- Tracés des lignes de métro et de tramway de Marseille (OpenStreetMap, relations
  route=subway / route=tram), pour faire rouler les rames dans la scène.
- Trajets à pied réels entre la gare Saint-Charles et chaque kebab situé à moins de
  2,5 km (service libre Valhalla, profil piéton), pour animer les piétons qui sortent
  de la gare. Leur durée réelle de marche est conservée.

Les réponses sont mises en cache dans donnees/brutes/ : supprimer un fichier pour le recollecter.
"""
import json
import time

import numpy as np
import pandas as pd
import requests

from config import DONNEES_BRUTES, DONNEES_TRAITEES, HEADERS
from utils import requete_overpass

VALHALLA_ROUTE = "https://valhalla1.openstreetmap.de/route"
GARE = (43.3032635, 5.3811927)          # gare Saint-Charles (gares.csv)
RAYON_M = 2500
R_TERRE = 6_371_000


def distance_m(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * R_TERRE * np.arcsin(np.sqrt(a))


# --- 1. Lignes de métro et de tram ------------------------------------------------------
requete = """
[out:json][timeout:120];
relation["type"="route"]["route"~"^(subway|tram)$"](43.20,5.30,43.42,5.56);
out geom;
"""
osm = requete_overpass(requete, DONNEES_BRUTES / "osm_lignes_metro_tram.json")


def assembler(ways):
    """Recolle les tronçons d'une relation en un seul tracé (orientation la plus proche)."""
    morceaux = [[(p["lon"], p["lat"]) for p in w["geometry"]] for w in ways if w.get("geometry")]
    if not morceaux:
        return []
    trace = list(morceaux[0])
    for m in morceaux[1:]:
        fin = trace[-1]
        d_debut = abs(m[0][0] - fin[0]) + abs(m[0][1] - fin[1])
        d_fin = abs(m[-1][0] - fin[0]) + abs(m[-1][1] - fin[1])
        if len(trace) == len(morceaux[0]) and min(d_debut, d_fin) > 2e-3:   # 1er tronçon à l'envers
            debut = trace[0]
            if abs(m[0][0] - debut[0]) + abs(m[0][1] - debut[1]) < d_debut:
                trace.reverse()
                fin = trace[-1]
                d_debut = abs(m[0][0] - fin[0]) + abs(m[0][1] - fin[1])
                d_fin = abs(m[-1][0] - fin[0]) + abs(m[-1][1] - fin[1])
        trace.extend(m if d_debut <= d_fin else m[::-1])
    return trace


lignes, vues = [], set()
for rel in osm["elements"]:
    tags = rel.get("tags", {})
    ref = tags.get("ref", "?")
    if tags.get("network") != "RTM":      # réseau marseillais seulement (pas le tram d'Aubagne)
        continue
    if ref in vues:                       # une seule direction par ligne suffit
        continue
    ways = [m for m in rel.get("members", []) if m["type"] == "way" and m.get("role", "") in ("", "forward", "backward")]
    trace = assembler(ways)
    if len(trace) < 10:
        continue
    vues.add(ref)
    lignes.append({"ref": ref, "type": tags["route"], "nom": tags.get("name", ref),
                   "couleur": tags.get("colour"), "trace": [[round(x, 6), round(y, 6)] for x, y in trace]})
print("lignes :", [(l["type"], l["ref"], len(l["trace"])) for l in lignes])
(DONNEES_TRAITEES / "lignes_metro_tram.json").write_text(json.dumps(lignes, ensure_ascii=False), encoding="utf-8")

# --- 2. Trajets à pied gare -> kebabs -------------------------------------------------------
cache = DONNEES_BRUTES / "trajets_pietons_saint_charles.json"
trajets = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
k = pd.read_csv(DONNEES_TRAITEES / "kebabs.csv")
k["d"] = distance_m(GARE[0], GARE[1], k["lat"], k["lon"])
proches = k[k["d"] <= RAYON_M]


def decoder(polyline, precision=6):
    """Décode une polyline encodée (format Google, précision 6 pour Valhalla)."""
    coords, index, lat, lon = [], 0, 0, 0
    while index < len(polyline):
        for i in range(2):
            resultat, decalage = 0, 0
            while True:
                b = ord(polyline[index]) - 63
                index += 1
                resultat |= (b & 0x1F) << decalage
                decalage += 5
                if b < 0x20:
                    break
            delta = ~(resultat >> 1) if resultat & 1 else resultat >> 1
            if i == 0:
                lat += delta
            else:
                lon += delta
        coords.append([round(lon / 10 ** precision, 6), round(lat / 10 ** precision, 6)])
    return coords


for l in proches.itertuples():
    if l.id_kebab in trajets:
        continue
    requete = {"locations": [{"lat": GARE[0], "lon": GARE[1], "radius": 300}, {"lat": l.lat, "lon": l.lon}],
               "costing": "pedestrian", "directions_options": {"units": "kilometers"}, "directions_type": "none"}
    for essai in range(3):
        try:
            r = requests.get(VALHALLA_ROUTE, params={"json": json.dumps(requete, separators=(",", ":"))},
                             headers=HEADERS, timeout=60)
            r.raise_for_status()
            jambe = r.json()["trip"]["legs"][0]
            trajets[l.id_kebab] = {"trace": decoder(jambe["shape"]), "secondes": jambe["summary"]["time"],
                                   "km": jambe["summary"]["length"]}
            break
        except (requests.RequestException, KeyError, ValueError) as e:
            print(f"  échec Valhalla pour {l.id_kebab} ({e})")
            time.sleep(3 * (essai + 1))
    time.sleep(1.1)                       # service public : on reste poli
    cache.write_text(json.dumps(trajets), encoding="utf-8")
print(f"trajets à pied : {len(trajets)} sur {len(proches)} kebabs à moins de {RAYON_M} m de la gare")
