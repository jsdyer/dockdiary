"""Exercise actual saved data, filters, history and export at a project subpath."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import shutil
import tempfile
import threading
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
class QuietHandler(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass

def main():
 screenshots=ROOT/'browser-checks';screenshots.mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory() as temporary:
  shutil.copytree(ROOT/'dist',Path(temporary)/'dockdiary')
  server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=temporary));threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   with sync_playwright() as p:
    browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.route('**/assets/tool-metrics.js',lambda route:route.fulfill(status=200,body=''))
    page.goto(f'http://127.0.0.1:{server.server_port}/dockdiary/')
    page.locator('.station-result').first.wait_for()
    assert int(page.locator('#station-count').inner_text().replace(',',''))>0
    assert page.locator('#network').locator('option').count()>100
    first_name=page.locator('.station-result strong').first.inner_text()
    page.locator('#station-search').fill(first_name)
    assert page.locator('.station-result').count()>0
    page.locator('.station-result').first.click()
    assert first_name == page.locator('#station-name').inner_text()
    assert page.locator('#heatmap button').count()==168
    page.locator('#heatmap button').first.click();assert 'observations' in page.locator('#cell-note').inner_text()
    page.locator('#station-search').fill('No such station xyz');assert 'No matching stations' in page.locator('#stations').inner_text()
    page.locator('#station-search').fill('');page.locator('.station-result').first.click()
    with page.expect_download() as event:page.locator('#csv').click()
    assert event.value.suggested_filename.endswith('.csv')
    # Reject an API failure without destroying the currently displayed station.
    name=page.locator('#station-name').inner_text()
    page.route('https://api.citybik.es/v2/networks/*',lambda route:route.fulfill(status=503,body='unavailable'))
    page.locator('#refresh').click();page.wait_for_function("document.querySelector('#status').textContent.includes('unchanged')")
    assert page.locator('#station-name').inner_text()==name
    page.screenshot(path=str(screenshots/'desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), page.evaluate('({viewport:innerWidth,page:document.documentElement.scrollWidth,detail:document.querySelector(".detail").getBoundingClientRect().width})')
    # Wide weekday/hour tables scroll inside the detail column, never the page.
    assert page.locator('.heatmap-wrap').evaluate('(el) => el.scrollWidth > el.clientWidth')
    assert page.locator('.detail').evaluate('(el) => el.getBoundingClientRect().right <= innerWidth')
    page.screenshot(path=str(screenshots/'mobile.png'),full_page=True)
    # City guides and their individual station links must reopen the matching network and station.
    toronto=page.get_by_role('link',name='Toronto',exact=True)
    toronto.click();page.get_by_role('heading',name='Toronto bike-share stations and return spaces').wait_for()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('.city-page details summary').first.click()
    station_link=page.locator('.city-page details[open] tbody th a').first
    linked_name=station_link.inner_text()
    station_link.click();page.wait_for_function("text=>document.querySelector('#station-name').textContent.trim()===text.trim()",arg=linked_name)
    assert page.locator('#network').input_value()=='bixi-toronto'
    assert not errors,errors;browser.close()
   print('Browser checks passed: real capture, directory, filters, history, CSV, failure retention and mobile layout')
  finally:server.shutdown()
if __name__=='__main__':main()
