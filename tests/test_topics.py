import unittest
from tech_uncovered.topics import DictionaryTopicClassifier, group_topics


class TopicTests(unittest.TestCase):
    def test_case_alias_boundary(self):
        classifier=DictionaryTopicClassifier({'Models':['gpt','claude'],'Code':['rust']})
        self.assertEqual(classifier.classify({'title':'GPT-5 and CLAUDE'}),['Models'])
        self.assertEqual(classifier.classify({'title':'Trust the system'}),[])

    def test_recurrence_only_qualifying_outliers(self):
        classifier=DictionaryTopicClassifier({'Models':['gpt']})
        def row(i, hot=True):
            return dict(video_id=str(i),title='GPT',channel='C',url='url',rank=i,
                        velocity_adjusted_score=3,is_outlier=hot)
        self.assertEqual(group_topics([row(1)],classifier),[])
        result=group_topics([row(1),row(2),row(3,False)],classifier)
        self.assertEqual(result[0]['video_count'],2)
        self.assertNotIn('title',result[0]['evidence'][0])

    def test_classifier_can_be_replaced(self):
        class Replacement:
            name='replacement'
            version='1'
            def classify(self,video): return ['Custom']
        rows=[dict(video_id=str(i),channel='c',url='url',rank=i,velocity_adjusted_score=3,is_outlier=True) for i in (1,2)]
        self.assertEqual(group_topics(rows,Replacement())[0]['theme'],'Custom')
