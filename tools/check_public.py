#!/usr/bin/env python3
"""Reject private execution artifacts and common secret formats in public source."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DENIED_NAMES = {'TEST-RESULTS.json', 'COMMAND-AUDIT.json', 'WALKTHROUGH.txt', '.env'}
PLACEHOLDERS = ('sk-unit-test-placeholder', 'sk-test-not-a-real-credential')
PATTERNS = {
    'provider credential': r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})',
    'private key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'provider request ID': r'\b(?:msg|req)_[A-Za-z0-9]{12,}',
    'personal home path': r'/Users/[A-Za-z0-9_.-]+/',
    'workstation hostname': r'[A-Za-z0-9-]+\.local\b',
    'Azure resource identity': r'/subscriptions/[0-9a-fA-F-]{36}/',
}

def main():
    findings = []
    for path in ROOT.rglob('*'):
        rel = path.relative_to(ROOT)
        if any(part in {'.git', '__pycache__', 'dist', '_site'} for part in rel.parts) or not path.is_file():
            continue
        if path.name in DENIED_NAMES or path.name.endswith(('.invite.json', '.pem', '.pfx', '.p12', '.bundle', '.log')):
            findings.append((str(rel), 'private artifact'))
        if path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.pyc'}:
            continue
        text = path.read_text()
        for placeholder in PLACEHOLDERS:
            text = text.replace(placeholder, 'TEST_PLACEHOLDER')
        for label, pattern in PATTERNS.items():
            if re.search(pattern, text):
                findings.append((str(rel), label))
    if findings:
        for path, reason in findings:
            print(f'FAIL: {path}: {reason}')
        raise SystemExit(1)
    print('PASS: no private execution files, common credential formats or personal execution identifiers found.')

if __name__ == '__main__':
    main()
