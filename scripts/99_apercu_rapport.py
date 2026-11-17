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
img + em, p > em:only-child { display: block; text-align: center; color: #52514e; font-size: .9em; }
table { border-collapse: collapse; margin: 1em 0; font-size: .92em; }
th, td { border: 1px solid #dcdad3; padding: .3em .7em; }
th { background: #f0efec; }
blockquote { border-left: 4px solid #2a78d6; margin: 1em 0; padding: .2em 1em; background: #f0efec; }
code { background: #f0efec; padding: 0 .25em; border-radius: 3px; }
.saut-de-page { page-break-after: always; }
@media print { body { max-width: none; margin: 0; } h1 { page-break-before: auto; } }
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
