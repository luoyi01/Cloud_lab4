"""Create an editable SimSun Word report from the measured report Markdown."""
import argparse
from pathlib import Path
import re
import zipfile
from lxml import etree

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import String
from reportlab.graphics.charts.barcharts import VerticalBarChart

import build_report

ROOT = Path(__file__).resolve().parents[1]
FONT = "宋体"
WIDTH = 16.0


def set_font(font, size=None, bold=None):
    font.name = FONT
    font.color.rgb = RGBColor(0, 0, 0)
    if size is not None:
        font.size = Pt(size)
    if bold is not None:
        font.bold = bold
    fonts = font._element.get_or_add_rPr().get_or_add_rFonts()
    for key in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn("w:" + key), FONT)
    for key in tuple(fonts.attrib):
        if key.endswith("Theme"):
            del fonts.attrib[key]


def add_text(paragraph, text, size=None, bold=None):
    run = paragraph.add_run(text)
    set_font(run.font, size, bold)
    return run


def shade(element, color):
    prop = element.get_or_add_pPr() if element.tag == qn("w:p") else element.get_or_add_tcPr()
    fill = OxmlElement("w:shd")
    fill.set(qn("w:fill"), color)
    fill.set(qn("w:val"), "clear")
    prop.append(fill)


def word_figures(font_path):
    pdfmetrics.registerFont(TTFont("Chinese", font_path))
    drawings = [(build_report.architecture(), "word-architecture"),
                (build_report.resource_chart(build_report.read("summary.json")), "word-api-memory")]
    for drawing, name in drawings:
        for element in drawing.contents:
            if isinstance(element, String):
                element.fontName = "Chinese"
            elif isinstance(element, VerticalBarChart):
                element.categoryAxis.labels.fontName = "Chinese"
                element.valueAxis.labels.fontName = "Chinese"
        build_report.render_figure(drawing, name)


def add_table(doc, headers, rows, number):
    weights = {1: [4.0, 1.3, 10.7], 2: [3.0, 13.0], 3: [4.7, 11.3],
               4: [5.0, 11.0], 5: [3.0, 1.2, 3.0, 3.0, 2.9, 2.9],
               6: [3.0, 1.2, 2.8, 3.0, 3.2, 2.8], 7: [3.0, 4.0, 4.0, 2.5, 2.5],
               8: [3.2, 5.7, 7.1], 9: [2.2, 4.6, 4.6, 4.6]}[number]
    table = doc.add_table(rows=1, cols=len(headers))
    table.autofit = False
    table.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for col, weight in zip(table.columns, weights):
        col.width = Cm(weight)
    prop = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = OxmlElement("w:" + edge)
        for key, value in (("val", "single"), ("sz", "4"), ("color", "D9D9D9")):
            border.set(qn("w:" + key), value)
        borders.append(border)
    prop.append(borders)
    margins = OxmlElement("w:tblCellMar")
    for edge, value in (("top", "85"), ("bottom", "85"), ("left", "90"), ("right", "90")):
        item = OxmlElement("w:" + edge)
        item.set(qn("w:w"), value)
        item.set(qn("w:type"), "dxa")
        margins.append(item)
    prop.append(margins)
    repeat = OxmlElement("w:tblHeader")
    table.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row_index, values in enumerate([headers] + rows):
        row = table.rows[0] if row_index == 0 else table.add_row()
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        for col_index, (cell, value, width) in enumerate(zip(row.cells, values, weights)):
            cell.width = Cm(width)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if row_index == 0:
                shade(cell._tc, "E9EEF2")
            para = cell.paragraphs[0]
            para.paragraph_format.space_after = Pt(0)
            para.paragraph_format.space_before = Pt(0)
            para.paragraph_format.line_spacing = 1.15
            para.paragraph_format.keep_with_next = row_index < len(rows)
            para.paragraph_format.widow_control = True
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER if row_index == 0 or number in (5, 6, 7, 9) or (number == 1 and col_index == 1) else WD_ALIGN_PARAGRAPH.LEFT
            add_text(para, value, 10.5, row_index == 0)
    gap = doc.add_paragraph()
    gap.paragraph_format.space_after = Pt(0)
    gap.paragraph_format.line_spacing = Pt(3)
    add_text(gap, "", 3)


