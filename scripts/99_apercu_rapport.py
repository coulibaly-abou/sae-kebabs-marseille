"""
99 - Aperçu du rapport : convertit rapport/rapport.md en page HTML lisible
(images affichées, tableaux mis en forme, sauts de page respectés à l'impression).

Usage (depuis le dossier scripts/) :
    python 99_apercu_rapport.py
puis ouvrir rapport/rapport_apercu.html dans un navigateur.
Pour un PDF provisoire : dans le navigateur, Ctrl+P -> "Enregistrer au format PDF".

Le rendu final se fera avec Quarto (consigne du sujet) ; cet aperçu sert à relire.
"""
import re

import markdown

from config import RACINE

SOURCE = RACINE / "rapport" / "rapport.md"
SORTIE = RACINE / "rapport" / "rapport_apercu.html"

STYLE = """
body { font-family: Georgia, 'Times New Roman', serif; max-width: 820px; margin: 2rem auto;
       padding: 0 16px; line-height: 1.55; color: #0b0b0b; background: #fcfcfb; }
h1, h2, h3 { font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.25; }
h1 { border-bottom: 2px solid #2a78d6; padding-bottom: .2em; margin-top: 2.2em; }
img { max-width: 100%; display: block; margin: 1.2em auto .3em; }
p.legende { text-align: center; color: #52514e; font-size: .9em; }
table { border-collapse: collapse; margin: 1em 0; font-size: .92em; }
th, td { border: 1px solid #dcdad3; padding: .3em .7em; }
th { background: #f0efec; }
blockquote { border-left: 4px solid #2a78d6; margin: 1em 0; padding: .2em 1em; background: #f0efec; }
code { background: #f0efec; padding: 0 .25em; border-radius: 3px; }
.saut-de-page { page-break-after: always; }
@media print { body { max-width: none; margin: 0; } h1 { page-break-before: auto; } }
/* Mise en page du PDF rendu (A4, Times 10,5 pt) : le corps doit tenir en 15 pages. */
@page { size: A4; margin: 1.5cm 1.7cm 1.6cm; }
@media print {
  body { font-family: 'Times New Roman', Times, serif; font-size: 10.5pt; line-height: 1.3;
         padding: 0; background: #fff; }
  h1 { font-size: 15pt; margin: .8em 0 .3em; padding-bottom: .1em; }
  h2 { font-size: 12pt; margin: .75em 0 .25em; }
  h3 { font-size: 11pt; margin: .6em 0 .2em; }
  h1, h2, h3 { page-break-after: avoid; break-after: avoid; }
  p, li { margin: .3em 0; text-align: justify; orphans: 3; widows: 3; }
  ul { margin: .2em 0; padding-left: 1.3em; }
  img { max-height: 7.6cm; width: auto; margin: .35em auto .05em; }
  p.legende { font-size: 9pt; margin-bottom: .4em; text-align: center; }
  table { font-size: 8.8pt; margin: .4em auto; page-break-inside: avoid; }
  th, td { padding: .1em .45em; }
  blockquote { margin: .5em 0; padding: .1em .8em; }
}
"""


def ancre_github(titre: str, separateur: str) -> str:
    """Ancre d'un titre comme GitHub / VS Code (accents gardés), pour que les liens
    du sommaire "#31-périmètre-détude" fonctionnent aussi dans l'aperçu."""
    titre = re.sub(r"[^\w\- ]", "", titre.strip().lower())
    return titre.replace(" ", "-")


def main():
    texte = SOURCE.read_text(encoding="utf-8")
    # En-tête YAML (titre, auteurs...) : utile à Quarto, inutile ici
    texte = re.sub(r"\A---\n.*?\n---\n", "", texte, flags=re.S)
    # Commentaires de rédaction <!-- ... -->
    texte = re.sub(r"<!--.*?-->", "", texte, flags=re.S)
    # La page de garde est dans un <div> : on demande d'interpréter le Markdown dedans
    texte = texte.replace('<div align="center">', '<div align="center" markdown="1">')
    corps = markdown.markdown(texte, extensions=["tables", "md_in_html", "toc"],
                              extension_configs={"toc": {"slugify": ancre_github}})
    # Légendes (paragraphe entièrement en italique commençant par Figure / Tableau) : centrées
    corps = re.sub(r"<p><em>((?:Figure|Tableau) \d+ :[^<]*)</em></p>", r'<p class="legende"><em>\1</em></p>',
                   corps)
    # Formules LaTeX : affichées telles quelles (MathJax pour un rendu propre)
    page = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rapport SAÉ kebabs (aperçu)</title>
<script>window.MathJax = {{tex: {{inlineMath: [['$', '$']]}}}};</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<style>{STYLE}</style></head>
<body>{corps}</body></html>"""
    SORTIE.write_text(page, encoding="utf-8")
    print(f"-> {SORTIE.relative_to(RACINE)} (ouvrir dans un navigateur)")


if __name__ == "__main__":
    main()
