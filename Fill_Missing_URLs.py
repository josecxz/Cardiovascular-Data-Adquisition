"""Fill in the article URL for Research Square rows that have a DOI but no URL.

The URL is derived from the DOI (10.21203/rs.3.rs-NNNN/v1 ->
researchsquare.com/article/rs-NNNN/v1) and then CHECKED against the live page before
being written: the page's own DOI must match the row's DOI. Nothing is written on a
mismatch, a non-200, or a DOI whose slug cannot be derived (the older rs.2.* records use
an unrelated slug).

Applies to every sheet that carries a URL column. Re-running is a no-op.
"""
import json, re, shutil, sys, zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

sys.path.insert(0, '.')
from Get_V1_Publish_Dates import make_session

WORKBOOK = 'medRxiv and RS CV preprints data analysis 06_30 - Dates Fixed.xlsx'
RS_PREFIX = '10.21203/'
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
CELL_RE = re.compile(r'<c r="([A-Z]+)(\d+)".*?(?:/>|</c>)', re.S)

SHEETS = [('xl/worksheets/sheet1.xml', 'Research Square',        'B', 'G'),
          ('xl/worksheets/sheet3.xml', 'Combined Raw Data',      'B', 'G'),
          ('xl/worksheets/sheet4.xml', 'Final analytic dataset', 'B', 'H')]

zin = zipfile.ZipFile(WORKBOOK)
shared = [''.join(t.text or '' for t in si.iter(NS + 't'))
          for si in ET.fromstring(zin.read('xl/sharedStrings.xml'))]
session = make_session()
verified = {}          # doi -> confirmed url (checked once, reused across sheets)


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


def derive_url(doi):
    stem = doi.rsplit('/', 1)[0]                       # 10.21203/rs.3.rs-124308
    ver = doi.rsplit('/', 1)[1]                        # v1
    slug = stem.split('/', 1)[1] if '/' in stem else ''
    if 'rs.3.' not in slug:
        return None                                    # old rs.2.* slug is not derivable
    return f'https://www.researchsquare.com/article/{slug.split("rs.3.")[-1]}/{ver}'


def confirm(doi):
    """Only return a URL whose page reports the same DOI as the row."""
    if doi in verified:
        return verified[doi]
    url = derive_url(doi)
    ok = None
    if url:
        try:
            r = session.get(url, timeout=45)
            if r.status_code == 200:
                m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                              r.text, re.S)
                if m:
                    page_doi = json.loads(m.group(1))['props']['pageProps']['initialData'].get('doi')
                    if (page_doi or '').strip() == doi:
                        ok = url
                    else:
                        print(f'   !! {doi}: page reports {page_doi!r}, not writing')
            else:
                print(f'   !! {doi}: HTTP {r.status_code}, not writing')
        except Exception as e:
            print(f'   !! {doi}: {e}, not writing')
    else:
        print(f'   !! {doi}: URL not derivable from this DOI format, not writing')
    verified[doi] = ok
    return ok


parts, report = {}, []
for part, name, doi_col, url_col in SHEETS:
    xml = zin.read(part).decode('utf-8')
    filled = []

    def fix_row(m, doi_col=doi_col, url_col=url_col, filled=filled):
        row = m.group(0)
        rnum = int(re.search(r'<row r="(\d+)"', row).group(1))
        if rnum == 1:
            return row
        doi = cell_text(row, doi_col).strip()
        if not doi.startswith(RS_PREFIX) or cell_text(row, url_col).strip():
            return row
        url = confirm(doi)
        if not url:
            return row
        cell = f'<c r="{url_col}{rnum}" t="inlineStr"><is><t>{escape(url)}</t></is></c>'
        after = next((c for c in CELL_RE.finditer(row)
                      if col_index(c.group(1)) > col_index(url_col)), None)
        row = (row[:after.start()] + cell + row[after.start():] if after
               else row[:row.rindex('</row>')] + cell + '</row>')
        filled.append((rnum, doi, url))
        return row

    xml, _ = re.subn(r'<row r="\d+".*?</row>', fix_row, xml, flags=re.S)
    parts[part] = xml.encode('utf-8')
    report.append((name, filled))

tmp = WORKBOOK + '.tmp'
with zipfile.ZipFile(WORKBOOK) as zsrc, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zsrc.infolist():
        zout.writestr(item, parts.get(item.filename) or zsrc.read(item.filename))
shutil.move(tmp, WORKBOOK)

for name, filled in report:
    print(f'{name!r}: {len(filled)} URLs filled')
    for rnum, doi, url in filled:
        print(f'   row {rnum:5} {doi:32} {url}')
