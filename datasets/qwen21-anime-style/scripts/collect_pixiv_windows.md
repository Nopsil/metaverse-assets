# Collect Pixiv on your Windows PC, then download originals

Pixiv R-18 is not collectable from the cloud box that built this catalog, and this cloud box cannot download R-18 originals either.

- Grok Bot's remote machine cannot use Pixiv. The IP is a US datacenter address, and Pixiv blocks those.
- A Cursor cloud agent does not have your home IP or your logged-in Chrome.
- Public `mode=r18` search returns safe-mode works (`xRestrict=0`). That is not an R-18 set. See `catalog/pixiv_r18_probe.json`.
- Copying Chrome's Default profile does not work. Those cookies use app-bound encryption (ABE v20). A copy never stays logged in. Do not use a Cookies-file copy of Default.

Use one dedicated Playwright Chrome profile and your local proxy. The profile that already logged in on the home PC is `C:\Users\nopsi\temp\pixiv-collector-chrome` with proxy `http://127.0.0.1:7890`.

Nothing here puts a cookie, refresh token, Chrome profile, or image file in git.

## Age check

Do not decide that a character is a minor from body proportions or a cute face alone. Check the series, the character, and what the artist says the setting is.

- Drop child-coded and school-coded characters even when the drawing looks adult.
- Do not drop a clearly adult character (canonical adult, お姉さん, 人妻, 熟女, stated age 21 or older) only because the style is cute.
- `scripts/safety.py` enforces the series and age tags. A full-size look of the original file is still required when the setting is unclear.

## Run order

From `datasets/qwen21-anime-style/scripts` on Windows. Install once: `py -3 -m pip install playwright`. The scripts launch installed Google Chrome (`channel=chrome`), not Playwright's bundled Chromium.

Set the profile and proxy in each command. Close any Chrome window that already has this dedicated profile open.

### 1. Log in once

```bat
py -3 collect_pixiv_windows.py --login --dedicated-profile C:\Users\nopsi\temp\pixiv-collector-chrome --proxy http://127.0.0.1:7890
```

A Chrome window opens on that folder. Log into Pixiv and open one R-18 artwork. Press Enter in the terminal. The profile stays on disk. Do not commit that folder.

### 2. Collect artwork page URLs

```bat
py -3 collect_pixiv_windows.py --self-check
py -3 collect_pixiv_windows.py --mode both --limit 60 --dedicated-profile C:\Users\nopsi\temp\pixiv-collector-chrome --proxy http://127.0.0.1:7890
```

`--mode both` reads public bookmarks and an allowlisted R-18 search (お姉さん / 熟女 / 人妻 / 長身 / 巨乳, original illustrations). Safe-mode stand-ins from a masked R-18 search are not saved. Every title, tag, and description goes through `safety.py`. Output is gitignored `catalog/_pixiv_windows_export.jsonl`.

| Flag | Meaning |
| --- | --- |
| `--dedicated-profile` | Persistent Chrome user-data directory. Not the system Chrome profile. |
| `--proxy` | Local proxy, `http://127.0.0.1:7890` on this PC. |
| `--login` | Open the profile for a one-time Pixiv login. |
| `--user-id 123456` | Numeric id from `https://www.pixiv.net/users/123456`, if the page does not show one. |
| `--mode bookmarks` | Public bookmarks only. |
| `--mode r18` | Allowlisted R-18 searches only. |
| `--include-private` | Also read private bookmarks. They stay in the gitignored export unless you merge them. |
| `--include-ai` | Keep works Pixiv has labeled as AI. Off by default. |

`--self-check` only validates the search words and can run anywhere. A real collect or download exits on Linux and macOS.

### 3. Download img-original files

The catalog stores artwork **page** URLs. `square1200` and `master1200` are thumbnails. The downloader opens each Pixiv page in the dedicated profile and saves `i.pximg.net/img-original/...` only. Chrome is started with `--proxy-server=http://127.0.0.1:7890`. A saved file must match the pixel size Pixiv reports, so a thumbnail cannot be kept under an original name.

