# Dock Diary

A bike-share station explorer and sampled-availability diary, starting with Vancouver's Mobi network. The public app reads retained hourly captures, searches the full CityBikes directory, supports a manual current lookup for any station-based network, and compares station observations by local weekday/hour. No account or API key is needed.

<!-- coolcode:guide -->
Choose a network and use **Fetch current availability**, then select a station to inspect bikes, return spaces and a weekday/hour heatmap. Vancouver starts with a real retained capture; the history grows through hourly scheduled checks. An empty heatmap cell means no observations, not uninterrupted availability. A percentage is the share of sampled, distinct observations with zero bikes or spaces, not the share of time unavailable and not a trip count. Download **Save diary JSON** before closing the tab to retain manual lookups; imports and comparisons stay local. Edit **web/config.json** to add tracked networks and their time zones, then run **Dock Diary · Capture, check and publish** to begin retaining them.
<!-- /coolcode:guide -->

## Use it

1. Open [Dock Diary](https://coolcode.ca/dockdiary/). The saved Mobi capture loads immediately without contacting CityBikes.
2. Search stations by name or ID. Filter empty, full, paused or stale station readings. Select any result to see its timestamp, counts and an OpenStreetMap link.
3. Change **Dated capture** to inspect an earlier saved response. Its counts and freshness are calculated for that response; its history stops at that capture.
4. A station's heatmap groups source observations by the chosen IANA time zone. Click an hour to inspect its denominator. Asterisks identify cells below the configurable minimum sample count (three initially).
5. Use the full network directory to choose another city and **Fetch current availability**. New queries are opt-in, one request per click with a 30-second cooldown. A failed lookup retains the previous visible result. Networks with only roaming vehicles and no stations are explicitly unsupported by this station diary.
6. **Save diary JSON** downloads all captures held for the displayed network. **Export capture CSV** downloads the selected capture. **Import a diary** merges the same network's captures in tab memory; these never automatically enter the public repository. Imported files are capped at 30 MB and validated.

For example, three distinct Monday 08:00 station observations with bike counts 0, 3 and 0 show **67%** sampled unavailability. They do not show that the station was empty for 40 minutes. At launch most cells have no samples; useful comparisons require repeated observations over time.

## Data and interpretation

- Source: [CityBikes v2](https://docs.citybik.es/api/) and [API schema](https://api.citybik.es/v2/), supplied by [CityBikes](https://citybik.es/). This project visibly attributes and links CityBikes under its [terms](https://docs.citybik.es/api/tos).
- Basic public access is limited to **300 requests per hour**. This collector normally uses two hourly requests: the directory and one configured network. Request a key from CityBikes only if a future deployment genuinely needs more; do not add one to browser code.
- The initial directory was fetched on 23 November 2026 and contains **815 networks**. The initial Mobi capture contains **261 stations**. These are initial source counts, not limits; the UI derives them from the actual directory and selected capture.
- Available bikes and empty docks are instantaneous source values. They are not demand, trip counts or durations. Maintenance, rebalancing and service pauses can affect them. Unknown values remain null; zero remains zero.
- `capturedAt` is our retrieval timestamp. Each observation also preserves the provider's station update timestamp, using `extra.last_updated` when supplied and the CityBikes station timestamp otherwise. CityBikes' duplicated `+00:00Z` suffix is normalized, and naive source timestamps are treated as UTC.
- Heatmaps count distinct station timestamps once. Readings older than `staleMinutes` **at capture**, absent counts and relevant explicitly paused rental/return service are excluded. A missing service flag is retained as unknown rather than invented. Check the operator before travelling.
- Historical captures keep their own station coverage; new and removed stations do not rewrite old counts. Station labels/coordinates use the newest captured metadata for that station ID. Capture gaps and short sample histories remain visible.
- [CityBikes historical data](https://data.citybik.es/) is a separate upstream resource; this app does **not** claim to import that archive. Its diary begins with its actual first saved capture.

## Expand or customize

Edit **`web/config.json`**. Defaults are conveniences, never an exclusive UI list. The browser directory permits all station-based networks returned by CityBikes. To retain Toronto alongside Vancouver, append:

```json
{"id":"bixi-toronto","label":"Toronto · Bike Share Toronto","timezone":"America/Toronto"}
```

The full configuration fields are:

| Field | Meaning |
| --- | --- |
| `defaultNetwork` | Initially displayed tracked network ID. Must be present in `trackedNetworks`. |
| `trackedNetworks` | Objects with CityBikes `id`, descriptive `label` and an IANA `timezone`. |
| `historyDays` | Rolling published history, initially 28 days; allowed 1–90. |
| `maxCapturesPerNetwork` | Hard capture bound, initially 672; allowed 1–2160. Older captures remain in Git history after rolling out. |
| `staleMinutes` | Maximum source age at retrieval for aggregate counts and heatmaps, initially 60. |
| `minimumSamplesPerCell` | Threshold for the low-sample asterisk, initially 3. It is not a statistical confidence claim. |
| `maxStationsPerNetwork` | Collector response sanity bound, initially 15,000; can expand up to 30,000. |
| `maxTrackedNetworks` | Collector request budget, initially 12; at most 30. |
| `requestTimeoutSeconds` | Per-request timeout, initially 35 seconds. |
| `liveCooldownSeconds` | Browser's minimum interval between manual lookups, initially 30 seconds. |

**Refresh after editing:** Commit/push the config, then open Actions → **Dock Diary · Capture, check and publish** → **Run workflow** on `main`. An ordinary code push builds the existing data offline; it does not fetch new observations. The manual and hourly `:17` UTC runs call `scripts/collect.py`, validate all configured networks, run tests and the browser check, commit only the data, and deploy. The new network then appears in the public retained diary. Locally:

```sh
python3 scripts/collect.py
node --test tests/*.test.mjs
python3 -m unittest discover -s tests -v
python3 scripts/build.py
```

Collection is all-or-nothing for the configured set: unavailable/invalid sources fail before replacing saved files, and failed CI does not deploy. GitHub schedules can be delayed, skipped or disabled after prolonged repository inactivity. Inspect the displayed capture date, not just whether the site loads. Data are rolling retained captures, not an indefinitely growing full archive. Download diaries when you want an independent copy.

## Privacy and operation

The page loads its own saved JSON by default. A manual lookup sends only the selected network ID (plus ordinary connection information) to CityBikes. It does not request your device location. Station search, imported files and exports are processed locally without persistence. No API key, framework or runtime server is required. Shared CoolCode aggregate page metrics and the report link are added by the build.

The app works from a project subpath, with relative assets. GitHub Pages serves `dist/`; no CNAME or Cloudflare service is required. UI source is in `web/`; pure transformations are in `web/model.mjs`; the standard-library collector is `scripts/collect.py`. `tests/browser_smoke.py` runs in CI, checking saved data, filtering, export, failure retention and mobile overflow.

Related tools: [Trailglass](https://coolcode.ca/trailglass/) and [Road Pulse](https://coolcode.ca/roadpulse/).

<!-- schedule-reliability -->
## Schedule reliability

Public GitHub repositories can have scheduled workflows disabled after 60 days of inactivity. A separate weekly [schedule guard](.github/workflows/schedule-guard.yml) calls GitHub's enable-workflow API for an explicit list of refresh workflows and itself. It can restore workflows disabled for inactivity, preserves manually disabled workflows, and runs independently of collection failures.

This is an interim mitigation, not a scheduling guarantee: GitHub does not document active-workflow renewal as a permanent exemption, and scheduled runs can be delayed or dropped. A scheduler on our own Linux server is the planned independent trigger. The guard does not collect data, create dummy commits, or change source/check timestamps; successful collection and published data freshness still need monitoring.
<!-- /schedule-reliability -->
