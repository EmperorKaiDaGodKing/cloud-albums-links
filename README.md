# Photo feed

**Your albums are private. This GitHub repo is public.** A link that is saved in a file here can be seen by anyone on the internet, including in old commits. Put the real link in the `PHOTO_FEED_URL` Codespaces secret (steps below) and do not paste album pages, photo lists, or downloaded pictures into the repo or into a public chat.

The file `shared-album-link-storage/MCP-Photo-Feed` is already committed. Deleting it later does not erase it from older commits. If that album should stay private, turn off link sharing in Google Photos and create a new link. Save the new link only as the secret.

This folder is a small tool that reads a **public shared album link** and prints a list of the photos and videos. A bot (in Cursor, or another app that speaks MCP) can ask for that list. You do not install extra Python packages. The tool does not log in to Google or TeraBox.

It reads the same page a browser shows for "anyone with the link." It does not use the Google Photos API.

## What you need

- A shared album link from Google Photos: open the album, tap **Share**, then **Create link**. The link looks like `https://photos.app.goo.gl/...`. It has to be the "anyone with the link" kind. A private share that only certain Google accounts can open will not work, because this tool does not sign in.
- Python 3.10 or newer. In a GitHub Codespace, Python is already installed. On your Mac, check with the command in the next section.

A Codespace is a small computer GitHub runs in the cloud. Your 2017 Intel Mac only has to open a browser. The old Mac does not have to do the work.

## Check Python on the Mac

1. Open **Terminal** (search for Terminal in Spotlight).
2. Paste this and press Return:

```bash
python3 --version
```

