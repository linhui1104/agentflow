#!/usr/bin/env python3
"""docx → HTML（按 body 顺序遍历段落/表格/图片，供 Chrome headless 打印 PDF）"""
import re
import sys
import zipfile
from pathlib import Path

from docx import Document
from docx.document import Document as _Doc
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn

SRC = Path("/mnt/c/Users/贾晖/Desktop/【赛题一+队伍名称+AgentFlow多智能体编排调度平台】项目白皮书.docx")
OUT_HTML = Path("/mnt/c/Temp/proposal.html")
IMG_DIR = Path("/mnt/c/Temp/proposal_imgs")
IMG_DIR.mkdir(parents=True, exist_ok=True)

# 提取图片
with zipfile.ZipFile(SRC) as z:
    for name in z.namelist():
        if name.startswith("word/media/"):
            z.extract(name, IMG_DIR)
media_files = {p.name: p for p in IMG_DIR.glob("word/media/*")}

doc = Document(str(SRC))


def run_style(run):
    sz = run.font.size.pt if run.font.size else None
    bold = run.font.bold
    name = run.font.name
    return sz, bold, name


def para_to_html(p: Paragraph):
    text = p.text
    if not text.strip():
        return "<p class='sp'></p>"
    # 取第一个有样式的 run
    sz, bold, name = None, None, None
    for r in p.runs:
        if r.text.strip():
            sz, bold, name = run_style(r)
            break
    is_center = p.alignment is not None and str(p.alignment).endswith("CENTER")
    cls = []
    if name == "Consolas":
        return f"<pre>{_esc(text)}</pre>"
    if sz and sz >= 16 and bold:
        return f"<h1>{_esc(text)}</h1>"
    if sz and sz >= 13 and bold:
        return f"<h2>{_esc(text)}</h2>"
    if sz and sz >= 18 and bold:  # 封面大标题
        return f"<div class='cover'>{_esc(text)}</div>"
    cls.append("center" if is_center else "p")
    indent = p.paragraph_format.first_line_indent
    style = "style='text-indent:2em'" if indent else ""
    return f"<p class='{' '.join(cls)}' {style}>{_esc(text)}</p>"


def table_to_html(t: Table):
    rows = ["<table>"]
    for i, row in enumerate(t.rows):
        tag = "th" if i == 0 else "td"
        cells = "".join(f"<{tag}>{_esc(c.text)}</{tag}>" for c in row.cells)
        rows.append(f"<tr>{cells}</tr>")
    rows.append("</table>")
    return "\n".join(rows)


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace("\n", "<br/>"))


# 按 body 顺序遍历
body = doc.element.body
parts = []
for child in body.iterchildren():
    if child.tag == qn("w:p"):
        parts.append(para_to_html(Paragraph(child, doc)))
    elif child.tag == qn("w:tbl"):
        parts.append(table_to_html(Table(child, doc)))

# 图片处理：docx 段落里的 drawing 在段落文本中不可见，需按 inline_shapes 顺序插入
# 简化：把 <w:drawing> 段落替换为 <img>
from lxml import etree
html = "\n".join(parts)
# 找 drawing 段落 → 依次替换为对应媒体文件
img_idx = 0
def repl(m):
    global img_idx
    # 按提取顺序映射（docx media 命名 image1.png...）
    img_idx += 1
    f = media_files.get(f"image{img_idx}.png") or media_files.get(f"image{img_idx}.jpeg")
    if f:
        return f"<p class='fig'><img src='{f.as_posix()}'/></p>"
    return ""
# w:drawing 所在段落在 python-docx 文本里是空的 —— 直接扫描 parts 里的空段落标记位置不可靠
# 更稳：重新遍历，检查段落 XML 是否含 drawing
parts2 = []
img_i = 0
for child in body.iterchildren():
    if child.tag == qn("w:p"):
        p = Paragraph(child, doc)
        if child.findall(".//" + qn("w:drawing")):
            img_i += 1
            f = media_files.get(f"image{img_i}.png") or media_files.get(f"image{img_i}.jpeg")
            if f:
                parts2.append(f"<p class='fig'><img src='{f.as_posix()}'/></p>")
            continue
        parts2.append(para_to_html(p))
    elif child.tag == qn("w:tbl"):
        parts2.append(table_to_html(Table(child, doc)))

html = "\n".join(parts2)

page = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<style>
@page {{ size: A4; margin: 20mm 18mm; }}
body {{ font-family: "Microsoft YaHei","SimSun",sans-serif; font-size: 11pt; line-height: 1.65; color: #1a1a1a; }}
h1 {{ font-size: 15pt; color: #1f3b73; margin: 18px 0 8px; border-bottom: 2px solid #1f3b73; padding-bottom: 4px; }}
h2 {{ font-size: 12.5pt; color: #2e518f; margin: 12px 0 5px; }}
p {{ margin: 4px 0; }}
p.p {{ text-align: justify; }}
.center {{ text-align: center; }}
.cover {{ font-size: 16pt; font-weight: bold; text-align: center; margin: 14px 0; }}
pre {{ font-family: Consolas,monospace; font-size: 8.5pt; background: #f5f7fa; padding: 8px; border-left: 3px solid #6366f1; white-space: pre-wrap; }}
table {{ border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9.5pt; }}
th, td {{ border: 1px solid #b8c2d0; padding: 4px 7px; text-align: left; }}
th {{ background: #eef2f8; }}
.fig img {{ max-width: 100%; }}
.fig {{ text-align: center; margin: 8px 0; }}
</style></head><body>
{html}
</body></html>"""

OUT_HTML.write_text(page)
print("HTML生成:", OUT_HTML, f"({len(page)} chars)")
