"""Capture the public documents named by reviewed JobBench technical-writer tasks."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import urllib.request
from scripts.source_world_calibration import save, sha
from worldlab.references import extract, ReferenceLibrary

SOURCES = [
    {'id': 'swagger_markdown_example', 'title': 'azagniotov: REST API documentation in Markdown',
     'source_url': 'https://gist.github.com/azagniotov/a4b16faf0febd12efbc6c3d7370383a6',
     'fetch_url': 'https://api.github.com/gists/a4b16faf0febd12efbc6c3d7370383a6/c9cfbc9fd436a76e82abfd50491c3429b3fd77a7',
     'extractor': {'kind': 'github_gist', 'file': 'beautiful.rest.api.docs.in.markdown.md'},
     'source_revision': 'c9cfbc9fd436a76e82abfd50491c3429b3fd77a7'},
    {'id': 'google_style_highlights', 'title': 'Google developer documentation style guide: Highlights',
     'source_url': 'https://developers.google.com/style/highlights',
     'fetch_url': 'https://developers.google.com/style/highlights',
     'extractor': {'kind': 'html_element', 'tag': 'div', 'attribute': 'class', 'value': 'devsite-article-body'}},
    {'id': 'microsoft_reference_guidelines', 'title': 'Microsoft Writing Style Guide: Reference documentation',
     'source_url': 'https://learn.microsoft.com/en-us/style-guide/developer-content/reference-documentation',
     'fetch_url': 'https://learn.microsoft.com/en-us/style-guide/developer-content/reference-documentation',
     'extractor': {'kind': 'html_element', 'tag': 'main', 'attribute': 'id', 'value': 'main'}},
]


def build(out):
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    save(out / 'PLAN.json', {'sources': SOURCES, 'operator_sha256': sha(Path(__file__)),
        'scope': 'Public reference snapshots only. No task answers, evaluator rubrics or model-generated reference summaries.'})
    def fetch(source):
        root = out / source['id']; root.mkdir()
        request = urllib.request.Request(source['fetch_url'], headers={'User-Agent': 'Big-World-CL-reference-capture/1'})
        with urllib.request.urlopen(request, timeout=45) as response:
            if response.status != 200: raise ValueError('Reference fetch did not succeed')
            raw = response.read()
            receipt = {'status': response.status, 'final_url': response.geturl(),
                       'headers': {k: response.headers.get(k) for k in ('Content-Type', 'ETag', 'Last-Modified')}}
        (root / 'raw.bin').write_bytes(raw)
        text = extract(raw, source['extractor'])
        (root / 'content.txt').write_bytes(text.encode('utf-8'))
        row = {**source, 'fetched_at': datetime.now(timezone.utc).isoformat(), **receipt,
               'raw_path': str((root / 'raw.bin').relative_to(out)),
               'content_path': str((root / 'content.txt').relative_to(out)),
               'raw_sha256': sha(root / 'raw.bin'), 'content_sha256': sha(root / 'content.txt')}
        save(root / 'FETCH.json', row)
        return row
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(fetch, SOURCES))
    save(out / 'MANIFEST.json', {'version': 1, 'references': rows})
    library = ReferenceLibrary(out)
    save(out / 'VERIFIED.json', {'ok': True, 'identity': library.identity(),
        'plan_sha256': sha(out / 'PLAN.json'),
        'scope': 'Complete declared article elements / original Markdown verified against retained raw sources; no live-web capability claim.'})
    return {'root': str(out), 'references': len(rows), 'manifest_sha256': sha(out / 'MANIFEST.json'),
            'content_bytes': {row['id']: (out / row['content_path']).stat().st_size for row in rows}}


if __name__ == '__main__':
    import json
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--out', type=Path, required=True)
    print(json.dumps(build(p.parse_args().out), indent=2))
