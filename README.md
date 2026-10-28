# Photo feed

**Put album links in a secret, not in this repo.** This GitHub repository is public. Anyone can open a file that has been committed, including `shared-album-link-storage/MCP-Photo-Feed`. A Google Photos share link is enough to view the album. Save the link as the `PHOTO_FEED_URL` Codespaces secret (steps below). When you have done that, delete the link from the file. You can leave the file where it is.

## What this does

This is a small Python tool. You give it a public Google Photos shared-album link. It prints the photos and videos in that album: a direct file link, an id or a filename, and the date or file size when the page includes them.

It does not log into Google. It reads the same page a browser opens for someone who has the link.

A bot in Cursor can call it too. The bot uses two tools: `list_albums` and `list_album_photos`.

## What you need

Python 3.10 or newer. A Codespace made from this repo already has Python. The dev container installs nothing else. There is no `pip install` step.

On a 2017 Intel Mac, outside a Codespace:

1. Press Command and the space bar together. Type `Terminal`. Press Return.
2. Type `python3 --version` and press Return.
3. If the Mac says `command not found`, download Python from [python.org/downloads/macos](https://www.python.org/downloads/macos/). Use the macOS 64-bit installer. That installer works on Intel Macs. Quit Terminal, open it again, and run `python3 --version` once more.

## How a link is chosen

The tool stops at the first place that has a link.

1. The environment variable `PHOTO_FEED_URL`. In a Codespace this is the secret.
2. A file named `photo-feed.local.json` in this folder. Git ignores that file, so it is not uploaded. You can point `PHOTO_FEED_CONFIG` at a file outside this folder if you want the link kept somewhere else on your Mac.
3. Text files under `shared-album-link-storage/`. Empty files are skipped. A link is already stored in `shared-album-link-storage/MCP-Photo-Feed`.

## Add a link on your Mac

Copy the example file and edit the copy:

```bash
cp photo-feed.local.json.example photo-feed.local.json
```

Open `photo-feed.local.json`, replace the placeholder with your link, and save. Do not commit that file.

For one Terminal window only, you can also run:

```bash
export PHOTO_FEED_URL='https://photos.app.goo.gl/paste-your-link-here'
```

That command is saved in Terminal history. The secret, or `photo-feed.local.json`, is a better place for a private link.

In the Google Photos app: open the album, tap Share, then Create link. Copy that link. Link sharing has to be turned on.

## Set the PHOTO_FEED_URL Codespaces secret

1. On GitHub, open this repository.
2. Click **Settings**. Use the repository Settings tab, not your account settings.
3. In the left sidebar, open **Secrets and variables**, then **Codespaces**.
4. Click **New repository secret**.
5. Name: `PHOTO_FEED_URL`
6. Value: the shared album link, starting with `https://`
7. Click **Add secret**.

Stop the Codespace and start it again. A secret is loaded when the Codespace starts. A Codespace that is already running does not see a secret you just created.

The secret is not written into the repo. This project has no GitHub Actions workflow, on purpose. Do not add one that fetches the album or uploads the photo list.

## Run it

Open Terminal in this project folder. In a Codespace, the window is already there. On your Mac, type `cd ` with a space after it, drag the project folder into the window, and press Return.

Show which link will be used:

```bash
python3 -m photo_feed list-albums
```

Print the photos and videos as JSON:

```bash
python3 -m photo_feed list-photos
```

Save copies into a `downloads` folder. Git ignores that folder.

```bash
python3 -m photo_feed list-photos --download downloads
```

If you pick a folder that git does not ignore, the tool prints a warning. Do not commit that folder.

To pass one link without saving it:

```bash
python3 -m photo_feed list-photos --url 'https://photos.app.goo.gl/paste-your-link-here'
```

Check the program without opening your album. This uses a fake page in the tests. It does not use your link.

```bash
python3 -m unittest discover -s tests
```

You want a final line that says `OK`.

## What the JSON looks like

A real run prints your album. This sample is fake, so the README does not contain a real photo link.

```json
{
  "album": {
    "name": "PHOTO_FEED_URL",
    "title": "Picnic",
    "provider": "google-photos"
  },
  "items": [
    {
      "id": "fixture-photo-1",
      "filename": "picnic.jpg",
      "kind": "photo",
      "url": "https://cdn.example.test/picnic.jpg",
      "width": 800,
      "height": 600,
      "created_at": "2023-11-14T22:13:20Z",
      "size_bytes": 2048
    }
  ]
}
```

`kind` is `photo` or `video`. Filename, dates, and `size_bytes` are filled in when Google's page includes them. Otherwise they are `null`.

The public page includes the first batch of items, about 300. A bigger album is cut off, because Google only sends the rest when a person scrolls. The `note` field in the JSON says this too.

This reads Google's public share page. It is not an official API. Google removed the official way for apps to read albums. If Google changes the page, the list can come back empty until this tool is updated.

## How a bot connects

This project includes `.cursor/mcp.json`. Cursor starts the tool as an MCP server with:

```bash
python3 -m photo_feed mcp
```

The bot gets two tools:

| Tool | What you ask for | What it returns |
| --- | --- | --- |
| `list_albums` | nothing | The saved links, and which place they came from |
| `list_album_photos` | optional `url`, `name`, or `download_dir` | Photos and videos. `download_dir` also saves copies on this computer |

In Cursor:

1. Open this project folder. The server starts in that folder, so it can see the secret and the link files.
2. Open Settings, then MCP. Turn on `photo-feed` if it is off.
3. Start a new chat. Ask the bot to list the album photos.

In a Codespace, rebuild or restart it after you add `PHOTO_FEED_URL`, then start the chat. The bot reads the same secret the Terminal sees.

You do not need to run `python3 -m photo_feed mcp` yourself. Cursor runs it. If you do run it, the window sits and waits. Press Control-C to stop it.

## TeraBox

TeraBox links are recognized, then refused. TeraBox asks for a signed-in cookie and often a captcha before it will list files, and each file link is signed. This tool does not log in. It also does not send your link to a third-party downloader, because that would hand a private album to someone else.

Use a Google Photos share link. The empty files under `shared-album-link-storage/terabox-link-album/` are left where they are.

## Privacy

- Do not commit photos, thumbnails, image links from an album, JSON output, or `photo-feed.local.json`.
- `.gitignore` ignores `downloads/`, `output/`, `photo-feed-downloads/`, `photo-feed-out/`, and `photo-feed.local.json`.
- Do not add a GitHub Actions workflow that opens the album or publishes the list.
- The photo list is printed in your Terminal, or returned to the bot. It is not stored in git unless you commit it yourself.