3. If you see `Python 3.10` or a higher number, you are set.
4. If the command is not found, install Python from [python.org/downloads](https://www.python.org/downloads/). Use the macOS installer. It works on Intel Macs. Then close Terminal, open it again, and run the version command once more.

## Where the tool looks for a link

It stops at the first place that has a link:

1. The environment variable `PHOTO_FEED_URL` (this is the Codespaces secret).
2. A local config file. By default that is `photo-feed.local.json` in this folder. Git ignores that file, so it is not uploaded. To keep the file somewhere else, set `PHOTO_FEED_CONFIG` to its path (for example `~/albums/photo-feed.local.json`).
3. Text files under `shared-album-link-storage/`. Empty files are skipped. A line that starts with `#` is a note, not a link.

## Set the PHOTO_FEED_URL secret

Do this in a browser, on GitHub. You must be the owner of the repo.

1. Open the `cloud-albums-links` repository on GitHub.
2. Click **Settings**.
3. In the left sidebar, open **Secrets and variables**, then **Codespaces**.
4. Click **New repository secret**.
5. Name: `PHOTO_FEED_URL` (all capitals, exactly that).
6. Value: paste the shared album link and nothing else.
7. Click **Add secret**.

Stop any codespace that is already running and create a new one so it can see the secret. GitHub does not update the secret inside a codespace that is already open.

The secret is **not** put in the repo, and it is **not** given to GitHub Actions. This project does not have a GitHub Actions workflow on purpose.

### Use the secret in a Codespace

1. On the repo page, click **Code**, then **Codespaces**, then **Create codespace** on this branch (after it is merged, `main` is fine).
2. Wait until the terminal is ready. The setup runs the tests, which use a fake album page. They do not open your album.
3. In the codespace terminal:

```bash
python3 -m photo_feed list-albums
python3 -m photo_feed list-photos
```

`list-albums` prints which link will be used. `list-photos` prints the photos and videos as JSON (a text format programs can read).

### Use a link on the Mac instead

The Codespaces secret exists only inside a Codespace. Cursor on the Mac does not see it.

From the project folder:

```bash
cd cloud-albums-links
cp photo-feed.local.json.example photo-feed.local.json
```

Open `photo-feed.local.json` in a text editor and replace the example link with your real link. Save. That file is git-ignored. If you would rather keep that file outside the project, put it somewhere else and point at it:

```bash
export PHOTO_FEED_CONFIG="$HOME/albums/photo-feed.local.json"
```

`PHOTO_FEED_URL` still wins when it is set. A one-link secret is the right choice in a Codespace. `PHOTO_FEED_CONFIG` is for a file on your Mac.

You can also type this in Terminal. It lasts until you close the window, and the link is saved in Terminal's command history, so the file is the better choice:

```bash
export PHOTO_FEED_URL='paste-the-link-here'
python3 -m photo_feed list-photos
```

## Run it

From the project folder:

```bash
python3 -m photo_feed --help
python3 -m photo_feed list-albums
python3 -m photo_feed list-photos
```

Read one link without saving it in config:

```bash
python3 -m photo_feed list-photos 'https://photos.app.goo.gl/paste-your-link-here'
```

Save copies of the files on this computer only (not on GitHub):

```bash
python3 -m photo_feed list-photos --download
```

Files go in `downloads/`. That folder is git-ignored, so the command stays quiet. If you pick another folder and git is not ignoring it, the command prints a warning: this repo is public, so do not commit the photos. You can also use `output/` if you want to save the JSON:

```bash
python3 -m photo_feed list-photos > output/list.json
```

Do not commit `downloads/` or `output/`. Do not paste that JSON into a public place. It contains direct links to the photos.

A made-up example of what one item looks like (this is not a real photo):

```json
{
  "id": "fixture-photo-1",
  "filename": "fixture-photo-1.jpg",
  "kind": "image",
  "url": "https://lh3.googleusercontent.com/pw/EXAMPLE_NOT_A_REAL_PHOTO=s2048",
  "original_url": "https://lh3.googleusercontent.com/pw/EXAMPLE_NOT_A_REAL_PHOTO=d",
  "width": 800,
  "height": 600,
  "date": "2024-03-09T16:00:00Z",
  "size_bytes": null
}
```

- `url` is a direct link, sized for viewing.
- `original_url` asks Google for the original file. `--download` saves that one. For a video, this is the file itself when Google allows it.
- `date` is the date on the public page, when Google includes one.
- `size_bytes` is the file size when the page includes one. Google's public page usually does not, so this is often `null`.
- `kind` is `image` or `video`. A video is marked when the page says it is a video.

## How a bot connects

This repo includes `.cursor/mcp.json`. That file tells Cursor to start a small helper called an MCP server. The helper's name is `photo-feed`. It has two tools:

- `list_albums` — which albums are configured
- `list_album_photos` — the photos and videos in one album

In Cursor:

1. Open this project folder (on the Mac, or the Codespace).
2. Open **Cursor Settings → MCP**.
3. Turn on **photo-feed**. If it is missing, reload the window (Command-Shift-P, then "Reload Window").
4. In chat, ask the bot to list the photos in the album. It should call those tools. You do not paste the album page into the chat.

The bot only sees a link that is available **where the bot is running**:

- Bot inside the Codespace: the `PHOTO_FEED_URL` secret is enough.
- Bot in Cursor on the Mac: use `photo-feed.local.json` on the Mac, or start Cursor from a Terminal where `PHOTO_FEED_URL` is set. The Codespaces secret is not on the Mac.

Other apps that speak MCP can use the same command:

```json
{
  "mcpServers": {
    "photo-feed": {
      "command": "python3",
      "args": ["-m", "photo_feed", "mcp"],
      "env": {
        "PYTHONPATH": "/full/path/to/cloud-albums-links"
      }
    }
  }
}
```

Replace the path with the real folder on your Mac.

## TeraBox

TeraBox share links are recognized and then refused, with a short explanation. A TeraBox share page does not include the file list in the HTML. Reading it means running TeraBox's anti-bot script and then asking for a signed download link, which often comes back as a captcha from a Codespace. This tool will not sign in and will not send your link to another website's downloader. Use a Google Photos link for the bot.

## Limits

- Only albums shared so **anyone with the link** can view them.
- A short `photos.app.goo.gl` link is fine. Google redirects a simple request to the album page. This tool follows that redirect.
- A large album comes back as the first batch on that page (often about 300 items). The JSON then has `"partial": true`. Google loads the rest only when a person scrolls, and this tool does not pretend to scroll. If the page only contains links to each photo, the tool opens up to 40 of those pages. Use `--limit` to take fewer.
- Google sometimes changes the page. If the link works in a browser but this tool says no photos were found, the page format changed and the parser needs an update.
- The tool does not upload anything and it does not start a website.

## Tests

The tests use a fake album page stored in `tests/fixtures/`. They do not open your album and they do not print what is in it.

```bash
python3 -m unittest discover -s tests
```

## Project files

| Path | What it is |
| --- | --- |
| `photo_feed/` | The program |
| `shared-album-link-storage/` | Optional link files. Prefer the secret. |
| `photo-feed.local.json.example` | A sample config. Copy it to `photo-feed.local.json`. |
| `.cursor/mcp.json` | How Cursor starts the bot helper |
| `.devcontainer/` | How the Codespace is built |
| `downloads/` and `output/` | Created when you ask. Git ignores them. |
