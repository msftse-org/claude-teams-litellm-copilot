#!/usr/bin/env python3
"""Offline checks for the distributable package; no provider requests or credentials."""
import ast
import json
import re
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class Guide(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.anchors = []
        self.images = []
        self.external = []
        self.journeys = []
        self.buttons = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.append(a['id'])
        if tag == 'a' and a.get('href', '').startswith('#'):
            self.anchors.append(a['href'][1:])
        if tag == 'img' and a.get('src'):
            self.images.append(a['src'])
        if tag in ('script', 'link') and (a.get('src') or a.get('href')):
            self.external.append(a)
        if 'data-journey' in a:
            self.journeys.append(a)
        if 'data-role' in a:
            self.buttons.append(a)

def main():
    for p in ROOT.rglob('*.py'):
        ast.parse(p.read_text(), feature_version=(3, 10))
    for p in ROOT.rglob('*.json'):
        if '.git' not in p.parts:
            json.loads(p.read_text())
    subprocess.run(['sh', '-n', str(ROOT / 'setup')], check=True)
    page = (ROOT / 'START-HERE.html').read_text()
    guide = Guide()
    guide.feed(page)
    assert len(guide.ids) == len(set(guide.ids)), 'Duplicate HTML IDs'
    assert set(guide.anchors) <= set(guide.ids), 'Broken section anchor'
    assert not guide.external, 'Guide must be self-contained'
    assert len(guide.images) == 3 and all(x.startswith('data:image/png;base64,') for x in guide.images)
    assert {x['data-journey'] for x in guide.journeys} == {'admin', 'developer'}
    assert all('hidden' in x for x in guide.journeys), 'No journey may be selected initially'
    assert len(guide.buttons) == 2 and all(x.get('aria-pressed') == 'false' for x in guide.buttons)
    with tempfile.TemporaryDirectory() as temp:
        scripts = re.findall(r'<script>(.*?)</script>', page, re.S)
        for i, source in enumerate(scripts):
            p = Path(temp) / f'guide-{i}.js'
            p.write_text(source)
            subprocess.run(['node', '--check', str(p)], check=True)
    for doc in [ROOT / 'README.md', ROOT / 'docs/CONFIGURATION.md']:
        for target in re.findall(r'\]\(([^)]+)\)', doc.read_text()):
            if '://' not in target and not target.startswith('#'):
                assert (doc.parent / target.split('#')[0]).exists(), f'Broken file link: {target}'
    assert not list(ROOT.rglob('*.invite.json')), 'Invitation found in package'
    print('PASS: Python 3.10 syntax, JSON, shell, inline JavaScript, guide assets/roles/anchors and documentation file links.')

if __name__ == '__main__':
    main()
