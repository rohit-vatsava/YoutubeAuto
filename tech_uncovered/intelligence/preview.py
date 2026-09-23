"""Read-only persisted Intelligence preview: no provider initialization or calls."""
import json
import sqlite3
from .reports import clean


def preview(path, radar_run_id=None, top=20):
    if top <= 0:
        raise ValueError('--top must be positive')
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT intelligence_run_id FROM intelligence_runs WHERE expired=0 '
                         "AND status='complete' AND (? IS NULL OR radar_run_id=?) ORDER BY rowid DESC LIMIT 1",
                         (radar_run_id, radar_run_id)).fetchone()
        if not row:
            raise ValueError('No complete unexpired Intelligence run; run intelligence --offline first')
        ideas = [json.loads(r[0]) for r in db.execute(
            'SELECT payload FROM idea_candidates WHERE intelligence_run_id=?', row)]
    ideas.sort(key=lambda i: (i.get('rank') is None, i.get('rank') or 0, -i['idea_score'], i['idea_id']))
    lines = [f'Intelligence run: {row[0]} (read-only; zero network/model calls)', '',
             '| Rank | Idea ID | Idea score | Idea researchability | Source researchability | Canonical subject | Named entities | Alleged event | Market cohort | Production fit | Source title | Source channel | Review status | Unresolved fields |',
             '| ' + ' | '.join(['---'] * 14) + ' |']
    for i in ideas[:top]:
        sources = i.get('source_opportunities', [])
        def joined(key):
            return '; '.join(dict.fromkeys(str(s.get(key, 'unknown')) for s in sources)) or 'unknown'
        unresolved = sorted({k for b in i.get('story_context', []) for k in b.get('unknown_reasons', {})})
        unresolved += i.get('required_research', [])
        values = [i.get('rank') or '—', i['idea_id'], round(i['idea_score'],2),
                  i.get('idea_researchability_score'), i.get('source_researchability_score'),
                  i.get('canonical_subject') or i['topic'], ', '.join(i.get('named_entities', [])),
                  i.get('alleged_event') or 'unknown', joined('market_cohort'), joined('production_fit'),
                  joined('title'), joined('channel'), i.get('review_status', i['category']), '; '.join(unresolved)]
        lines.append('| ' + ' | '.join(clean(v) for v in values) + ' |')
    return '\n'.join(lines)
