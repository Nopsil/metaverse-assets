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
        with self.assertRaises(RuntimeError):
            validate_queries(["制服 オリジナル"])

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
