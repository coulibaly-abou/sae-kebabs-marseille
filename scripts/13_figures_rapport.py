"""
Figures complémentaires du rapport :
- figure de l'article de référence (Pearce et al., 2007), redessinée à partir de leur tableau 1 ;
- diagramme de Gantt prévisionnel (annexe A), lu dans Gantt_SAE_Kebabs_Marseille.xlsx ;
- capture de la scène 3D (dashboard/kebabs_3d.html), si Chrome et Selenium sont disponibles.
"""
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import openpyxl
from matplotlib.patches import Patch

from config import FIGURES, RACINE

FOND, TEXTE, TEXTE_2, GRILLE = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": TEXTE_2, "axes.labelcolor": TEXTE,
                     "xtick.color": TEXTE_2, "ytick.color": TEXTE_2, "figure.facecolor": FOND,
                     "axes.facecolor": FOND})

# --- 1. Article de référence ------------------------------------------------------
# Pearce J., Blakely T., Witten K., Bartie P. (2007), Am J Prev Med 32(5), tableau 1 :
# distance médiane (m) par la route au fast-food le plus proche, par décile de défavorisation
# (NZDep 2001), ensemble de la Nouvelle-Zélande.
deciles = list(range(1, 11))
tous = [1545, 1870, 1629, 1274, 1046, 892, 806, 735, 714, 742]
multinationales = [3498, 4422, 4459, 3978, 3076, 2617, 2161, 1926, 1894, 2259]
locaux = [1576, 1950, 1661, 1301, 1083, 919, 823, 762, 734, 753]

fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(deciles, multinationales, marker="o", color="#2a78d6", lw=2, label="Chaînes multinationales")
ax.plot(deciles, locaux, marker="o", color="#e0874a", lw=2, label="Fast-foods locaux")
ax.plot(deciles, tous, marker="o", color=TEXTE, lw=1.5, ls="--", label="Tous les fast-foods")
ax.set_xticks(deciles, ["1\nmoins\ndéfavorisé"] + [str(d) for d in range(2, 10)] + ["10\nplus\ndéfavorisé"])
ax.set_xlabel("Décile de défavorisation du quartier (indice NZDep 2001)")
ax.set_ylabel("Distance médiane au plus proche (m)")
ax.set_ylim(0, 5000)
ax.grid(axis="y", color=GRILLE)
ax.spines[["top", "right"]].set_visible(False)
ax.legend(frameon=False, loc="upper right")
fig.text(0.01, 0.01, "Données : Pearce et al. (2007), tableau 1 (37 760 quartiers de Nouvelle-Zélande). "
         "Graphique redessiné par nos soins.", fontsize=8, color=TEXTE_2)
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig(FIGURES / "fig00_article_pearce.png", dpi=200)
plt.close(fig)

# --- 2. Diagramme de Gantt ------------------------------------------------------------
COULEURS = {"FFA9D18E": ("#8fc27a", "Préparation"), "FFFFC000": ("#f2b630", "Analyse spatiale"),
            "FFF4A582": ("#ef9a72", "Modélisation et livrables"), "FFE03C31": ("#d9443a", "Semaine d'évaluation")}
ws = openpyxl.load_workbook(RACINE / "Gantt_SAE_Kebabs_Marseille.xlsx")["Gantt détaillé"]
semaines = [ws.cell(3, c).value.replace("\n", " ") for c in range(3, 15)]
lignes = []
for r in range(4, 38):
    libelle = ws.cell(r, 2).value
    if not libelle:
        continue
    cases = [(c - 3, ws.cell(r, c).fill.fgColor.rgb) for c in range(3, 15)
             if ws.cell(r, c).fill.fill_type and ws.cell(r, c).fill.fgColor.rgb in COULEURS]
    lignes.append((libelle, libelle[:2].rstrip(".").isdigit() and libelle[1] == ".", cases))

fig, ax = plt.subplots(figsize=(10, 9))
for i, (libelle, est_etape, cases) in enumerate(lignes):
    if est_etape:
        ax.axhspan(i - 0.5, i + 0.5, color="#efeeea", zorder=0)
    for semaine, coul in cases:
        ax.barh(i, 0.9, left=semaine + 0.05, height=0.62, color=COULEURS[coul][0], zorder=2)
ax.set_yticks(range(len(lignes)), [l[0] for l in lignes], fontsize=8.5)
for t, l in zip(ax.get_yticklabels(), lignes):
    if l[1]:
        t.set_fontweight("bold")
ax.invert_yaxis()
ax.set_xticks([s + 0.5 for s in range(12)], [s.replace(" ", "\n", 1) for s in semaines], fontsize=8)
ax.set_xlim(0, 12)
ax.xaxis.tick_top()
ax.grid(axis="x", color=GRILLE, zorder=1)
ax.set_axisbelow(True)
ax.spines[["top", "right", "bottom", "left"]].set_visible(False)
ax.tick_params(length=0)
ax.legend(handles=[Patch(color=c, label=l) for c, l in COULEURS.values()], frameon=False,
          loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=4, fontsize=9)
fig.tight_layout()
fig.savefig(FIGURES / "figA_gantt.png", dpi=200)
plt.close(fig)

# --- 3. Capture de la scène 3D --------------------------------------------------------
try:
    from selenium import webdriver
    options = webdriver.ChromeOptions()
    for a in ["--headless=new", "--window-size=1440,820", "--use-angle=swiftshader",
              "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--hide-scrollbars"]:
        options.add_argument(a)
    navigateur = webdriver.Chrome(options=options)
    navigateur.get((RACINE / "dashboard" / "kebabs_3d.html").as_uri())
    time.sleep(6)
    for etape, nom in [(1, "figD_scene3d_marseille.png"), (4, "figD_scene3d_marche.png"),
                       (6, "figD_scene3d_simulation.png")]:
        navigateur.execute_script(f"document.querySelectorAll('#points button')[{etape}].click()")
        time.sleep(5)
        if etape == 4:                    # marche : on fige l'horloge à 11 minutes pour la capture
            navigateur.execute_script("window.scene3d.avancer(660)")
            time.sleep(3)
        navigateur.save_screenshot(str(FIGURES / nom))
    navigateur.quit()
except Exception as erreur:  # pas de Chrome : les captures existantes sont conservées
    print("captures de la scène 3D non refaites :", erreur)

print("figures écrites dans", FIGURES)
