"""
98 - Livrables du rapport, à partir de rapport/rapport.md :

- rapport/<NOM>.qmd  : source Quarto (demandée par le sujet) ;
- rapport/<NOM>.docx : rapport Word (Pandoc, puis mise en forme avec python-docx) :
  page de garde avec liens cliquables, sommaire automatique, Times New Roman, légendes
  centrées, tableaux encadrés, numéros de page ;
- rapport/<NOM>.pdf  : export du .docx par Word (sommaire mis à jour), via word_maj.ps1.

Usage (depuis scripts/) : python 98_livrables.py
Nécessite : pypandoc_binary, python-docx, et Microsoft Word pour le PDF.
"""
import copy
import re
import subprocess

import pypandoc
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from config import RACINE

NOM = "AMAVIGAN_COULIBALY_rapport_SAE5EMS01"
RAPPORT = RACINE / "rapport"
SCENE = "https://coulibaly-abou.github.io/sae-kebabs-marseille/dashboard/kebabs_3d.html"
DEPOT = "https://github.com/coulibaly-abou/sae-kebabs-marseille"
POLICE, CODE = "Times New Roman", "Courier New"
BLEU = RGBColor(0x1F, 0x3A, 0x5F)

md = (RAPPORT / "rapport.md").read_text(encoding="utf-8")

# --- 1. Fichier Quarto ----------------------------------------------------------------
qmd = md.replace('lang: fr\n---', 'lang: fr\nformat:\n  pdf:\n    toc: false\n    mainfont: "Times New Roman"\n'
                 '  html:\n    embed-resources: true\n---', 1)
qmd = re.sub(r'<div class="saut-de-page"[^>]*></div>', "{{< pagebreak >}}", qmd)
(RAPPORT / f"{NOM}.qmd").write_text(qmd, encoding="utf-8")
print(f"-> rapport/{NOM}.qmd")

# --- 2. Markdown préparé pour Pandoc ----------------------------------------------------
SAUT = '\n```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```\n'
t = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)
t = t[t.index("## Sommaire"):]                                   # la page de garde est refaite en Word
t = t[t.index("### Liste des figures"):]                         # le sommaire devient un champ Word
t = re.sub(r'<div class="saut-de-page"[^>]*></div>', SAUT, t)
t = re.sub(r"!\[[^\]]*\]\((figures/[^)]+)\)", r"![](\1)", t)     # légendes : celles du texte
t = t.replace("<br>", "")
docx_brut = RAPPORT / f"{NOM}.docx"
pypandoc.convert_text(t, "docx", format="markdown-implicit_figures", outputfile=str(docx_brut),
                      extra_args=["--resource-path", str(RAPPORT)])

# --- 3. Mise en forme -----------------------------------------------------------------------
doc = Document(str(docx_brut))
sec = doc.sections[0]
sec.page_height, sec.page_width = Cm(29.7), Cm(21)
sec.top_margin, sec.bottom_margin = Cm(1.8), Cm(1.8)
sec.left_margin = sec.right_margin = Cm(2.0)
largeur_utile = Cm(17.0)

# styles
for nom in ["Normal", "Body Text", "First Paragraph", "Compact"]:
    if nom in [s.name for s in doc.styles]:
        st = doc.styles[nom]
        st.font.name, st.font.size = POLICE, Pt(10.5)
        pf = st.paragraph_format
        pf.space_before, pf.space_after, pf.line_spacing = Pt(0), Pt(3), 1.05
        if nom != "Compact":
            pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
for niveau, taille, avant in [(1, 14.5, 10), (2, 12, 7), (3, 11, 5)]:
    st = doc.styles[f"Heading {niveau}"]
    st.font.name, st.font.size, st.font.bold, st.font.italic = POLICE, Pt(taille), True, False
    st.font.color.rgb = BLEU
    st.paragraph_format.space_before, st.paragraph_format.space_after = Pt(avant), Pt(4)
    st.paragraph_format.keep_with_next = True
if "Source Code" in [s.name for s in doc.styles]:
    sc = doc.styles["Source Code"]
    sc.font.size = Pt(7.5)
    sc.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    sc.paragraph_format.line_spacing, sc.paragraph_format.space_after = 1.0, Pt(0)
    sc.paragraph_format.left_indent = Cm(0.3)
    fond = OxmlElement("w:shd"); fond.set(qn("w:val"), "clear"); fond.set(qn("w:fill"), "F3F2EF")
    sc.element.get_or_add_pPr().append(fond)
