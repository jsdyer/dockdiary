#!/usr/bin/env python3
"""Fetch configured CityBikes networks and atomically retain bounded observations."""
from datetime import datetime, timezone, timedelta
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import tempfile
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
API = 'https://api.citybik.es/v2/networks'
SCHEMA = 'coolcode.dockdiary.v1'
SLUG = re.compile(r'^[a-z0-9][a-z0-9_-]{0,100}$')

def utc(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')
    if not isinstance(value, str): raise ValueError('Missing observation timestamp')
    value = value.replace('+00:00Z', '+00:00')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100000 else None

def flag(value):
    return bool(value) if value in (True, False, 0, 1) and value is not None else None

def coordinate(value, limit):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and abs(value) <= limit else None

def validate_config(config):
    networks = config.get('trackedNetworks')
    if not isinstance(networks, list) or not 1 <= len(networks) <= int(config.get('maxTrackedNetworks', 12)) <= 30:
        raise ValueError('Configure 1–30 tracked networks within maxTrackedNetworks')
    seen = set()
    for item in networks:
        if not SLUG.fullmatch(item.get('id', '')) or item['id'] in seen: raise ValueError('Invalid or duplicate network ID')
        seen.add(item['id']); ZoneInfo(item['timezone'])
        cap = item.get('maxCaptures', config['maxCapturesPerNetwork'])
        if type(cap) is not int or not 1 <= cap <= config['maxCapturesPerNetwork']:
            raise ValueError('Network capture limit exceeds the configured archive bound')
    if config.get('defaultNetwork') not in seen: raise ValueError('Default network must be tracked')
    for key, low, high in [('historyDays', 1, 90), ('maxCapturesPerNetwork', 1, 2160), ('maxStationsPerNetwork', 1, 30000), ('requestTimeoutSeconds', 5, 90), ('staleMinutes', 1, 1440), ('minimumSamplesPerCell', 1, 100), ('liveCooldownSeconds', 10, 3600)]:
        if not isinstance(config.get(key), int) or not low <= config[key] <= high: raise ValueError('Invalid '+key)
    return config

def normalize(raw, setting, captured_at, maximum=15000):
    network = raw.get('network')
    if not isinstance(network, dict) or network.get('id') != setting['id']: raise ValueError('Network identity did not match')
    stations = network.get('stations')
    if not isinstance(stations, list) or not 1 <= len(stations) <= maximum: raise ValueError('Empty or oversized station response')
    metadata, rows, seen = {}, [], set()
    for item in stations:
        ident = item.get('id')
        if not isinstance(ident, str) or not 1 <= len(ident) <= 150 or ident in seen: raise ValueError('Invalid or duplicate station ID')
        seen.add(ident)
        if not isinstance(item.get('name'), str) or not item['name'].strip(): raise ValueError('Station name missing')
        extra = item.get('extra') or {}
        observed = utc(extra.get('last_updated') or item.get('timestamp'))
        if datetime.fromisoformat(observed.replace('Z', '+00:00')) > datetime.fromisoformat(captured_at.replace('Z', '+00:00')) + timedelta(minutes=5): raise ValueError('Observation is in the future')
        metadata[ident] = {'name': item['name'][:300], 'latitude': coordinate(item.get('latitude'), 90), 'longitude': coordinate(item.get('longitude'), 180)}
        rows.append([ident, count(item.get('free_bikes')), count(item.get('empty_slots')), observed, flag(extra.get('renting')), flag(extra.get('returning'))])
    location = network.get('location') or {}
    info = {'id': setting['id'], 'name': str(network.get('name') or setting['id'])[:200], 'city': str(location.get('city') or '')[:200], 'country': str(location.get('country') or '')[:10], 'timezone': setting['timezone']}
    return {'schema': SCHEMA, 'network': info, 'stations': metadata, 'captures': [{'capturedAt': captured_at, 'rows': rows}], 'source': API+'/'+setting['id']}

def merge(previous, incoming, config):
    incoming = deepcopy(incoming)
    if not previous: return incoming
    if previous.get('schema') != SCHEMA or previous.get('network', {}).get('id') != incoming['network']['id']: raise ValueError('Previous archive identity invalid')
    latest = incoming['captures'][0]['capturedAt']
    threshold = (datetime.fromisoformat(latest.replace('Z', '+00:00')) - timedelta(days=config['historyDays'])).isoformat().replace('+00:00', 'Z')
    captures = {item['capturedAt']: item for item in previous['captures'] if item['capturedAt'] >= threshold}
    captures[latest] = incoming['captures'][0]
    incoming['captures'] = sorted(captures.values(), key=lambda x:x['capturedAt'])[-config['maxCapturesPerNetwork']:]
    used = {row[0] for item in incoming['captures'] for row in item['rows']}
    incoming['stations'] = {k:v for k,v in (previous['stations'] | incoming['stations']).items() if k in used}
    return incoming

def fetch(url, timeout):
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'CoolCode-DockDiary/1.0 (+https://coolcode.ca/dockdiary/)'})
    with urlopen(request, timeout=timeout) as response:
        data = response.read(30_000_001)
        if len(data) > 30_000_000: raise ValueError('API response too large')
        return json.loads(data)

def collect(root=ROOT):
    config = validate_config(json.loads((root/'web/config.json').read_text()))
    now = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    directory = fetch(API, config['requestTimeoutSeconds'])
    if not isinstance(directory.get('networks'), list) or not directory['networks']: raise ValueError('Network directory unavailable')
    networks = []
    for n in directory['networks']:
        if not SLUG.fullmatch(str(n.get('id', ''))): raise ValueError('Unexpected network ID')
        location = n.get('location') or {}
        networks.append({'id':n['id'], 'name':str(n.get('name',n['id'])), 'city':str(location.get('city','')), 'country':str(location.get('country',''))})
    outputs = {'networks.json': {'capturedAt':now, 'source':API, 'networks':networks}}
    summary = []
    for setting in config['trackedNetworks']:
        archive = normalize(fetch(API+'/'+setting['id'], config['requestTimeoutSeconds']), setting, now, config['maxStationsPerNetwork'])
        path = root/'web/data'/f"{setting['id']}.json"
        old = json.loads(path.read_text()) if path.exists() else None
        archive = merge(old, archive, config | {'maxCapturesPerNetwork':setting.get('maxCaptures',config['maxCapturesPerNetwork'])})
        outputs[path.name] = archive
        summary.append({'id':setting['id'], 'label':setting.get('label',archive['network']['name']), 'file':path.name, 'capturedAt':now, 'captures':len(archive['captures']), 'stations':len(archive['captures'][-1]['rows'])})
    outputs['index.json'] = {'schema':SCHEMA, 'capturedAt':now, 'networks':summary, 'historyDays':config['historyDays'], 'cadence':'Hourly target; GitHub schedules may be late or skipped'}
    dest=root/'web/data'; dest.mkdir(parents=True,exist_ok=True)
    # Validate every network before replacing any file. A failed fetch leaves the prior deployment intact.
    with tempfile.TemporaryDirectory(dir=dest) as temp:
        for name,data in outputs.items(): (Path(temp)/name).write_text(json.dumps(data, ensure_ascii=False, separators=(',',':'))+'\n')
        for name in outputs: (Path(temp)/name).replace(dest/name)
    print(f"Captured {len(summary)} network(s), {sum(x['stations'] for x in summary)} stations at {now}; directory {len(networks)} networks")

if __name__ == '__main__': collect()
