import unittest
from tech_uncovered.scripting.pivot_scope import classify,FAILURES
from tech_uncovered.scripting.scope_language import production_direction

class VisualProductionScopeTests(unittest.TestCase):
    def check_text(self,text):
        return classify({'text':text,'factual':False,'surface':'visual_notes/0'},
                        {'topic':'GPT-6 Astra','claims':[],'source_records':[]})

    def test_pure_choreography_is_nonfactual(self):
        for text in ('Use a two-card layout.',
                     'Keep the two existing on-screen text elements visually separate.',
                     'Fade the existing card out.','Highlight the existing label.',
                     'Zoom into the existing screenshot.',
                     'Fade the first card out before showing the second.',
                     'Show the existing text one line at a time.',
                     'Use a three-column layout.','Position the existing image on the left.',
                     'Transition to the next frame.'):
            with self.subTest(text=text):
                self.assertEqual(self.check_text(text)['classification'],'NONFACTUAL_EDITORIAL')

    def test_factual_and_mixed_instructions_stay_bound(self):
        for text in ('Show that GPT-6 Astra supports web search.',
                     "Display 'GPT-6 Astra supports web search.'",
                     'Show Astra is reliable.',"Display '5 reasoning settings.'",
                     'Show 2x performance.',
                     'Use a two-card layout showing GPT-6 Astra supports web search.',
                     "Display 'Tools listed for use with the Responses API.'",
                     "Label the card 'Tools supported by GPT-6 Astra.'",
                     'Show that Astra is faster.',
                     'Highlight the existing label proving Astra is safe.',
                     'Show the existing text: Astra launches tomorrow.',
                     'Use a two-card layout. Astra is reliable.'):
            with self.subTest(text=text):
                self.assertFalse(production_direction(text))
                self.assertIn(self.check_text(text)['classification'],FAILURES)

    def test_proposal_sentences_compose_without_claims(self):
        result=self.check_text('Use a two-card layout. Keep the two existing on-screen text elements visually separate.')
        self.assertNotIn(result['classification'],FAILURES)
        self.assertEqual([u['classification'] for u in result['atomic_units']],['NONFACTUAL_EDITORIAL']*2)
