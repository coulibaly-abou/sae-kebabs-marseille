"""
98 - Livrables du rapport :
- rapport/<NOM>.qmd : version Quarto du rapport (sommaire automatique, sauts de page Quarto) ;
- rapport/<NOM>.pdf : PDF imprimé par Chrome à partir de l'aperçu HTML (script 99), avec
  numéros de page. Quarto n'étant pas installé sur nos postes, c'est ce PDF que nous rendons ;
  le .qmd se compile tel quel avec `quarto render` si Quarto est disponible.

Usage (depuis scripts/) : python 98_livrables.py
"""
import base64
import re
import subprocess
import sys
import time

from config import RACINE

NOM = "AMAVIGAN_COULIBALY_rapport_SAE5EMS01"
RAPPORT = RACINE / "rapport"

# --- 1. Fichier Quarto --------------------------------------------------------------
md = (RAPPORT / "rapport.md").read_text(encoding="utf-8")
qmd = md.replace('lang: fr\n---', 'lang: fr\nformat:\n  pdf:\n    toc: false\n    number-sections: false\n'
                 '    mainfont: "Times New Roman"\n  html:\n    toc: false\n    embed-resources: true\n---', 1)
qmd = re.sub(r'<div class="saut-de-page"[^>]*></div>', "{{< pagebreak >}}", qmd)
qmd = qmd.replace("](figures/", "](figures/")
(RAPPORT / f"{NOM}.qmd").write_text(qmd, encoding="utf-8")
print(f"-> rapport/{NOM}.qmd")

# --- 2. PDF par Chrome --------------------------------------------------------------
subprocess.run([sys.executable, str(RACINE / "scripts" / "99_apercu_rapport.py")], check=True)
from selenium import webdriver  # noqa: E402

options = webdriver.ChromeOptions()
options.add_argument("--headless=new")
navigateur = webdriver.Chrome(options=options)
navigateur.get((RAPPORT / "rapport_apercu.html").as_uri())
time.sleep(4)  # MathJax et images
pied = ('<div style="font-size:8px;width:100%;text-align:center;color:#52514e;'
        'font-family:Georgia,serif"><span class="pageNumber"></span></div>')
pdf = navigateur.execute_cdp_cmd("Page.printToPDF", {
    "printBackground": True, "paperWidth": 8.27, "paperHeight": 11.69,
    "marginTop": 0.7, "marginBottom": 0.7, "marginLeft": 0.75, "marginRight": 0.75,
    "displayHeaderFooter": True, "headerTemplate": "<span></span>", "footerTemplate": pied,
})
navigateur.quit()
(RAPPORT / f"{NOM}.pdf").write_bytes(base64.b64decode(pdf["data"]))
print(f"-> rapport/{NOM}.pdf")