def normalize_package(path):
    """Also normalize defaults, theme fonts and unused numbering styles."""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
          "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    members = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            data = archive.read(name)
            if name.startswith("word/") and name.endswith(".xml"):
                tree = etree.fromstring(data)
                for border in tree.findall(".//w:pBdr", ns):
                    border.getparent().remove(border)
                for fonts in tree.findall(".//w:rFonts", ns):
                    fonts.attrib.clear()
                    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
                        fonts.set(qn("w:" + attr), FONT)
                for item in tree.findall(".//a:fontScheme//a:latin", ns) + tree.findall(".//a:fontScheme//a:ea", ns) + tree.findall(".//a:fontScheme//a:cs", ns) + tree.findall(".//a:fontScheme//a:font", ns):
                    item.set("typeface", FONT)
                if name == "word/styles.xml":
                    defaults = tree.find("w:docDefaults/w:rPrDefault/w:rPr", ns)
                    fonts = defaults.find("w:rFonts", ns)
                    if fonts is None:
                        fonts = etree.SubElement(defaults, qn("w:rFonts"))
                    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
                        fonts.set(qn("w:" + attr), FONT)
                data = etree.tostring(tree, encoding="UTF-8", xml_declaration=True, standalone=True)
            members[name] = data
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", default="C:/Windows/Fonts/simsun.ttc")
    args = parser.parse_args()
    word_figures(args.font)
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(2.3)
    section.left_margin = section.right_margin = Cm(2.5)
    section.footer_distance = Cm(1.1)
    for style in doc.styles:
        if hasattr(style, "font"):
            set_font(style.font)
    normal = doc.styles["Normal"]
    set_font(normal.font, 12)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.widow_control = True
    for name, size, before, after in (("Title", 20, 0, 16), ("Heading 1", 15, 12, 8), ("Heading 2", 12, 9, 5)):
        style = doc.styles[name]
        set_font(style.font, size, True)
        style.paragraph_format.line_spacing = 1.25
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.keep_together = True
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_text(footer, "第 ", 9)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    add_text(footer, " 页", 9)
    lines = (ROOT / "docs/report.md").read_text(encoding="utf-8").splitlines()
    index, table_number = 0, 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line:
            continue
        if line.startswith("# "):
            para = doc.add_paragraph(style="Title")
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_text(para, "班级云留言板云计算实验报告", 20, True)
        elif line.startswith("## "):
            title = line[3:]
            para = doc.add_paragraph(style="Heading 1")
            if title.startswith(("一、", "八、")):
                para.paragraph_format.page_break_before = True
            add_text(para, title)
        elif line.startswith("### "):
            add_text(doc.add_paragraph(style="Heading 2"), line[4:])
        elif line.startswith("```"):
            code = []
            while index < len(lines) and not lines[index].startswith("```"):
                code.append(lines[index]); index += 1
            index += 1
            para = doc.add_paragraph()
            para.paragraph_format.line_spacing = 1.15
            para.paragraph_format.space_before = Pt(5)
            para.paragraph_format.space_after = Pt(8)
            para.paragraph_format.keep_together = True
            shade(para._p, "F3F5F6")
            add_text(para, "\n".join(code), 9.5)
        elif line.startswith("|"):
            table_number += 1
            headers = [part.strip() for part in line.strip("|").split("|")]
            index += 1  # Markdown separator.
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append([part.strip() for part in lines[index].strip().strip("|").split("|")])
                index += 1
            add_table(doc, headers, rows, table_number)
        elif line.startswith("!["):
            match = re.fullmatch(r"!\[(.*?)\]\((.*?)\)", line)
            caption, relative = match.groups()
            image = (ROOT / "docs" / relative).resolve()
            if image.name in ("architecture.png", "api-memory.png"):
                image = image.with_name("word-" + image.name)
            with Image.open(image) as source:
                width, height = source.size
            ratio = min(WIDTH / width, 9.0 / height)
            para = doc.add_paragraph()
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para.paragraph_format.space_after = Pt(4)
            para.paragraph_format.keep_with_next = True
            picture = para.add_run().add_picture(str(image), width=Cm(width * ratio), height=Cm(height * ratio))
            picture._inline.docPr.set("descr", caption)
            para = doc.add_paragraph()
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para.paragraph_format.line_spacing = 1.2
            para.paragraph_format.space_after = Pt(10)
            para.paragraph_format.keep_together = True
            add_text(para, caption, 10.5)
        elif re.match(r"表 \d+", line):
            para = doc.add_paragraph()
            para.paragraph_format.keep_with_next = True
            para.paragraph_format.space_before = Pt(6)
            para.paragraph_format.space_after = Pt(5)
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_text(para, line, 10.5)
        else:
            para = doc.add_paragraph()
            add_text(para, line)
            if not line.startswith(("学号", "实验平台", "交付版本", "仓库", "[")):
                para.paragraph_format.first_line_indent = Pt(24)
    assert table_number == 9
    props = doc.core_properties
    props.title = "班级云留言板云计算实验报告"
    props.subject = "Docker Compose 与 Kind Kubernetes 的部署与实测对比"
    props.author = props.last_modified_by = props.comments = ""
    props.keywords = "云计算 实验 容器 Kubernetes"
    output = ROOT / "report.docx"
    doc.save(output)
    normalize_package(output)
    print(f"Created {output.name}: 9 editable tables, 6 figures; all editable fonts set to {FONT}.")


if __name__ == "__main__":
    main()
