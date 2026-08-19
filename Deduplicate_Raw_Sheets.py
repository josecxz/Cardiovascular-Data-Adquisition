"""Remove duplicate DOI rows from the three raw sheets.

Three preprints appear twice in the source data ('Research Square', 'MedRvix' and
'Combined Raw Data'). The copies are identical in every field except the sequential
'Number' counter, so the row with the LOWEST Number is kept and the rest dropped.

'Final analytic dataset' already has no duplicates and is not touched.

Deleting a row means renumbering every row below it -- Excel treats the r attribute as an
absolute position, so simply dropping a <row> would leave a blank row behind. Rows and
their cells are renumbered, and dimension/sortState ranges are shrunk to match.

These sheets carry no formulas, hyperlinks, merged cells or conditional formatting
(verified before writing this), so renumbering cannot break a reference.
"""
import re, shutil, zipfile
import xml.etree.ElementTree as ET

WORKBOOK = 'medRxiv and RS CV preprints data analysis 06_30 - Dates Fixed.xlsx'
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
SHEETS = [('xl/worksheets/sheet1.xml', 'Research Square'),
          ('xl/worksheets/sheet2.xml', 'MedRvix'),
          ('xl/worksheets/sheet3.xml', 'Combined Raw Data')]
DOI_COL, NUM_COL = 'B', 'A'

zin = zipfile.ZipFile(WORKBOOK)
shared = [''.join(t.text or '' for t in si.iter(NS + 't'))
          for si in ET.fromstring(zin.read('xl/sharedStrings.xml'))]


def cell_text(row_xml, col):
    m = re.search(rf'<c r="{col}\d+"[^>]*?(/>|>(.*?)</c>)', row_xml, re.S)
    if not m or m.group(1) == '/>':
        return ''
    body, opening = m.group(2), m.group(0).split('>', 1)[0]
    if 't="inlineStr"' in opening:
        t = re.search(r'<t[^>]*>(.*?)</t>', body, re.S)
        return t.group(1) if t else ''
    v = re.search(r'<v>(.*?)</v>', body, re.S)
    if not v:
        return ''
    if 't="s"' in opening:
        return shared[int(v.group(1))]
    return v.group(1)


parts, report = {}, []
for part, name in SHEETS:
    xml = zin.read(part).decode('utf-8')
    head = xml[:xml.index('<sheetData>') + len('<sheetData>')]
    tail = xml[xml.rindex('</sheetData>'):]
    blocks = re.findall(r'<row r="\d+".*?</row>', xml, re.S)

    # Group data rows by DOI; keep the copy with the smallest Number.
    seen = {}
    for i, b in enumerate(blocks):
        rnum = int(re.search(r'<row r="(\d+)"', b).group(1))
        if rnum == 1:
            continue
        doi = cell_text(b, DOI_COL).strip()
        if not doi:
            continue
        num = cell_text(b, NUM_COL).strip()
        num = int(num) if num.isdigit() else 10**9
        seen.setdefault(doi, []).append((num, i))

    drop, dropped = set(), []
    for doi, hits in seen.items():
        if len(hits) < 2:
            continue
        hits.sort()
        for num, i in hits[1:]:
            drop.add(i)
            dropped.append((doi, num, int(re.search(r'<row r="(\d+)"', blocks[i]).group(1))))

    kept = [b for i, b in enumerate(blocks) if i not in drop]

    # Renumber rows and their cells so no gap is left behind.
    out = []
    for new_r, b in enumerate(kept, start=1):
        old_r = int(re.search(r'<row r="(\d+)"', b).group(1))
        if old_r != new_r:
            b = re.sub(r'^<row r="\d+"', f'<row r="{new_r}"', b)
            b = re.sub(r'<c r="([A-Z]+)\d+"', lambda m: f'<c r="{m.group(1)}{new_r}"', b)
        out.append(b)

    last = len(out)
    xml = head + ''.join(out) + tail
    xml = re.sub(r'<dimension ref="A1:([A-Z]+)\d+"/>',
                 lambda m: f'<dimension ref="A1:{m.group(1)}{last}"/>', xml, count=1)
    xml = re.sub(r'(<sortState ref="A2:([A-Z]+))\d+"',
                 lambda m: f'{m.group(1)}{last}"', xml, count=1)
    xml = re.sub(r'(<sortCondition ref="([A-Z])1:([A-Z]))\d+"',
                 lambda m: f'{m.group(1)}{last}"', xml, count=1)

    parts[part] = xml.encode('utf-8')
    report.append((name, dropped, len(blocks), len(out)))

tmp = WORKBOOK + '.tmp'
with zipfile.ZipFile(WORKBOOK) as zsrc, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zsrc.infolist():
        zout.writestr(item, parts.get(item.filename) or zsrc.read(item.filename))
shutil.move(tmp, WORKBOOK)

for name, dropped, before, after in report:
    print(f'{name!r}: {before-1} data rows -> {after-1}  ({len(dropped)} removed)')
    for doi, num, oldrow in dropped:
        print(f'   dropped row {oldrow:5}  Number={num:6}  {doi}')