```bat
py -3 download_pixiv_originals.py --catalog ../catalog/style_candidates.jsonl --dedicated-profile C:\Users\nopsi\temp\pixiv-collector-chrome --proxy http://127.0.0.1:7890
```

Files land in gitignored `catalog/_originals/` as `{id}_p0.jpg` (and `_p1`, `_p2` when the work has more than one still). A `manifest.jsonl` in that folder records skips. Do not commit the folder.

- **Ugoira** (animated) is skipped.
- **Multi-page** works save the first 3 stills and record how many later pages were left out.
- A row whose tags or title fail `safety.py` is not saved.
- Civitai rows in the same catalog are skipped here. This script is the Pixiv original path. A cloud machine did not download R-18 files.

Then review those files at full size. Delete a file and its catalog row when the series, character, or author's setting is child-coded or school-aged. Cute proportions on a clearly adult character are not a reason to delete.

## Paste URLs (no collector)

Use this when you would rather copy links from the browser yourself.

1. On Pixiv, open your bookmarks or a search you have already looked at.
2. Copy artwork links. These shapes all work:

```text
https://www.pixiv.net/artworks/123456789
https://www.pixiv.net/en/artworks/123456789
https://www.pixiv.net/i/123456789
```

3. Put one URL per line in gitignored `catalog/pixiv_urls.txt`. Lines starting with `#` are ignored. An empty template is `catalog/pixiv_url_paste.example.txt`. Do not commit the filled-in file.
4. You can also save a CSV with a `url` column and optional `title` and `tags` columns. Separate tags with `|`.

The paste file has no metadata screen until merge time. Rows with a title or tags are screened. Rows that are only a URL are kept as `rating=unreviewed` and `visual_review=pending`. They are not cleared for training. After they are in the catalog, step 3 above downloads the originals.

## Merge and dedupe

Reviewed rows already in `catalog/style_candidates.jsonl` stay when an import repeats the same artwork id. New rows do not overwrite `visual_review=thumbnail_pass`.

From `datasets/qwen21-anime-style/scripts`:

```bash
python3 merge_exports.py \
  --import ../catalog/_pixiv_windows_export.jsonl \
  --import ../catalog/pixiv_urls.txt \
  --import ../catalog/civitai_adult_pending.jsonl
```

That writes `catalog/_merged_preview.jsonl` and `.csv` (gitignored) and prints counts: added, dropped by the safety screen, and duplicates that kept the reviewed row. It does **not** change `style_candidates.*`.

When the preview looks right:

```bash
python3 merge_exports.py \
  --import ../catalog/_pixiv_windows_export.jsonl \
  --import ../catalog/pixiv_urls.txt \
  --apply
```

`--apply` rewrites `style_candidates.jsonl` and `style_candidates.csv`. Imported rows stay `visual_review=pending` until you have opened the original file.

Dedupe key is the source plus the numeric id, so `pixiv.net/en/artworks/ID` and `pixiv.net/artworks/ID` are one row. A reviewed row wins over a later import of the same id. Two pending imports of the same id keep the one with more tags.

If you already merged 13 Pixiv rows on the home PC (129 URLs) and those commits were not pushed, pull this branch and run the merge again from `catalog/_pixiv_windows_export.jsonl` so those rows stay. This cloud branch does not contain those 13 URLs.

## After the originals are on disk

1. Review the files in `catalog/_originals/`. Delete a row when the series, character, or setting is child-coded. Do not delete a clearly adult character for a cute drawing style.
2. Do not commit image files, cookies, or the dedicated Chrome profile.
3. R-18 illustrations can stay on the style list when they are full drawings of adults. Close-up anatomy belongs in `catalog/nsfw_anatomy_scaffold.csv`, still with `safety_status=unreviewed` until you have checked the file.
4. No training from this step.
