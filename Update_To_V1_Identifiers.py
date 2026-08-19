"""Rewrite Research Square DOIs and URLs from /vN to /v1 on the three data sheets.

Only rows whose DOI names a version later than v1 are touched:

    Research Square         DOI col B, URL col G
    Combined Raw Data       DOI col B, URL col G
    Final analytic dataset  DOI col B, URL col H

Hyperlink relationship targets are rewritten alongside the cell text -- otherwise the
displayed URL would say /v1 while clicking it still opened the old version.

medRxiv rows (DOI prefix 10.1101/) and rows already at /v1 are left alone.

Re-running is a no-op: rows are selected by having a version suffix other than v1.
"""
import re, shutil, zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

WORKBOOK = 'medRxiv and RS CV preprints data analysis 06_30 - Dates Fixed.xlsx'
RS_PREFIX = '10.21203/'
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
VER = re.compile(r'/v(\d+)\s*$')
CELL_RE = re.compile(r'<c r="([A-Z]+)(\d+)".*?(?:/>|</c>)', re.S)

TARGETS = [
    ('xl/worksheets/sheet1.xml', 'Research Square',        'B', 'G'),
    ('xl/worksheets/sheet3.xml', 'Combined Raw Data',      'B', 'G'),
    ('xl/worksheets/sheet4.xml', 'Final analytic dataset', 'B', 'H'),
]

zin = zipfile.ZipFile(WORKBOOK)
shared = [''.join(t.text or '' for t in si.iter(NS + 't'))
          for si in ET.fromstring(zin.read('xl/sharedStrings.xml'))]


def col_index(letters):
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


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


def set_cell(row, col, rnum, text):
    m = re.search(rf'<c r="{col}{rnum}"([^>]*?)(?:/>|>.*?</c>)', row, re.S)
    if m:
        st = re.search(r'\ss="(\d+)"', m.group(1))
        st = f' s="{st.group(1)}"' if st else ''
        cell = f'<c r="{col}{rnum}"{st} t="inlineStr"><is><t>{escape(text)}</t></is></c>'
        return row[:m.start()] + cell + row[m.end():]
    cell = f'<c r="{col}{rnum}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'
    after = next((c for c in CELL_RE.finditer(row)
                  if col_index(c.group(1)) > col_index(col)), None)
    if after:
        return row[:after.start()] + cell + row[after.start():]
    return row[:row.rindex('</row>')] + cell + '</row>'


parts, report = {}, []
for part, name, doi_col, url_col in TARGETS:
    xml = zin.read(part).decode('utf-8')
    stats = {'doi': 0, 'url': 0, 'url_missing': 0, 'url_odd': 0}
    touched_rows = set()

    def fix_row(m, doi_col=doi_col, url_col=url_col, stats=stats, touched=touched_rows):
        row = m.group(0)
        rnum = int(re.search(r'<row r="(\d+)"', row).group(1))
        if rnum == 1:
            return row
        doi = cell_text(row, doi_col).strip()
        if not doi.startswith(RS_PREFIX):
            return row
        ver = VER.search(doi)
        if not ver or int(ver.group(1)) == 1:
            return row

        row = set_cell(row, doi_col, rnum, VER.sub('/v1', doi))
        stats['doi'] += 1
        touched.add(rnum)

        url = cell_text(row, url_col).strip()
        if not url:
            stats['url_missing'] += 1
        elif not VER.search(url):
            stats['url_odd'] += 1                 # no /vN suffix: leave it alone
        else:
            row = set_cell(row, url_col, rnum, VER.sub('/v1', url))
            stats['url'] += 1
        return row

    xml, _ = re.subn(r'<row r="\d+".*?</row>', fix_row, xml, flags=re.S)
    parts[part] = xml.encode('utf-8')

    # Repoint hyperlink targets on the URL column of the rows we just rewrote.
    relname = part.replace('xl/worksheets/', 'xl/worksheets/_rels/') + '.rels'
    rels = zin.read(relname).decode('utf-8')
    links = re.findall(rf'<hyperlink ref="{url_col}(\d+)" r:id="(rId\d+)"', xml)
    fixed = 0
    for rnum, rid in links:
        if int(rnum) not in touched_rows:
            continue
        m = re.search(rf'(Id="{rid}"[^>]*?Target=")([^"]+)(")', rels)
        if m and VER.search(m.group(2)):
            rels = rels[:m.start(2)] + VER.sub('/v1', m.group(2)) + rels[m.end(2):]
            fixed += 1
    parts[relname] = rels.encode('utf-8')
    report.append((name, stats, fixed))

tmp = WORKBOOK + '.tmp'
with zipfile.ZipFile(WORKBOOK) as zsrc, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zsrc.infolist():
        zout.writestr(item, parts.get(item.filename) or zsrc.read(item.filename))
shutil.move(tmp, WORKBOOK)

for name, stats, fixed in report:
    print(f'{name!r}')
    print(f'   DOIs rewritten to /v1      : {stats["doi"]}')
    print(f'   URLs rewritten to /v1      : {stats["url"]}')
    print(f'   hyperlink targets repointed: {fixed}')
    if stats['url_missing']:
        print(f'   !! rows with no URL        : {stats["url_missing"]}')
    if stats['url_odd']:
        print(f'   !! URLs without a version  : {stats["url_odd"]}')
    print()