if "Hyperlink" in [s.name for s in doc.styles]:
    doc.styles["Hyperlink"].font.color.rgb = RGBColor(0x05, 0x63, 0xC1)
    doc.styles["Hyperlink"].font.underline = True

# police partout (sauf le code)
for el in [doc.styles.element, doc.element.body]:
    for rf in el.iter(qn("w:rFonts")):
        code = rf.get(qn("w:ascii")) in ("Consolas", "Courier New")
        for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rf.set(qn(a), CODE if code else POLICE)
        for a in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
            rf.attrib.pop(qn(a), None)
for r in doc.element.body.iter(qn("w:r")):
    if r.xpath("./w:rPr/w:rStyle[@w:val='VerbatimChar']"):
        rpr = r.find(qn("w:rPr")); rf = rpr.find(qn("w:rFonts"))
        if rf is None:
            rf = OxmlElement("w:rFonts"); rpr.append(rf)
        for a in ("w:ascii", "w:hAnsi", "w:cs"):
            rf.set(qn(a), CODE)

# annexes : à partir du titre « Annexes »
dans_annexes = False
for p in doc.paragraphs:
    if p.style.name == "Heading 1" and p.text.strip() == "Annexes":
        dans_annexes = True
    # images : largeur et hauteur maximales
    for forme in p._p.iter(qn("wp:extent")):
        cx, cy = int(forme.get("cx")), int(forme.get("cy"))
        hmax = Cm(17 if dans_annexes else 7.2)
        k = min(1.0, largeur_utile / cx, hmax / cy)
        forme.set("cx", str(int(cx * k))); forme.set("cy", str(int(cy * k)))
        for ext in p._p.iter(qn("a:ext")):
            ext.set("cx", str(int(cx * k))); ext.set("cy", str(int(cy * k)))
    if p._p.xpath(".//w:drawing"):
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(4), Pt(1)
    # légendes
    if re.match(r"^(Figure|Tableau) \d+ :", p.text) and all(r.italic for r in p.runs if r.text.strip()):
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(6)
        for r in p.runs:
            r.font.size = Pt(9); r.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
        if p.text.startswith("Tableau"):
            p.paragraph_format.keep_with_next = True
    # citation (problématique)
    if p.style.name == "Block Text":
        p.paragraph_format.left_indent = Cm(1); p.paragraph_format.right_indent = Cm(1)
        for r in p.runs:
            r.italic = True

# tableaux : encadrés, en-tête grisé, 9 pt, centrés
for tb in doc.tables:
    tb.alignment = WD_TABLE_ALIGNMENT.CENTER
    tblPr = tb._tbl.tblPr
    bords = OxmlElement("w:tblBorders")
    for cote in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{cote}")
        b.set(qn("w:val"), "single"); b.set(qn("w:sz"), "4"); b.set(qn("w:color"), "A6A6A6")
        bords.append(b)
    for vieux in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(vieux)
    tblPr.append(bords)
    for i, ligne in enumerate(tb.rows):
        for cel in ligne.cells:
            if i == 0:
                tcPr = cel._tc.get_or_add_tcPr()
                fond = OxmlElement("w:shd"); fond.set(qn("w:val"), "clear"); fond.set(qn("w:fill"), "EDEBE6")
                tcPr.append(fond)
            for p in cel.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                p.paragraph_format.space_after = Pt(0)
                for r in p.runs:
                    r.font.size = Pt(9)
                    if i == 0:
                        r.bold = True


# --- 4. Page de garde, liens et sommaire ---------------------------------------------------
def lien(par, texte, url, taille=11):
    r_id = par.part.relate_to(url, RT.HYPERLINK, is_external=True)
    h = OxmlElement("w:hyperlink"); h.set(qn("r:id"), r_id)
    r = OxmlElement("w:r"); rpr = OxmlElement("w:rPr")
    rf = OxmlElement("w:rFonts")
    for a in ("w:ascii", "w:hAnsi", "w:cs"):
        rf.set(qn(a), POLICE)
    c = OxmlElement("w:color"); c.set(qn("w:val"), "0563C1")
    u = OxmlElement("w:u"); u.set(qn("w:val"), "single")
    sz = OxmlElement("w:sz"); sz.set(qn("w:val"), str(int(taille * 2)))
    for e in (rf, c, u, sz):
        rpr.append(e)
    r.append(rpr)
    tt = OxmlElement("w:t"); tt.text = texte; tt.set(qn("xml:space"), "preserve"); r.append(tt)
    h.append(r); par._p.append(h)


