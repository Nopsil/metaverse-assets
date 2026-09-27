"""Unit checks for the age/style safety screen. No network."""

from __future__ import annotations

import unittest

from safety import has_person_signal, male_genitalia_reason, rating_for, screen


class ScreenTest(unittest.TestCase):
    def test_blocks_loli_and_shota(self):
        self.assertFalse(screen("1girl, loli, nude")[0])
        self.assertFalse(screen("cute shota boy")[0])
        self.assertFalse(screen("合法ロリ 女の子")[0])
        self.assertFalse(screen("ロリババア")[0])

    def test_blocks_school_and_stated_age(self):
        self.assertFalse(screen("beautiful 16yo schoolgirl, serafuku")[0])
        self.assertFalse(screen("18 years old woman in a classroom")[0])
        self.assertFalse(screen("高校生 制服 女の子")[0])
        self.assertFalse(screen("スク水 お姉さん オリジナル")[0])
        self.assertFalse(screen("スクール水着 人妻")[0])
        self.assertFalse(screen("title 男子中学生だった", tags=["オリジナル"])[0])
        self.assertEqual(screen("she is 25 years old, anime woman")[0], True)

    def test_blocks_known_minor_characters_and_series(self):
        self.assertFalse(screen("hatsune miku, vocaloid, anime")[0])
        self.assertFalse(screen("kinomoto_sakura, card")[0])
        self.assertFalse(screen("ブルーアーカイブ コトネ")[0])
        self.assertFalse(screen("1girl, klee (genshin impact)")[0])
        self.assertFalse(screen("frieren, sousou no frieren")[0])

    def test_bishoujo_word_is_not_an_automatic_drop(self):
        # 美少女 is a genre label used for adult women. Exact tag 少女 is not.
        ok, reason = screen("美少女 お姉さん オリジナル", tags=["美少女", "女性"])
        self.assertTrue(ok, reason)

    def test_petite_adult_is_kept_and_child_coded_flat_is_not(self):
        ok, reason = screen(
            "お姉さん オリジナル 貧乳 スレンダー 細身",
            tags=["華奢", "女性", "オリジナル"],
        )
        self.assertTrue(ok, reason)
        self.assertTrue(screen("ちっぱい お姉さん オリジナル", tags=["女性"])[0])
        self.assertFalse(screen("ちっぱい ロリ オリジナル")[0])
        self.assertFalse(screen("つるぺた オリジナル 女の子")[0])
        self.assertFalse(screen("世良真純 名探偵コナン 貧乳")[0])
        self.assertFalse(screen("からかい上手の高木さん 貧乳 人妻")[0])
        self.assertFalse(screen("オリジナル 全裸登校 授業参観 人妻")[0])
        self.assertFalse(screen("人妻 スレンダー 母娘丼")[0])

    def test_allows_adult_anime_and_childhood_friend_trope(self):
        ok, reason = screen(
            "1girl, adult woman, anime style, cel shading, masterpiece, childhood friend"
        )
        self.assertTrue(ok, reason)
        ok, reason = screen("お姉さん オリジナル 厚塗り 巨乳", tags=["女性", "オリジナル"])
        self.assertTrue(ok, reason)

    def test_exact_ambiguous_tags(self):
        self.assertFalse(screen("original", tags=["少女"])[0])
        self.assertFalse(screen("original", tags=["JK"])[0])
        self.assertFalse(screen("original", tags=["ちび"])[0])
        self.assertTrue(screen("original woman", tags=["女の子", "オリジナル"])[0])

    def test_blocks_male_genitalia_and_futanari(self):
        self.assertFalse(screen("お姉さん ふたなり オリジナル")[0])
        self.assertFalse(screen("細身", tags=["チンポ", "女性"])[0])
        self.assertFalse(screen("futanari dickgirl")[0])
        self.assertFalse(screen("貧乳 ペニス")[0])
        self.assertFalse(screen("ちんこ 人妻")[0])
        self.assertFalse(screen("男根")[0])
        self.assertFalse(screen("お姉さん 射精 ふたなり")[0])
        self.assertIsNotNone(male_genitalia_reason("ふたなり", ["お姉さん"]))
        ok, reason = screen("お姉さん オリジナル 射精", tags=["女性", "貧乳"])
        self.assertTrue(ok, reason)
        self.assertIsNone(male_genitalia_reason("お姉さん 射精", ["女性", "貧乳"]))

    def test_flags(self):
        self.assertFalse(screen("adult woman", minor_flag=True)[0])
        self.assertFalse(screen("adult woman", poi_flag=True)[0])
        self.assertFalse(screen("adult woman", lo_flag=True)[0])

    def test_rating(self):
        self.assertEqual(rating_for(1, "1girl, smile, dress"), "all-ages")
        self.assertEqual(rating_for(1, "1girl, nude, nipples"), "adult")
        self.assertEqual(rating_for(8, "portrait"), "adult")
        self.assertEqual(rating_for("Soft", "sexy dress"), "all-ages")

    def test_person_signal(self):
        self.assertTrue(has_person_signal("1girl, anime"))
        self.assertTrue(has_person_signal("adult woman"))
        self.assertFalse(has_person_signal("landscape, mountain, sky"))
        self.assertFalse(has_person_signal("no humans, city light"))

    def test_loli_prefix_and_school_series(self):
        self.assertFalse(screen("artist:loliconder, 1girl")[0])
        self.assertFalse(screen("nagatoro hayase, gym uniform")[0])
        self.assertFalse(screen("1girl, mesugaki, smile")[0])
        self.assertFalse(screen("satellizer el bridget, anime")[0])
        self.assertFalse(screen("やんちゃっ子 女の子")[0])
        self.assertFalse(screen("violet evergarden, 1girl")[0])
        self.assertFalse(screen("tohsaka rin, fate")[0])
        self.assertFalse(screen("gold ship, umamusume")[0])
        self.assertFalse(screen(r"1girl, suomi_\(girls'_frontline\)")[0])
        self.assertFalse(screen(r"darkness \(konosuba\), 1girl")[0])
        self.assertFalse(screen("go-toubun no hanayome, 1girl")[0])
        self.assertFalse(screen(r"ankha \(animal crossing\), 1girl")[0])
        self.assertFalse(screen(r"reze \(chainsaw man\), naked towel")[0])
        self.assertFalse(screen("1girl, 3d style, large breasts")[0])
        self.assertFalse(screen("monika (doki doki literature club), 1girl")[0])
        self.assertFalse(screen("shantae, 1girl, ponytail")[0])
        self.assertTrue(screen("お姉さん オリジナル 厚塗り", tags=["女の子"])[0])


if __name__ == "__main__":
    unittest.main()
