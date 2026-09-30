import copy,json,unittest
from tests import test_editorial_revision as helpers
from tests.m3_golden import NOW
from tech_uncovered.scripting.editorial_revision import apply_edits,create,load

class SentenceMoveTests(unittest.TestCase):
    def setUp(self):
        helpers.EditorialRevisionTests.setUp(self)
        self.first=self.old['sections'][1]['sentences'][0]['sentence_id']
        self.last=self.old['sections'][1]['sentences'][-1]['sentence_id']
    def move(self,sid=None,section=None,anchor=None):
        return {'sentence_id':sid or self.last,'target_section':section or self.old['sections'][1]['name'],'before_sentence_id':anchor or self.first}
    def test_move_text_combination_append_only(self):
        before={p.name:p.read_bytes() for p in self.folder.iterdir() if p.is_file()}
        edits=dict(self.edits,sentence_moves=[self.move()])
        manifest,path=create(self.reports,self.sid,edits,self.db,NOW,self.cfg)
        result=load(self.reports,self.sid,manifest['revision'],self.db,NOW,self.cfg)
        draft=result['draft'];self.assertEqual(draft['sections'][1]['sentences'][0]['sentence_id'],self.last)
        old={r['sentence_id']:r for sec in self.old['sections'] for r in sec['sentences']}
        rows=[r for sec in draft['sections'] for r in sec['sentences']]
        self.assertEqual(len(rows),len({r['sentence_id'] for r in rows}))
        for row in rows:self.assertEqual({k:v for k,v in row.items() if k!='text'},{k:v for k,v in old[row['sentence_id']].items() if k!='text'})
        self.assertEqual(next(r for r in rows if r['sentence_id']==self.first)['text'],self.edits[self.first])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.folder.iterdir() if p.is_file()})
        self.assertEqual(result['scope_validation']['result'],'PASS')
        self.assertEqual(manifest['parent_revision'],1)
        self.assertEqual(result['data']['research_packet'],self.result['packet'])
    def test_cross_section_preserves_object(self):
        original=copy.deepcopy(self.old)
        row=original['sections'][1]['sentences'].pop()
        original['sections'].append({'name':'End','sentences':[row]})
        draft=apply_edits(original,{'sentence_moves':[self.move()]},self.cfg)
        self.assertEqual(draft['sections'][1]['sentences'][0],row)
        self.assertEqual(draft['sections'][-1]['sentences'],[])
        self.assertEqual(original['sections'][-1]['sentences'],[row])
    def test_invalid_moves(self):
        for moves in ([self.move(sid='missing')],[self.move(section='missing')],[self.move(anchor='missing')],
                      [self.move(anchor=self.last)],[self.move(),self.move()],
                      [self.move(sid='selected-hook')],[self.move(section='HOOK',anchor='selected-hook')],
                      [dict(self.move(),after_sentence_id=self.first)],{'bad':'type'}):
            with self.subTest(moves=moves),self.assertRaises(ValueError):apply_edits(self.old,{'sentence_moves':moves},self.cfg)
    def test_duplicate_existing_ids_rejected(self):
        original=copy.deepcopy(self.old);original['sections'][1]['sentences'].append(copy.deepcopy(original['sections'][1]['sentences'][0]))
        with self.assertRaisesRegex(ValueError,'duplicate'):apply_edits(original,{'sentence_moves':[self.move()]},self.cfg)
    def test_anchor_in_other_section_rejected(self):
        with self.assertRaisesRegex(ValueError,'anchor'):apply_edits(self.old,{'sentence_moves':[self.move(anchor='selected-hook')]},self.cfg)
    def test_text_only_unchanged_behavior(self):
        draft=apply_edits(self.old,self.edits,self.cfg)
        self.assertEqual([r['sentence_id'] for sec in draft['sections'] for r in sec['sentences']],[r['sentence_id'] for sec in self.old['sections'] for r in sec['sentences']])
