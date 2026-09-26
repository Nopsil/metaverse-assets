# Collect Pixiv on your Windows PC

Pixiv R-18 is not collectable from the cloud box that built this catalog.

- Grok Bot's remote machine cannot use Pixiv. The IP is a US datacenter address, and Pixiv blocks those.
- A Cursor cloud agent usually does not have your home IP or your logged-in Chrome either.
- Public `mode=r18` search, when it answers at all, returns safe-mode works (`xRestrict=0`). That is not an R-18 set. See `catalog/pixiv_r18_probe.json`.

Do the collection at home. Two ways are below. Neither one puts a cookie, refresh token, or Chrome profile in git.

## 1. Script (Chrome profile copy)

`collect_pixiv_windows.py` is Windows-only.

What it does:

1. Copies only the login files for one Chrome profile into a temp folder: `Local State`, `Cookies`, and preferences.
2. It does **not** copy `Login Data` (saved passwords), History, or cache, and it does not read cookie values in Python.
3. It opens **installed Google Chrome** on that temp copy, so the real profile stays closed and unmodified.
4. It reads your public bookmarks and/or an allowlisted R-18 search (お姉さん / 熟女 / 人妻 / 長身 / 巨乳, original illustrations).
5. Every title, tag, and description goes through `safety.py`. School, stated age under 21, child-coded series, chibi, and R-18G are dropped.
6. It writes artwork **page URLs** to `catalog/_pixiv_windows_export.jsonl` (gitignored).
7. It deletes the temp copy on the way out.

If Windows kills the script before that delete, remove leftover folders named `pixiv-chrome-copy-*` under your temp directory. Those folders contain a session cookie. Do not copy them into this repo.

### Setup

1. Install [Google Chrome](https://www.google.com/chrome/) and log into Pixiv in the profile you want to use (`Default`, or `Profile 1`, …). Confirm an R-18 page opens in that window.
2. Install Python 3.11+ from python.org if `py -3` is not already available.
3. In a terminal:

```bat
py -3 -m pip install playwright
```

Do not point the script at Playwright's bundled Chromium. Windows ties Chrome's saved login to the installed Chrome app. The script launches `channel="chrome"`.

4. Close Chrome completely, including the tray icon. If a cookie file is locked, the script stops. It will not scrape the live profile in place.

### Run

From `datasets/qwen21-anime-style/scripts`:

```bat
py -3 collect_pixiv_windows.py --self-check
py -3 collect_pixiv_windows.py --mode both --limit 60
```

Other flags:

| Flag | Meaning |
| --- | --- |
| `--profile "Profile 1"` | Chrome profile folder under `%LOCALAPPDATA%\Google\Chrome\User Data`. |
| `--user-id 123456` | Numeric id from `https://www.pixiv.net/users/123456`, if the script cannot see it. |
| `--mode bookmarks` | Your public bookmarks only. |
| `--mode r18` | Allowlisted R-18 searches only. Safe-mode stand-ins are not saved. |
| `--include-private` | Also read private bookmarks (`rest=hide`). They stay in the gitignored export unless you later merge them. |
| `--include-ai` | Keep works Pixiv has labeled as AI. Off by default, same as the public fetcher. |
| `--dry-run` | Copy the profile to temp, delete it, do not open Pixiv. |

A cloud shell, including this repo's agent, exits immediately on Linux and macOS. `--self-check` only validates the search words.

## 2. Paste URLs (no script)

Use this when you would rather export from the browser yourself.

1. On Pixiv, open your bookmarks or a search you have already looked at.
2. Copy artwork links. These shapes all work:

```text
https://www.pixiv.net/artworks/123456789
https://www.pixiv.net/en/artworks/123456789
https://www.pixiv.net/i/123456789
```

3. Put one URL per line in a file **outside git** or in the gitignored path `catalog/pixiv_urls.txt`. Lines starting with `#` are ignored. An empty template with comments is `catalog/pixiv_url_paste.example.txt`. Do not commit the filled-in file.
4. You can also save a CSV with a `url` column and optional `title` and `tags` columns. Separate tags with `|`.

The paste file has no metadata screen until merge time. Rows with a title or tags are screened. Rows that are only a URL are kept as `rating=unreviewed` and `visual_review=pending`. They are not cleared for training.

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

`--apply` rewrites `style_candidates.jsonl` and `style_candidates.csv`. Imported rows stay `visual_review=pending` until you have opened the full image.

Dedupe key is the source plus the numeric id, so `pixiv.net/en/artworks/ID` and `pixiv.net/artworks/ID` are one row. A reviewed row wins over a later import of the same id. Two pending imports of the same id keep the one with more tags.

Drop anything the screen catches (age under 21, school, loli/shota, child-coded series, chibi, gore). Opening the page is still required: a tag list cannot see the picture.

## After the URLs are in the catalog

1. Full-size review. If the character could be a minor, delete the row.
2. Do not commit image files, cookies, or the temp Chrome folder.
3. R-18 illustrations can stay on the style list when they are full drawings of adults. Close-up anatomy belongs in `catalog/nsfw_anatomy_scaffold.csv`, still with `safety_status=unreviewed` until you have checked the file. The collector does not fill that scaffold by itself.
4. No training from this step.
