"""模拟真实分页的漏抓回归：不用真实账号或私密评论作为夹具。"""
import contextlib
import io
import unittest
import weread_notes as w


class LikedCoverageTests(unittest.TestCase):
    def run_scan(self, client, chapters):
        with contextlib.redirect_stdout(io.StringIO()):
            return client.liked_thoughts('b', chapters, [], set())

    def detail(self, rid, liked):
        return {'reviewId': rid, 'review': {'bookId': 'b', 'isLike': int(liked),
                                          'content': 'fixture', 'author': {'userVid': 456}}}

    def test_candidate_budget_cannot_hide_positive_hint_in_later_range(self):
        client = w.Weread(api_key='wrk-fixture', max_review_checks=1)
        checked = []
        def request(path, params=None, **kwargs):
            if path == '/book/bestbookmarks':
                return {'items': [{'range': '1-10'}, {'range': '11-20'}]}
            if path == '/book/underlines':
                return {'underlines': []}
            if path == '/book/readreviews':
                span = params['reviews'][0]['range']
                rows = ([{'reviewId': f'456_early{i}', 'review': {'isLike': 0}} for i in range(5)]
                        if span == '1-10' else [{'reviewId': '456_late', 'review': {'isLike': 1}}])
                return {'reviews': [{'range': span, 'hasMore': 0, 'pageReviews': rows}]}
            checked.append(params['reviewId'])
            return self.detail(params['reviewId'], True)
        client.request = request
        rows, _ = self.run_scan(client, [{'chapterUid': 1}])
        self.assertEqual(checked, ['456_late'])
        self.assertEqual(rows[0]['reviewId'], '456_late')
        self.assertEqual(client.last_liked_scan['visited_ranges'], 2)
        self.assertEqual(client.last_liked_scan['unchecked_candidates'], 5)

    def test_default_checks_candidates_after_number_200(self):
        client = w.Weread(api_key='wrk-fixture')
        checked = []
        def request(path, params=None, **kwargs):
            if path == '/book/bestbookmarks':
                return {'items': [{'range': '1-10'}]}
            if path == '/book/underlines':
                return {'underlines': []}
            if path == '/book/readreviews':
                offset = params['reviews'][0]['maxIdx']
                rows = [{'reviewId': f'456_{i}', 'review': {}} for i in range(offset, offset + 20)]
                return {'reviews': [{'range': '1-10', 'pageReviews': rows, 'hasMore': int(offset < 200),
                                     'maxIdx': offset + 20, 'synckey': 0}]}
            rid = params['reviewId']
            checked.append(rid)
            return self.detail(rid, rid == '456_219')
        client.request = request
        rows, _ = self.run_scan(client, [{'chapterUid': 1}])
        self.assertEqual(len(checked), 220)
        self.assertEqual([r['reviewId'] for r in rows], ['456_219'])
        self.assertTrue(client.last_liked_scan['complete_within_known_ranges'])
        self.assertFalse(client.last_liked_scan['full_book_complete'])

    def test_underlines_discovers_range_outside_popular_top20(self):
        client = w.Weread(api_key='wrk-fixture')
        def request(path, params=None, **kwargs):
            if path == '/book/bestbookmarks':
                return {'items': []}
            if path == '/book/underlines':
                return {'underlines': [{'range': '100-110'}]}
            if path == '/book/readreviews':
                return {'reviews': [{'range': '100-110', 'hasMore': 0,
                                     'pageReviews': [{'reviewId': '456_nonpopular', 'review': {'isLike': 1}}]}]}
            return self.detail(params['reviewId'], True)
        client.request = request
        rows, _ = self.run_scan(client, [{'chapterUid': 2}])
        self.assertEqual([r['reviewId'] for r in rows], ['456_nonpopular'])

    def test_later_chapter_first_page_precedes_early_range_second_page(self):
        client = w.Weread(api_key='wrk-fixture', max_pages=2)
        visited = []
        def request(path, params=None, **kwargs):
            if path == '/book/bestbookmarks':
                return {'items': [{'range': '1-10'}]}
            if path == '/book/underlines':
                return {'underlines': []}
            if path == '/book/readreviews':
                uid = params['chapterUid']
                visited.append((uid, params['reviews'][0]['maxIdx']))
                return {'reviews': [{'range': '1-10', 'hasMore': int(uid == 1), 'maxIdx': 20,
                                     'pageReviews': [{'reviewId': f'456_ch{uid}', 'review': {}}]}]}
            return self.detail(params['reviewId'], params['reviewId'] == '456_ch2')
        client.request = request
        rows, _ = self.run_scan(client, [{'chapterUid': 1}, {'chapterUid': 2}])
        self.assertEqual(visited, [(1, 0), (2, 0)])
        self.assertEqual([r['reviewId'] for r in rows], ['456_ch2'])
        self.assertTrue(client.last_liked_scan['pending_pages'])
        self.assertFalse(client.last_liked_scan['complete_within_known_ranges'])

    def test_range_limit_is_shared_between_chapters(self):
        client = w.Weread(api_key='wrk-fixture', max_review_ranges=2)
        chapters_visited = []
        def request(path, params=None, **kwargs):
            if path == '/book/bestbookmarks':
                return {'items': [{'range': '1-10'}, {'range': '11-20'}, {'range': '21-30'}]}
            if path == '/book/underlines':
                return {'underlines': []}
            if path == '/book/readreviews':
                chapters_visited.append(params['chapterUid'])
                return {'reviews': [{'range': params['reviews'][0]['range'], 'hasMore': 0, 'pageReviews': []}]}
            raise AssertionError(path)
        client.request = request
        self.run_scan(client, [{'chapterUid': 1}, {'chapterUid': 2}])
        self.assertEqual(chapters_visited, [1, 2])
        self.assertEqual(client.last_liked_scan['known_ranges'], 6)
        self.assertEqual(client.last_liked_scan['scheduled_ranges'], 2)
        self.assertFalse(client.last_liked_scan['complete_within_known_ranges'])


if __name__ == '__main__':
    unittest.main()
