"""Atomic, profile-specific local drafts. API keys never enter a draft."""
from pathlib import Path
import base64
import hashlib
import json
import os


class DraftStore:
    def __init__(self, profile, directory=None):
        directory = Path(directory) if directory else Path(__file__).parent / 'user_files' / 'drafts'
        self.path = directory / (hashlib.sha256(profile.encode('utf-8')).hexdigest()[:20] + '.json')

    def save(self, payload):
        data = dict(payload, schema=1)
        data['rows'] = [dict(f=r['f'], q=r.get('q', {}), sel=bool(r.get('sel')),
                             img={k: base64.b64encode(v).decode('ascii') for k, v in r.get('img', {}).items() if v})
                        for r in payload.get('rows', [])]
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
        if len(raw) > 64 * 1024 * 1024:
            raise ValueError('Draft is larger than 64 MB')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_bytes(raw)
        os.replace(temporary, self.path)

    def load(self):
        if not self.path.exists():
            return None
        if self.path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError('Draft is larger than 64 MB')
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('schema') != 1 or not isinstance(data.get('rows'), list):
            raise ValueError('Unsupported draft format')
        for r in data['rows']:
            r['img'] = {k: base64.b64decode(v, validate=True) for k, v in r.get('img', {}).items()}
            r.update(cands={}, thumbs={})
        return data

    def clear(self):
        self.path.unlink(missing_ok=True)
