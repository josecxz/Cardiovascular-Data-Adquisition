"""Turn the Research Square hyperlinks into plain text holding the v1 URL.

For every hyperlinked cell whose target is a researchsquare.com article:

    * the cell keeps the URL as ordinary text (already /v1 after
      Update_To_V1_Identifiers.py),
    * the <hyperlink> element and its relationship are removed, so the cell is no
      longer clickable,
    * the 'Hyperlink' cell style is dropped, so it renders like every other URL cell
      instead of blue and underlined.

The single medRxiv hyperlink is left alone -- medRxiv has no version suffix, so it is
outside the Research Square scope of this change.

Re-running is a no-op: there is nothing left to strip.
"""
import re, shutil, zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

WORKBOOK = 'medRxiv and RS CV preprints data analysis 06_30 - Dates Fixed.xlsx'
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
MARKER = 'researchsquare.com'

SHEETS = [('xl/worksheets/sheet1.xml', 'Research Square'),
          ('xl/worksheets/sheet3.xml', 'Combined Raw Data'),
          ('xl/worksheets/sheet4.xml', 'Final analytic dataset')]

zin = zipfile.ZipFile(WORKBOOK)
shared = [''.join(t.text or '' for t in si.iter(NS + 't'))
          for si in ET.fromstring(zin.read('xl/sharedStrings.xml'))]

parts, report = {}, []
for part, name in SHEETS:
    xml = zin.read(part).decode('utf-8')
    relname = part.replace('xl/worksheets/', 'xl/worksheets/_rels/') + '.rels'
    rels = zin.read(relname).decode('utf-8')
    targets = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels))

    flattened, kept = [], []
    for m in list(re.finditer(r'<hyperlink ref="([A-Z]+\d+)" r:id="(rId\d+)"[^/]*/>', xml)):
        ref, rid = m.group(1), m.group(2)
        target = targets.get(rid, '')
        if MARKER not in target:
            kept.append((ref, target))
            continue

        # Cell text is authoritative; fall back to the relationship target.
        cm = re.search(rf'<c r="{ref}"[^>]*>(.*?)</c>', xml, re.S)
        text = target
        if cm:
            t = re.search(r'<t[^>]*>(.*?)</t>', cm.group(1), re.S)
            if t:
                text = t.group(1)
            else:
                v = re.search(r'<v>(\d+)</v>', cm.group(1))
                if v:
                    text = shared[int(v.group(1))]
            # Rewrite without the s="" hyperlink style so it renders as plain text.
            cell = f'<c r="{ref}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'
            xml = xml[:cm.start()] + cell + xml[cm.end():]

        xml = xml.replace(m.group(0), '')
        rels = re.sub(rf'<Relationship Id="{rid}"[^>]*/>', '', rels)
        flattened.append((ref, text))

    if '<hyperlinks>' in xml and re.search(r'<hyperlinks>\s*</hyperlinks>', xml):
        xml = re.sub(r'<hyperlinks>\s*</hyperlinks>', '', xml)

    parts[part] = xml.encode('utf-8')
    parts[relname] = rels.encode('utf-8')
    report.append((name, flattened, kept))

tmp = WORKBOOK + '.tmp'
with zipfile.ZipFile(WORKBOOK) as zsrc, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zsrc.infolist():
        zout.writestr(item, parts.get(item.filename) or zsrc.read(item.filename))
shutil.move(tmp, WORKBOOK)

for name, flattened, kept in report:
    print(f'{name!r}: {len(flattened)} hyperlinks flattened to text')
    for ref, text in flattened:
        print(f'   {ref:8} {text}')
    for ref, target in kept:
        print(f'   {ref:8} KEPT (not Research Square) -> {target}')
    print()
