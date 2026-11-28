import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from xml.etree import ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build import ROOT, build, metadata
from cities import summary


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copytree(ROOT / "web", self.root / "web")
        shutil.copyfile(ROOT / "tool.json", self.root / "tool.json")
        shutil.copyfile(ROOT / "README.md", self.root / "README.md")

    def edit(self, **changes):
        tool = json.loads((self.root / "tool.json").read_text())
        tool.update(changes)
        (self.root / "tool.json").write_text(json.dumps(tool))

    def test_build_is_scoped_to_web_and_escapes_metadata(self):
        (self.root / "private.txt").write_text("must not publish")
        self.edit(title='<img src=x onerror="bad()">')
        build(self.root)
        page = (self.root / "dist/index.html").read_text()
        self.assertIn('&lt;img', page)
        self.assertNotIn('<img', page)
        self.assertNotIn('{{', page)
        self.assertIn('href="./style.css"', page)
        self.assertFalse((self.root / "dist/private.txt").exists())
        self.assertTrue((self.root / "dist/.nojekyll").exists())

    def test_reporting_is_scoped_to_initialized_coolcode_tools(self):
        for owner, slug, enabled in [
            ("jsdyer", "coolcode-tool-template", False),
            ("another-owner", "my-tool", False),
            ("jsdyer", "my-tool", True),
        ]:
            with self.subTest(owner=owner, slug=slug):
                self.edit(id=slug, url=f"/{slug}/", source=f"https://github.com/{owner}/{slug}")
                build(self.root)
                page = (self.root / "dist/index.html").read_text()
                self.assertEqual('/assets/tool-metrics.js' in page, enabled)
                self.assertEqual(f'https://coolcode.ca/report/?tool={slug}' in page, enabled)
                self.assertNotIn("{{", page)

    def test_retained_networks_have_canonical_pages_and_station_links(self):
        build(self.root)
        dist = self.root / "dist"
        config = json.loads((dist / "config.json").read_text())
        index = json.loads((dist / "data/index.json").read_text())
        locs = {loc.text for loc in ET.parse(dist / "sitemap.xml").iterfind(".//{*}loc")}
        for item in index["networks"]:
            network = next(n for n in config["trackedNetworks"] if n["id"] == item["id"])
            path = f'cities/{network["slug"]}/'
            self.assertIn('https://coolcode.ca/dockdiary/' + path, locs)
            markup = (dist / path / "index.html").read_text()
            self.assertIn(f'?network={network["id"]}&amp;station=', markup)
            self.assertIn("Stations with spaces", markup)
            self.assertIn(network["city"], markup)

    def test_city_summary_distinguishes_zero_unknown_stale_and_paused(self):
        at = "2026-11-28T10:00:00Z"
        rows = [["a", 3, 0, at, True, True], ["b", None, 2, at, True, True],
                ["c", 4, None, at, False, True], ["d", 8, 8, "2026-11-28T08:59:00Z", True, True]]
        self.assertEqual(summary({"capturedAt": at, "rows": rows}, 60), ["1 of 1", "1 of 2"])

    def test_url_matches_tool_id(self):
        self.edit(url="/different/")
        with self.assertRaises(ValueError): metadata(self.root)

    def test_requires_a_source_sentence_and_a_guide_note(self):
        (self.root / "README.md").write_text("# A tool")
        with self.assertRaisesRegex(ValueError, "README note"):
            metadata(self.root)
        self.edit(data_info={"mode": "local", "detail": ""})
        with self.assertRaisesRegex(ValueError, "homepage card"):
            metadata(self.root)

    def test_browser_access_is_explicit(self):
        self.edit(access="install")
        with self.assertRaisesRegex(ValueError, "immediately usable"):
            metadata(self.root)

    def test_failed_build_keeps_existing_output(self):
        build(self.root)
        existing = (self.root / "dist/index.html").read_bytes()
        self.edit(source="javascript:bad()")
        with self.assertRaises(ValueError): build(self.root)
        self.assertEqual((self.root / "dist/index.html").read_bytes(), existing)


if __name__ == "__main__": unittest.main()
