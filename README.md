# Horrorometer Kodi Addon

Browse your [Horrorometer](https://horrorometer.com) watchlist on Kodi.

## What it does

- Connects to your Horrorometer account via OAuth Device Flow (no password entered on Kodi)
- Lists your horror watchlist (movies, TV, books)
- Marks titles as watched
- Filters by type and status

## Install

1. In Kodi, go to **Settings → File manager → Add source**
2. Add `https://sirnightowl.github.io/horrorometer-kodi/` as a source
3. Go to **Add-ons → Install from zip file** → select the source → install `plugin.video.horrorometer-x.x.x.zip`
4. Open the addon — it will show a code and URL
5. Visit the URL on your phone/browser, sign in to Horrorometer, approve
6. Your watchlist appears in Kodi

## Build from source

```
zip -r plugin.video.horrorometer.zip plugin.video.horrorometer/
```

## Requirements

- Kodi 19+ (Matrix) or 21+ (Omega)
- A Horrorometer account (free at [horrorometer.com](https://horrorometer.com))

## API docs

See [Horrorometer External API docs](https://github.com/sirnightowl/horrorometer/blob/main/docs/EXTERNAL_API.md) for the full API reference.