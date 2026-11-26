# Horrorometer Kodi Addon

Browse your [Horrorometer](https://horrorometer.com) watchlist on Kodi.

## What it does

- Connects to your Horrorometer account via OAuth Device Flow (no password entered on Kodi)
- Lists your horror watchlist (movies, TV, books)
- Marks titles as watched
- Filters by type and status

## Install

1. Download the ZIP from the [install page](https://sirnightowl.github.io/horrorometer-kodi/) or build it from source below.
2. In Kodi, enable **Settings → System → Add-ons → Unknown sources** for ZIP installation.
3. Go to **Add-ons → Install from zip file** and select the downloaded ZIP.
4. Open the add-on and select **Authorize Horrorometer**.
5. On your phone or computer, visit the address shown in Kodi. Enter the code, sign in to Horrorometer, and approve access. Kodi opens the watchlist menu after approval.

Select a title for details. Use its context menu to **Mark as Watched**. **Sign Out** removes the saved sign-in from that Kodi profile. You can revoke the device's access from [Horrorometer app settings](https://horrorometer.com/settings/apps).

## Build from source

```bash
./build.sh
```

The build needs Python 3.9 or later. It writes the ZIP to `dist/` and copies it into `docs/` for publishing.

## Requirements

- Kodi 19 (Matrix) or later
- A Horrorometer account (free at [horrorometer.com](https://horrorometer.com))

## API docs

See [Horrorometer External API docs](https://github.com/sirnightowl/horrorometer/blob/main/docs/EXTERNAL_API.md) for the full API reference.
