import unittest
from datetime import datetime, timedelta, timezone
from math import sqrt

from tech_uncovered.scoring import score_videos
from tech_uncovered.settings import Settings

NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)


def video(i, views=100000, age=20, duration=100, channel='one', **changes):
    row = dict(video_id=str(i), channel_id=channel, channel=channel, title='Title',
               published_at=(NOW-timedelta(days=age)).isoformat(), observed_at=NOW.isoformat(),
               views=views, likes=None, comments=None, duration_seconds=duration,
               available=True, is_live=False, url='https://example.invalid/'+str(i))
    row.update(changes)
    return row


class ScoringTests(unittest.TestCase):
    def score(self, rows):
        return score_videos(rows, Settings())[0]

    def test_known_formula(self):
        rows = self.score([video(i) for i in range(10)] + [video(10, 200000, 10)])
        hot = rows[-1]
        self.assertEqual(hot['baseline_median_views'], 100000)
        self.assertEqual(hot['baseline_median_views_per_day'], 5000)
        self.assertEqual(hot['outlier_ratio'], 2)
        self.assertEqual(hot['velocity_ratio'], 4)
        self.assertAlmostEqual(hot['velocity_adjusted_score'], sqrt(8))
        self.assertTrue(hot['is_outlier'])
        self.assertEqual(hot['rank'], 1)

    def test_below_threshold_all_scores_null(self):
        for row in self.score([video(i) for i in range(9)]):
            for key in ('outlier_ratio','velocity_ratio','velocity_adjusted_score','percentile'):
                self.assertIsNone(row[key])
            self.assertEqual(row['eligibility_reason'], 'insufficient_baseline_sample')
            self.assertEqual(row['baseline_sample_size'], 9)

    def test_provisional_excluded_even_with_large_views(self):
        rows = self.score([video(i) for i in range(10)] + [video(10, 100000000, .99)])
        self.assertEqual(rows[-1]['eligibility_reason'], 'under_24_hours')
        self.assertTrue(rows[-1]['provisional'])
        self.assertIsNone(rows[-1]['rank'])
        self.assertIsNone(rows[-1]['velocity_adjusted_score'])
        self.assertEqual(rows[0]['baseline_sample_size'], 10)

    def test_age_boundaries(self):
        rows = self.score([video(i) for i in range(10)] + [video('day',age=1),video('old',age=90),video('too-old',age=91),video('future',age=-1)])
        self.assertEqual(rows[-4]['eligibility_reason'], 'eligible')
        self.assertEqual(rows[-3]['eligibility_reason'], 'eligible')
        self.assertEqual(rows[-2]['eligibility_reason'], 'outside_lookback')
        self.assertEqual(rows[-1]['eligibility_reason'], 'future_publish_date')

    def test_cohorts_and_channels_do_not_mix(self):
        rows = self.score([video(i) for i in range(10)] + [video('long',duration=181), video('other',channel='two')])
        self.assertEqual(rows[-1]['baseline_sample_size'], 1)
        self.assertIsNone(rows[-1]['velocity_adjusted_score'])
        self.assertIsNone(rows[-2]['velocity_adjusted_score'])
        self.assertEqual(rows[0]['baseline_sample_size'], 10)

    def test_zero_baseline(self):
        rows = self.score([video(i, views=0) for i in range(10)])
        self.assertEqual(rows[0]['eligibility_reason'], 'zero_baseline_median')
        self.assertIsNone(rows[0]['outlier_ratio'])

    def test_zero_views_valid_against_positive_baseline(self):
        row = self.score([video(i) for i in range(10)]+[video('zero',views=0)])[-1]
        self.assertEqual(row['velocity_adjusted_score'], 0)
        self.assertEqual(row['eligibility_reason'], 'eligible')

    def test_missing_live_unavailable_bad_duration(self):
        special = [video('missing',views=None),video('live',is_live=True),
                   video('gone',available=False),video('duration',duration=None)]
        rows = self.score([video(i) for i in range(10)] + special)
        self.assertEqual([r['eligibility_reason'] for r in rows[-4:]],
                         ['missing_or_invalid_views','live_or_upcoming','unavailable','missing_or_invalid_duration'])

    def test_even_median_and_tied_percentile(self):
        rows = self.score([video(i, views=100 if i < 5 else 200) for i in range(10)])
        self.assertEqual(rows[0]['baseline_median_views'],150)
        self.assertEqual(rows[0]['percentile'],25)
        self.assertEqual(rows[-1]['percentile'],75)

    def test_tie_ranks_are_stable(self):
        a = self.score([video(i) for i in range(10)])
        b = self.score([video(i) for i in reversed(range(10))])
        self.assertEqual({r['video_id']:r['rank'] for r in a}, {r['video_id']:r['rank'] for r in b})

    def test_cached_observation_age_unchanged(self):
        rows = self.score([video(i) for i in range(10)])
        self.assertEqual(rows[0]['age_days'],20)
        self.assertEqual(rows[0]['views_per_day'],5000)
