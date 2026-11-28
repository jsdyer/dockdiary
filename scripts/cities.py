"""Build dated Canadian bike-share city guides from the same archives as the diary."""
from collections import defaultdict
from datetime import datetime, timedelta
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlencode
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo


def link(url, label):
    return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def local_time(value, zone):
    return timestamp(value).astimezone(zone).strftime('%b %d, %Y at %H:%M %Z')


def reading_values(row, cutoff):
    if timestamp(row[3]) < cutoff:
        return ('Stale', 'Stale')
    return tuple('Paused' if enabled is False else 'Unknown' if count is None else count
                 for count, enabled in ((row[1], row[4]), (row[2], row[5])))


def summary(capture, stale_minutes):
    total = [0, 0]
    usable = [0, 0]
    cutoff = timestamp(capture['capturedAt']) - timedelta(minutes=stale_minutes)
    for row in capture['rows']:
        for i, value in enumerate(reading_values(row, cutoff)):
            if isinstance(value, int):
                total[i] += value > 0
                usable[i] += 1
    return [f'{n:,} of {d:,}' if d else 'No usable readings' for n, d in zip(total, usable)]


def page(stage, base, path, title, description, body):
    target = stage / path
    target.mkdir(parents=True, exist_ok=True)
    href = '../' * len(Path(path).parts)
    (target / 'index.html').write_text(f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · Dock Diary</title><meta name="description" content="{escape(description, quote=True)}">
<link rel="canonical" href="{escape(base + path)}"><link rel="stylesheet" href="{href}style.css"></head>
<body><a class="skip" href="#main">Skip to station guide</a><header><a class="brand" href="{href}">Dock Diary</a><nav><a href="{href}cities/">All cities</a><a href="https://coolcode.ca/">CoolCode</a></nav></header>
<main id="main" class="city-page"><h1>{escape(title)}</h1>{body}</main></body></html>''', encoding='utf-8')


def station_table(archive, setting, capture, stale_minutes):
    cutoff = timestamp(capture['capturedAt']) - timedelta(minutes=stale_minutes)
    groups = defaultdict(list)
    for row in sorted(capture['rows'], key=lambda item: archive['stations'][item[0]]['name'].strip().casefold()):
        name = archive['stations'][row[0]]['name'].strip()
        letter = name.lstrip()[:1].upper()
        group = letter if letter.isalpha() else 'Numbers and symbols'
        url = '../../?' + urlencode({'network': setting['id'], 'station': row[0]}) + '#station-name'
        bikes, docks = reading_values(row, cutoff)
        groups[group].append(f'<tr><th scope="row">{link(url, name)}</th><td>{bikes}</td><td>{docks}</td></tr>')
    sections = []
    for letter, rows in groups.items():
        sections.append(f'<details><summary>{escape(letter)} · {len(rows)} stations</summary><table><thead><tr>'
                        '<th>Station</th><th>Bikes</th><th>Return spaces</th></tr></thead>'
                        f'<tbody>{"".join(rows)}</tbody></table></details>')
    return ''.join(sections)


def city_guide(stage, base, name, path, setting, archive, stale_minutes):
    zone = ZoneInfo(setting['timezone'])
    captures = archive['captures']
    latest = captures[-1]
    date = local_time(latest['capturedAt'], zone)
    rows = latest['rows']
    bikes, docks = summary(latest, stale_minutes)
    label = setting.get('label', archive['network']['name'])
    title = f'{name} bike-share stations and return spaces'
    query = '../../?' + urlencode({'network': setting['id']}) + '#main'
    body = (f'<p class="lead">Of stations with usable readings, <strong>{bikes}</strong> had a bike to rent and '
            f'<strong>{docks}</strong> had a space to return one at the latest saved check.</p>'
            f'<p>{escape(label)} · {len(rows):,} stations in the capture · {escape(date)}.</p>'
            f'<p>{link(query, "Search stations or fetch a current reading")}</p>'
            '<h2>Recent checks</h2>')
    if len(captures) == 1:
        body += '<p>This is the first retained capture. Hourly checks will add station history.</p>'
    else:
        first = local_time(captures[0]['capturedAt'], zone)
        body += f'<p>{len(captures):,} captures in the retained window, from {escape(first)} to {escape(date)}. '
        body += 'Checks can be missed. A station can change between checks.</p>'
    body += ('<table><thead><tr><th>Captured locally</th><th>Stations with bikes</th>'
             '<th>Stations with spaces</th></tr></thead><tbody>')
    for capture in reversed(captures[-6:]):
        bikes_now, docks_now = summary(capture, stale_minutes)
        body += f'<tr><th scope="row">{local_time(capture["capturedAt"], zone)}</th><td>{bikes_now}</td><td>{docks_now}</td></tr>'
    body += ('</tbody></table><h2>Find a station</h2><p>Open a letter, then choose a station to see its own weekday and hour history.</p>'
             + station_table(archive, setting, latest, stale_minutes))
    sources = [link(archive['source'], 'CityBikes station data')]
    if setting.get('operator'):
        sources.append(link(setting['operator'], label.split(' · ')[-1]))
    body += (f'<h2>Reading these counts</h2><p>“Stale” means the source reading was over {stale_minutes} minutes old when collected. '
             'The totals exclude stale readings, missing counts and stations where the relevant service was paused. '
             'A zero is a reported zero. Check current availability before leaving.</p>'
             f'<p>Source and operator: {" · ".join(sources)}. {link("../", "Compare all saved cities")}</p>')
    description = f'Find bikes and return spaces from the latest saved {name} bike-share capture, explore station histories and see the local observation times.'
    page(stage, base, path, title, description, body)


def build_cities(stage, tool):
    base = 'https://coolcode.ca' + tool['url']
    config = json.loads((stage / 'config.json').read_text())
    index = json.loads((stage / 'data/index.json').read_text())
    settings = {item['id']: item for item in config['trackedNetworks']}
    cities = []
    for item in index['networks']:
        setting = settings[item['id']]
        archive = json.loads((stage / 'data' / item['file']).read_text())
        name = setting.get('city') or archive['network']['city'] or setting['id']
        slug = setting.get('slug', setting['id'])
        if not re.fullmatch(r'[a-z0-9]+(?:[-_][a-z0-9]+)*', slug) or any(slug == c[0] for c in cities):
            raise ValueError('City paths must be safe and unique')
        city_guide(stage, base, name, f'cities/{slug}/', setting, archive, config['staleMinutes'])
        cities.append((slug, name, setting.get('province', ''), len(archive['captures'][-1]['rows']),
                       local_time(archive['captures'][-1]['capturedAt'], ZoneInfo(setting['timezone']))))
    cities.sort(key=lambda item: item[1])
    paths = ['cities/']
    entries = []
    shortcuts = []
    for slug, name, province, stations, date in cities:
        path = f'cities/{slug}/'
        paths.append(path)
        entries.append(f'<li><strong>{link(slug + "/", name)}</strong> {escape(province)}'
                       f'<br>{stations:,} stations · {escape(date)}</li>')
        shortcuts.append(link(path, name))
    page(stage, base, 'cities/', 'Canadian bike-share station guides', 'Choose a city to find a bike or a return space and inspect saved station observations.',
         '<p class="lead">Choose a city to check bikes and return spaces, then open a station to explore its saved history.</p>'
         f'<ul class="cities">{"".join(entries)}</ul><p>{link("../#main", "Look up another network in the CityBikes directory")}</p>')
    xml = ET.Element('urlset', xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')
    for path in paths:
        ET.SubElement(ET.SubElement(xml, 'url'), 'loc').text = base + path
    ET.ElementTree(xml).write(stage / 'sitemap.xml', encoding='utf-8', xml_declaration=True)
    return ' '.join(shortcuts)
