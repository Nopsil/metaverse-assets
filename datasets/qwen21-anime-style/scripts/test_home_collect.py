"""Offline checks for the home Pixiv collector, URL merge, and Civitai caps."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from fetch_civitai import adult_pending_rows, cap_showcase_rows
from merge_exports import merge_rows
from pixiv_home import (
    ADULT_R18_QUERIES,
    PETITE_ADULT_QUERIES,
    iter_bookmark_works,
    iter_r18_search,
    row_from_illust_body,
    validate_queries,
)
from pixiv_urls import refs_from_text

HERE = Path(__file__).resolve().parent


def _adult_body(**extra) -> dict:
    body = {
        "id": "150000001",
        "title": "夜",
        "xRestrict": 1,
        "aiType": 1,
        "pageCount": 1,
        "width": 1536,
        "height": 2048,
        "bookmarkCount": 800,
        "userName": "example",
        "userId": "42",
        "tags": {"tags": [{"tag": "オリジナル"}, {"tag": "お姉さん"}, {"tag": "R-18"}]},
        "description": "adult woman",
        "urls": {"small": "https://i.pximg.net/c/540x540_70/example.jpg"},
    }
    body.update(extra)
    return body


class HomeCollectTest(unittest.TestCase):
    def test_queries_are_adult_and_school_is_refused(self):
        validate_queries(ADULT_R18_QUERIES)
        validate_queries(PETITE_ADULT_QUERIES)
        with self.assertRaises(RuntimeError):
            validate_queries(["制服 オリジナル"])
        with self.assertRaises(RuntimeError):
            validate_queries(["つるぺた オリジナル"])

    def test_r18_row_kept_and_secrets_dropped(self):
        row, why = row_from_illust_body(
            _adult_body(urls={"small": "https://i.pximg.net/x.jpg?PHPSESSID=abc"})
        )
        self.assertEqual(why, "pass")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["rating"], "adult")
        self.assertEqual(row["visual_review"], "pending")
        self.assertNotIn("PHPSESSID", json.dumps(row))
        self.assertNotIn("cookie", json.dumps(row).lower())

    def test_blocks_minor_school_gore_and_ai(self):
        self.assertIsNone(row_from_illust_body(_adult_body(title="合法ロリ"))[0])
        self.assertIsNone(row_from_illust_body(_adult_body(description="16yo schoolgirl"))[0])
        self.assertIsNone(row_from_illust_body(_adult_body(title="セーラー服"))[0])
        self.assertEqual(row_from_illust_body(_adult_body(xRestrict=2))[1], "r18g")
        self.assertEqual(row_from_illust_body(_adult_body(aiType=2))[1], "ai_generated")
        kept, why = row_from_illust_body(_adult_body(aiType=2), include_ai=True)
        self.assertEqual(why, "pass", kept)

    def test_safe_mode_stays_all_ages(self):
        row, why = row_from_illust_body(_adult_body(xRestrict=0))
        self.assertEqual(why, "pass")
        assert row is not None
        self.assertEqual(row["rating"], "all-ages")

    def test_r18_search_does_not_keep_safe_standins(self):
        def fetch(_url: str) -> dict:
            return {"error": False, "body": {"illust": {"data": [{"id": "5", "xRestrict": 0}]}}}

        found, masked = iter_r18_search(fetch, ["お姉さん オリジナル"], pages=2, limit=10)
        self.assertEqual(found, [])
        self.assertGreaterEqual(masked, 1)

    def test_r18_search_keeps_restricted_ids(self):
        def fetch(_url: str) -> dict:
            return {
                "error": False,
                "body": {"illust": {"data": [{"id": "9", "xRestrict": 1}, {"id": "9", "xRestrict": 1}]}},
            }

        found, masked = iter_r18_search(fetch, ["熟女 オリジナル"], pages=1, limit=10)
        self.assertEqual(masked, 0)
        self.assertEqual([item["id"] for item in found], ["9"])

    def test_bookmarks_need_a_numeric_user(self):
        with self.assertRaises(RuntimeError):
            iter_bookmark_works(lambda _url: {}, "me", rest="show", limit=5)

        def fetch(url: str) -> dict:
            if "offset=0" in url:
                return {"body": {"works": [{"id": "9"}], "total": 1}}
            return {"body": {"works": [], "total": 1}}

        works = iter_bookmark_works(fetch, "42", rest="show", limit=10)
        self.assertEqual(works, [{"id": "9"}])


class DedicatedProfileTest(unittest.TestCase):
    def test_refuses_system_chrome_and_repo_paths(self):
        from chrome_profile import (
            assert_dedicated_profile,
            default_dedicated_profile,
            is_system_chrome_path,
            system_chrome_user_data,
            validate_proxy,
        )

        system = system_chrome_user_data()
        self.assertTrue(is_system_chrome_path(system))
        self.assertTrue(is_system_chrome_path(system / "Default"))
        with self.assertRaises(RuntimeError):
            assert_dedicated_profile(system / "Default", Path("/tmp/not-the-profile"))
        repo = Path(__file__).resolve().parents[1]
        with self.assertRaises(RuntimeError):
            assert_dedicated_profile(repo / "catalog", repo.parents[1])
        dedicated = default_dedicated_profile()
        self.assertFalse(is_system_chrome_path(dedicated))
        self.assertEqual(validate_proxy("http://127.0.0.1:7890"), "http://127.0.0.1:7890")
        with self.assertRaises(RuntimeError):
            validate_proxy("127.0.0.1:7890")


class OriginalUrlTest(unittest.TestCase):
    def test_img_original_only(self):
        from pixiv_originals import is_original_url, originals_for_illust

        original = "https://i.pximg.net/img-original/img/2024/01/01/00/00/00/123_p0.png"
        thumb = "https://i.pximg.net/c/540x540_70/img-master/img/2024/01/01/00/00/00/123_p0_master1200.jpg"
        self.assertTrue(is_original_url(original))
        self.assertFalse(is_original_url(thumb))
        self.assertFalse(is_original_url(original.replace("img-original", "img-master")))
        kept = originals_for_illust(
            {
                "id": "123",
                "title": "夜",
                "illustType": 0,
                "pageCount": 1,
                "xRestrict": 1,
                "tags": {"tags": [{"tag": "お姉さん"}, {"tag": "オリジナル"}]},
                "urls": {"original": original, "regular": thumb},
            }
        )
        self.assertEqual(kept["urls"], [original])
        self.assertEqual(originals_for_illust({"illustType": 2, "title": "loop"})["skip"], "ugoira")
        pages = [{"urls": {"original": original.replace("_p0", f"_p{n}")}} for n in range(5)]
        multi = originals_for_illust(
            {
                "title": "夜",
                "illustType": 0,
                "pageCount": 5,
                "tags": {"tags": [{"tag": "女性"}]},
                "urls": {"original": original},
            },
            pages,
        )
        self.assertEqual(len(multi["urls"]), 3)
        self.assertEqual(multi["truncated"], 2)
        blocked = originals_for_illust(
            {
                "title": "制服",
                "illustType": 0,
                "pageCount": 1,
                "tags": {"tags": [{"tag": "セーラー服"}]},
                "urls": {"original": original},
            }
        )
        self.assertEqual(blocked["urls"], [])
        self.assertTrue(blocked["skip"])
        gore = originals_for_illust(
            {
                "title": "夜",
                "illustType": 0,
                "pageCount": 1,
                "xRestrict": 2,
                "tags": {"tags": [{"tag": "お姉さん"}]},
                "urls": {"original": original},
            }
        )
        self.assertEqual(gore["skip"], "r18g")
        from pixiv_originals import bytes_match_original

        jpeg = (
            b"\xff\xd8\xff\xc0\x00\x11\x08"
            + (2048).to_bytes(2, "big")
            + (1536).to_bytes(2, "big")
            + bytes([3])
            + (b"\x01\x11\x00" * 3)
            + b"\xff\xd9"
        )
        self.assertIsNone(bytes_match_original(jpeg, 1536, 2048))
        self.assertIsNotNone(bytes_match_original(jpeg, 1200, 1200))
        self.assertEqual(bytes_match_original(b"<html>nope</html>", 1536, 2048), "not_image")

    def test_targets_are_pixiv_pages(self):
        from download_pixiv_originals import pixiv_targets

        rows = pixiv_targets(
            [
                {"source": "pixiv", "id": "10", "url": "https://www.pixiv.net/artworks/10"},
                {"source": "civitai", "id": "99", "url": "https://civitai.com/images/99"},
                {"source": "pixiv", "id": "10", "url": "https://www.pixiv.net/en/artworks/10"},
            ]
        )
        self.assertEqual([row["id"] for row in rows], ["10"])


class MergeTest(unittest.TestCase):
    def test_urls_and_dedupe_keep_reviewed_row(self):
        refs = refs_from_text(
            "\n".join(
                [
                    "# comment",
                    "https://www.pixiv.net/artworks/135142899",
                    "https://www.pixiv.net/en/artworks/135142899?s=1",
                    "https://civitai.com/images/118195112",
                    "not a url",
                ]
            )
        )
        self.assertEqual([(ref.source, ref.id) for ref in refs], [("pixiv", "135142899"), ("civitai", "118195112")])

        base = [
            {
                "source": "pixiv",
                "url": "https://www.pixiv.net/artworks/135142899",
                "id": "135142899",
                "title": "伝われ",
                "tags": ["女性", "オリジナル"],
                "rating": "all-ages",
                "visual_review": "thumbnail_pass",
                "keep_reason": "Thumbnail review kept an adult-looking character with no child cue.",
            }
        ]
        incoming = [
            {"url": "https://www.pixiv.net/artworks/135142899", "title": "other", "tags": ["女性"]},
            {"url": "https://www.pixiv.net/artworks/150000001", "title": "夜", "tags": ["お姉さん", "オリジナル"]},
            {"url": "https://www.pixiv.net/artworks/150000002", "title": "bad", "tags": ["合法ロリ", "女の子"]},
            {"url": "https://www.pixiv.net/artworks/150000003"},
            {
                "url": "https://www.pixiv.net/artworks/150000004",
                "title": "kept",
                "tags": ["厚塗り"],
                "screen": "pass",
                "rating": "adult",
                "keep_reason": "no child cue",
            },
        ]
        merged, stats = merge_rows(base, incoming)
        by_id = {row["id"]: row for row in merged}
        self.assertEqual(by_id["135142899"]["visual_review"], "thumbnail_pass")
        self.assertEqual(by_id["135142899"]["title"], "伝われ")
        self.assertEqual(by_id["150000001"]["visual_review"], "pending")
        self.assertNotIn("150000002", by_id)
        self.assertEqual(by_id["150000003"]["rating"], "unreviewed")
        self.assertIn("150000004", by_id)
        self.assertGreaterEqual(stats["duplicate_kept_reviewed"], 1)
        self.assertGreaterEqual(stats["dropped:term:合法ロリ"] + stats["dropped:term:ロリ"], 1)

    def test_civitai_caps(self):
        rows = [
            {"id": "1", "rating": "all-ages", "model_id": "m", "quality": 100},
            {"id": "2", "rating": "adult", "model_id": "m", "quality": 2000},
            {"id": "3", "rating": "adult", "model_id": "m", "quality": 1800},
            {"id": "4", "rating": "adult", "model_id": "m", "quality": 1700},
            {"id": "5", "rating": "adult", "model_id": "m", "quality": 1600},
            {"id": "6", "rating": "adult", "model_id": "m", "quality": 1500},
        ]
        capped = cap_showcase_rows(rows, adult_cap=4, all_ages_cap=2)
        self.assertEqual([row["id"] for row in capped], ["2", "3", "4", "5", "1"])
        pending = adult_pending_rows(rows, {"2"}, cap=10, per_model=2)
        self.assertEqual([row["id"] for row in pending], ["3", "4"])
        self.assertTrue(all(row["visual_review"] == "pending" for row in pending))
        blocked = adult_pending_rows(
            [{"id": "143422745", "rating": "adult", "model_id": "m", "quality": 9}],
            set(),
            cap=5,
            per_model=3,
        )
        self.assertEqual(blocked, [])


class PaceTest(unittest.TestCase):
    def test_page_and_file_pauses_stay_slow_and_uneven(self):
        from pixiv_pace import human_pause

        pages = [human_pause("page") for _ in range(60)]
        files = [human_pause("file") for _ in range(40)]
        self.assertGreaterEqual(min(pages), 3.5)
        self.assertLessEqual(max(pages), 32.0)
        self.assertGreater(max(pages) - min(pages), 2.0)
        self.assertGreaterEqual(min(files), 1.8)
        self.assertLessEqual(max(files), 8.0)
        self.assertLess(min(files), min(pages))


class FlexibleWindowTest(unittest.TestCase):
    def test_shortest_window_wins_and_spans_stay_ordered(self):
        from datetime import date

        from pixiv_home import choose_window_days, flexible_keep_windows, parse_date_windows

        spans = parse_date_windows("7,30,90,180,365")
        self.assertEqual(spans, (7, 30, 90, 180, 365))
        with self.assertRaises(RuntimeError):
            parse_date_windows("365,7")
        with self.assertRaises(RuntimeError):
            parse_date_windows("3")
        windows = flexible_keep_windows(date(2026, 9, 27), spans)
        self.assertEqual(windows[0], (7, "2026-09-20", "2026-09-27"))
        self.assertEqual(windows[-1][0], 365)
        self.assertEqual(windows[-1][2], "2026-09-27")
        self.assertEqual(choose_window_days({7: 4, 30: 48, 90: 80}, 40, spans), 30)
        self.assertEqual(choose_window_days({7: 1, 30: 2, 365: 10}, 40, spans), 365)

    def test_thin_buckets_need_an_adult_setting(self):
        from pixiv_home import queries_for_buckets, thin_bucket_allowed, validate_queries

        slim = queries_for_buckets(["slim"])
        self.assertTrue(slim)
        self.assertTrue(all(bucket == "slim" for bucket, _word in slim))
        validate_queries([word for _bucket, word in slim])
        self.assertFalse(thin_bucket_allowed("slim", ["スレンダー", "オリジナル"], "夜"))
        self.assertTrue(thin_bucket_allowed("slim", ["スレンダー", "お姉さん"], "夜"))
        self.assertTrue(thin_bucket_allowed("curvy", ["巨乳", "オリジナル"], "夜"))


class HotSearchTest(unittest.TestCase):
    def test_popular_url_uses_padded_dates_and_bookmark_floor(self):
        from pixiv_home import canonical_order, hot_search_url, in_date_window

        self.assertEqual(canonical_order("popular"), "popular_d")
        self.assertEqual(canonical_order("人気"), "popular_d")
        url = hot_search_url(
            "お姉さん オリジナル",
            1,
            start_date="2026-04-01",
            end_date="2026-10-31",
            order="popular",
            min_bookmarks=1000,
        )
        self.assertIn("order=popular_d", url)
        self.assertIn("mode=r18", url)
        self.assertIn("type=illust", url)
        self.assertIn("scd=2026-03-31", url)
        self.assertIn("ecd=2026-11-01", url)
        self.assertIn("blt=1000", url)
        self.assertTrue(in_date_window("2026-04-01", "2026-04-01", "2026-10-31"))
        self.assertTrue(in_date_window("2026-10-31", "2026-04-01", "2026-10-31"))
        self.assertFalse(in_date_window("2026-03-31", "2026-04-01", "2026-10-31"))
        self.assertFalse(in_date_window("2026-11-01", "2026-04-01", "2026-10-31"))

    def test_hot_search_keeps_diverse_adults_inside_the_window(self):
        from pixiv_home import hot_query_texts, iter_hot_r18_search, select_hot_rows, validate_queries

        validate_queries(hot_query_texts())
        with self.assertRaises(RuntimeError):
            validate_queries(["ロリ オリジナル"])

        items = [
            {"id": "1", "title": "a", "xRestrict": 1, "illustType": 0, "bookmarkCount": 5000,
             "createDate": "2026-04-01T00:00:00+09:00", "tags": ["巨乳", "女性", "オリジナル"], "userId": "1"},
            {"id": "2", "title": "b", "xRestrict": 0, "illustType": 0, "bookmarkCount": 9000,
             "createDate": "2026-05-01T00:00:00+09:00", "tags": ["お姉さん", "オリジナル"], "userId": "2"},
            {"id": "3", "title": "c", "xRestrict": 1, "illustType": 0, "bookmarkCount": 200,
             "createDate": "2026-05-02T00:00:00+09:00", "tags": ["お姉さん", "オリジナル"], "userId": "3"},
            {"id": "4", "title": "d", "xRestrict": 1, "illustType": 0, "bookmarkCount": 1800,
             "createDate": "2026-03-31T00:00:00+09:00", "tags": ["スレンダー", "女性", "オリジナル"], "userId": "4"},
            {"id": "5", "title": "e", "xRestrict": 1, "illustType": 0, "bookmarkCount": 2200,
             "createDate": "2026-10-31T00:00:00+09:00", "tags": ["貧乳", "お姉さん", "オリジナル"], "userId": "5"},
            {"id": "6", "title": "ラフ", "xRestrict": 1, "illustType": 0, "bookmarkCount": 4000,
             "createDate": "2026-06-01T00:00:00+09:00", "tags": ["落書き", "お姉さん"], "userId": "6"},
            {"id": "7", "title": "f", "xRestrict": 1, "illustType": 2, "bookmarkCount": 3000,
             "createDate": "2026-06-01T00:00:00+09:00", "tags": ["お姉さん", "オリジナル"], "userId": "7"},
            {"id": "8", "title": "合法ロリ", "xRestrict": 1, "illustType": 0, "bookmarkCount": 8000,
             "createDate": "2026-07-01T00:00:00+09:00", "tags": ["ロリ", "オリジナル"], "userId": "8"},
        ]

        def fetch(url: str) -> dict:
            import urllib.parse

            if urllib.parse.quote("貧乳") in url:
                data = [items[4]]
            elif urllib.parse.quote("巨乳") in url:
                data = [items[0], items[1], items[2], items[3], items[5], items[6], items[7]]
            else:
                data = []
            return {"error": False, "body": {"illust": {"data": data}}}

        groups, notes = iter_hot_r18_search(
            fetch, pages=1, start_date="2026-04-01", end_date="2026-10-31", order="popular", min_bookmarks=1000
        )
        kept_ids = [item["id"] for bucket in groups.values() for item in bucket]
        self.assertIn("1", kept_ids)
        self.assertIn("5", kept_ids)
        self.assertNotIn("2", kept_ids)
        self.assertNotIn("3", kept_ids)
        self.assertNotIn("4", kept_ids)
        self.assertNotIn("6", kept_ids)
        self.assertNotIn("7", kept_ids)
        self.assertNotIn("8", kept_ids)
        self.assertEqual(notes["order_sent"], "popular_d")
        self.assertGreaterEqual(notes["search_bookmark_summary"]["max"], 5000)

        rows = []
        for bucket, stubs in groups.items():
            for stub in stubs:
                rows.append({
                    "id": stub["id"],
                    "body_bucket": bucket,
                    "bookmark_count": stub["bookmarkCount"],
                    "user_id": stub["userId"],
                    "rating": "adult",
                })
        for index in range(6):
            rows.append({
                "id": f"9{index}",
                "body_bucket": "curvy",
                "bookmark_count": 4000 - index,
                "user_id": f"c{index}",
                "rating": "adult",
            })
        chosen = select_hot_rows(rows, limit=8, per_bucket=3)
        buckets = [row["body_bucket"] for row in chosen]
        self.assertIn("flat", buckets)
        self.assertLessEqual(buckets.count("curvy"), 7)
        self.assertLessEqual(len(chosen), 8)

    def test_quarantine_moves_weak_pixiv_files_and_keeps_hot_rows(self):
        import tempfile
        from pathlib import Path

        from pixiv_home import quarantine_low_bookmark_pixiv

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            originals = root / "orig"
            quarantine = root / "q"
            originals.mkdir()
            (originals / "10_p0.jpg").write_bytes(b"weak")
            (originals / "11_p0.jpg").write_bytes(b"hot")
            rows = [
                {"source": "pixiv", "id": "10", "quality": 40, "visual_review": "pending", "keep_reason": "old"},
                {"source": "pixiv", "id": "11", "quality": 50, "pool": "hot", "visual_review": "pending"},
                {"source": "pixiv", "id": "12", "quality": 2500, "visual_review": "thumbnail_pass"},
                {"source": "civitai", "id": "13", "quality": 100, "visual_review": "pending"},
            ]
            stats = quarantine_low_bookmark_pixiv(
                rows, min_bookmarks=1000, originals_dir=originals, quarantine_dir=quarantine
            )
            self.assertEqual(stats["quarantined"], 1)
            self.assertEqual(stats["files_moved"], 1)
            self.assertTrue((quarantine / "10_p0.jpg").exists())
            self.assertTrue((originals / "11_p0.jpg").exists())
        self.assertEqual(rows[0]["visual_review"], "quarantine")
        self.assertEqual(rows[1]["pool"], "hot")
        self.assertEqual(rows[2]["visual_review"], "thumbnail_pass")
        self.assertEqual(rows[3]["visual_review"], "pending")

    def test_downloader_skips_quarantine(self):
        from download_pixiv_originals import pixiv_targets

        targets = pixiv_targets([
            {"source": "pixiv", "id": "10", "url": "https://www.pixiv.net/artworks/10", "visual_review": "quarantine"},
            {"source": "pixiv", "id": "12", "url": "https://www.pixiv.net/artworks/12", "status": "deprecated", "visual_review": "thumbnail_pass"},
            {"source": "pixiv", "id": "11", "url": "https://www.pixiv.net/artworks/11", "visual_review": "pending"},
        ])
        self.assertEqual([item["id"] for item in targets], ["11"])

    def test_merge_skips_deprecated_rows(self):
        from merge_exports import merge_rows

        base = [{"source": "pixiv", "id": "1", "status": "deprecated", "visual_review": "thumbnail_pass", "title": "old", "tags": ["a"]}]
        incoming = [{"source": "pixiv", "id": "2", "pool": "quarantine", "title": "old", "tags": ["お姉さん"], "url": "https://www.pixiv.net/artworks/2"}]
        merged, stats = merge_rows(base, incoming)
        self.assertEqual(merged, [])
        self.assertEqual(stats["deprecated_skipped"], 2)


class CliTest(unittest.TestCase):
    def test_self_check_and_non_windows_guard(self):
        checked = subprocess.run(
            [sys.executable, str(HERE / "collect_pixiv_windows.py"), "--self-check"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("ok", checked.stdout)
        if sys.platform == "win32":
            return
        refused = subprocess.run(
            [sys.executable, str(HERE / "collect_pixiv_windows.py")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(refused.returncode, 2)
        self.assertIn("Windows", refused.stderr)
        download = subprocess.run(
            [sys.executable, str(HERE / "download_pixiv_originals.py")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(download.returncode, 2)
        self.assertIn("Windows", download.stderr)


if __name__ == "__main__":
    unittest.main()