premier = doc.paragraphs[0]


def ligne(texte="", taille=11, gras=False, italique=False, couleur=None, apres=4, avant=0):
    p = premier.insert_paragraph_before()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after, p.paragraph_format.space_before = Pt(apres), Pt(avant)
    if texte:
        r = p.add_run(texte)
        r.font.size, r.bold, r.italic = Pt(taille), gras, italique
        r.font.name = POLICE
        if couleur:
            r.font.color.rgb = couleur
    return p


ligne("Université de Perpignan Via Domitia", 12, gras=True)
ligne("IUT de Carcassonne · BUT Science des Données, 3e année", 12)
ligne("Année universitaire 2026-2027", 11, apres=90)
ligne("Étude de l'implantation des kebabs", 24, gras=True, couleur=BLEU, apres=2)
ligne("dans l'agglomération marseillaise", 24, gras=True, couleur=BLEU, apres=14)
ligne("Ce que la carte des kebabs révèle de la métropole Aix-Marseille-Provence", 14, italique=True, apres=28)
ligne("SAÉ 5.EMS.01 : Mener une étude statistique dans un domaine d'application", 12, apres=70)
ligne("Réalisé par Ayi Amavigan et Aboubakar Coulibaly", 13, gras=True)
ligne("Encadrant : Sébastien Pinel", 12)
ligne("Décembre 2026", 12, apres=60)
p = ligne("Scène 3D interactive : ", 11, gras=True, apres=4); lien(p, SCENE.replace("https://", ""), SCENE)
p = ligne("Code, données et rapport : ", 11, gras=True, apres=4); lien(p, DEPOT.replace("https://", ""), DEPOT)
p = ligne(); p.add_run().add_break(WD_BREAK.PAGE)

# sommaire automatique (mis à jour par Word)
titre = ligne("Sommaire", 16, gras=True, couleur=BLEU, apres=10)
titre.alignment = WD_ALIGN_PARAGRAPH.LEFT
p = premier.insert_paragraph_before()
for typ, texte in [("begin", None), (None, ' TOC \\o "1-2" \\h \\z \\u '), ("separate", None),
                   (None, "Clic droit, puis Mettre à jour les champs."), ("end", None)]:
    r = OxmlElement("w:r")
    if typ:
        fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), typ); r.append(fc)
    elif texte.startswith(" TOC"):
        it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = texte; r.append(it)
    else:
        tt = OxmlElement("w:t"); tt.text = texte; r.append(tt)
    p._p.append(r)
p = premier.insert_paragraph_before(); p.add_run().add_break(WD_BREAK.PAGE)

# --- 5. Pied de page : numéro de page (pas sur la couverture) --------------------------------
sec.different_first_page_header_footer = True
pied = sec.footer.paragraphs[0]
pied.alignment = WD_ALIGN_PARAGRAPH.CENTER
for typ, texte in [("begin", None), (None, " PAGE "), ("end", None)]:
    r = OxmlElement("w:r")
    if typ:
        fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), typ); r.append(fc)
    else:
        it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = texte; r.append(it)
    pied._p.append(r)
for r in pied.runs:
    r.font.size, r.font.name = Pt(9), POLICE
en_tete = sec.header.paragraphs[0]
en_tete.alignment = WD_ALIGN_PARAGRAPH.RIGHT
r = en_tete.add_run("SAÉ 5.EMS.01 · Les kebabs de l'agglomération marseillaise")
r.font.size, r.font.name, r.italic = Pt(8.5), POLICE, True
r.font.color.rgb = RGBColor(0x70, 0x70, 0x70)

doc.core_properties.title = "Étude de l'implantation des kebabs dans l'agglomération marseillaise"
doc.core_properties.author = "Ayi Amavigan, Aboubakar Coulibaly"
doc.save(str(docx_brut))
print(f"-> rapport/{NOM}.docx")

# --- 6. PDF par Word ---------------------------------------------------------------------------
pdf = RAPPORT / f"{NOM}.pdf"
sortie = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                         str(RACINE / "scripts" / "word_maj.ps1"), "-Docx", str(docx_brut), "-Pdf", str(pdf)],
                        capture_output=True, text=True)
print(sortie.stdout.strip() or sortie.stderr.strip())
print(f"-> rapport/{NOM}.pdf")
