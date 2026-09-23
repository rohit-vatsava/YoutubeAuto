import json
from pathlib import Path
from tech_uncovered.intelligence.storage import persist
from tech_uncovered.scripting.selection import select_ideas
from tech_uncovered.scripting.costs import Budget
from tech_uncovered.scripting.pipeline import run
from tech_uncovered.scripting.providers.fixtures import *
ROOT=Path(__file__).resolve().parents[1]


def fixture(name='sufficient_research.json'):return json.loads((ROOT/'fixtures/scripts'/name).read_text())
def config():return json.loads((ROOT/'config/script.json').read_text())
def selected(db):
    seed=json.loads((ROOT/'fixtures/scripts/intelligence.json').read_text());persist(db,seed)
    return select_ideas(db,seed['intelligence_run_id'])[0]
def execute(db,bundle=None,choice=None,cfg=None,**overrides):
    bundle=bundle or fixture();cfg=cfg or config();choice=choice or selected(db)
    parts={'provider':FixtureResearchProvider(bundle),'synthesizer':FixtureResearchSynthesizer(bundle),
           'generator':FixtureScriptGenerator(bundle),'checker':FixtureScriptFactChecker(bundle),'reviewer':FixtureQualityReviewer(bundle),
           'budget':Budget(cfg,offline=True)}
    parts.update(overrides)
    return run(db,choice,cfg,now=bundle['as_of'],mode='synthetic',**parts)
