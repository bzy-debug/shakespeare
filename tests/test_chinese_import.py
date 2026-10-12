"""Integrity tests for the shipped Chinese collection and its safe EPUB importer.

Optional raw-source comparison:
    SHAKESPEARE_CHINESE_SOURCE=/path/to/expanded/epub python3 -m unittest discover -s tests
"""
import collections
import importlib.util
import json
import os
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "chinese-collection"
spec = importlib.util.spec_from_file_location("import_chinese", ROOT / "scripts" / "import_chinese.py")
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


class Fragment(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.nodes = []
        self.text = []
        self.feed(markup)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        self.text.append(data)


def load_work(work_id):
    content = (DATA / "works" / (work_id + ".js")).read_text()
    prefix = f'window.SHAKESPEARE_CHINESE = window.SHAKESPEARE_CHINESE || {{}};\nwindow.SHAKESPEARE_CHINESE["{work_id}"]='
    if not content.startswith(prefix):
        raise AssertionError("Unexpected lazy-loading JavaScript wrapper")
    return json.loads(content[len(prefix):].removesuffix(";\n"))


def blocks(work):
    return [block for section in work["sections"] for block in section["blocks"]]


class CollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((DATA / "catalog.json").read_text())
        cls.manifest = json.loads((DATA / "manifest.json").read_text())
        cls.works = [load_work(item["id"]) for item in cls.catalog]

    def test_complete_catalog_and_explicit_credits(self):
        self.assertEqual([item["id"] for item in self.catalog], [f"part{x:04d}" for x in range(4, 47)])
        self.assertEqual(len(self.works), 43)
        plays = [w for w in self.works if w["kind"] == "play"]
        self.assertEqual(len(plays), 39)
        self.assertEqual(sum(w["translator"] == "朱生豪" for w in plays), 30)
        self.assertEqual(sum(w["translator"] != "朱生豪" and w["attributionStatus"] == "explicit" for w in plays), 8)
        uncertain = [w for w in plays if w["attributionStatus"] != "explicit"]
        self.assertEqual([(w["id"], w["translatorCredit"]) for w in uncertain], [("part0020", "朱豪译")])
        self.assertEqual(load_work("part0018")["translator"], "方平")
        self.assertEqual(load_work("part0045")["translator"], "梁宗岱")
        self.assertEqual(set(load_work("part0046")["englishIds"]), {"lovers_complaint", "passionate_pilgrim", "sundry_notes_of_music", "phoenix_and_turtle"})
        js = (DATA / "catalog.js").read_text()
        self.assertEqual(json.loads(js.removeprefix("window.SHAKESPEARE_CHINESE_CATALOG=").removesuffix(";\n")), self.catalog)

    def test_no_lost_or_duplicate_blocks_headings_or_text(self):
        seen_blocks = set()
        seen_sections = set()
        heading_counts = collections.Counter()
        for item, work in zip(self.catalog, self.works):
            work_blocks = blocks(work)
            self.assertEqual(len(work_blocks), item["blockCount"])
            self.assertEqual(len(work["sections"]), item["sectionCount"])
            self.assertEqual([b["id"] for b in work_blocks], [f'{work["id"]}-{i:05d}' for i in range(len(work_blocks))])
            text = "".join(b["text"] for b in work_blocks)
            self.assertEqual(importer.sha256(text), work["source"]["textSha256"])
            for section in work["sections"]:
                self.assertNotIn(section["id"], seen_sections)
                seen_sections.add(section["id"])
                self.assertTrue(section["blocks"])
                for block in section["blocks"]:
                    self.assertNotIn(block["id"], seen_blocks)
                    seen_blocks.add(block["id"])
                    fragment = Fragment(block["html"])
                    self.assertEqual("".join(fragment.text), block["text"])
                    heading_counts[block["tag"]] += 1
            self.assertEqual(work["alignment"], "none")
        self.assertEqual(len(seen_blocks), 47598)
        self.assertEqual(len(seen_sections), 1258)
        self.assertEqual(heading_counts["h3"], 207)
        self.assertEqual(heading_counts["h4"], 967)

    def test_safe_html_images_and_all_nested_anchor_targets(self):
        all_ids = set()
        images = []
        all_links = []
        source_ids = 0
        for work in self.works:
            work_ids, links, work_images = set(), [], []
            for section in work["sections"]:
                for block in section["blocks"]:
                    for tag, attrs in Fragment(block["html"]).nodes:
                        self.assertIn(tag, importer.ALLOWED_TAGS)
                        self.assertLessEqual(set(attrs), {"id", "class", "src", "alt", "loading", "width", "height", "href", "data-source-anchor"})
                        self.assertTrue(all(not key.startswith("on") for key in attrs))
                        if "id" in attrs:
                            self.assertNotIn(attrs["id"], all_ids)
                            all_ids.add(attrs["id"])
                            work_ids.add(attrs["id"])
                            original = attrs["id"].removeprefix("epub-" + work["id"] + "-")
                            self.assertEqual(work["source"]["anchorSections"][original], section["id"])
                        if tag == "a" and "href" in attrs:
                            self.assertTrue(attrs["href"].startswith("#epub-" + work["id"] + "-"))
                            links.append(attrs["href"][1:])
                            self.assertIn(attrs["data-source-anchor"], work["source"]["anchorSections"])
                        if tag == "img":
                            self.assertTrue(attrs["src"].startswith("data/chinese-collection/images/"))
                            self.assertTrue((ROOT / attrs["src"]).is_file())
                            self.assertIn("epub-image", attrs["class"].split())
                            work_images.append(attrs["src"])
            self.assertLessEqual(set(links), work_ids)
            self.assertEqual(len(work_ids), len(work["source"]["anchorSections"]))
            self.assertEqual(len(work_images), work["source"]["imageCount"])
            images.extend(work_images)
            all_links.extend(links)
            source_ids += len(work_ids)
        self.assertEqual(len(images), 240)
        self.assertEqual(len(set(images)), 222)
        self.assertEqual(len(all_links), 1206)
        self.assertEqual(source_ids, 2434)
        for image in self.manifest["images"]:
            self.assertEqual(importer.sha256((DATA / image["path"]).read_bytes()), image["sha256"])

    def test_scene_context_and_retained_prefaces_and_notes(self):
        gentlemen = load_work("part0004")
        sections = gentlemen["sections"]
        self.assertEqual(sections[0]["kind"], "preface")
        scene = next(s for s in sections if s.get("actNumber") == 2 and s.get("sceneNumber") == 1)
        self.assertEqual(scene["label"], "第二幕 · 第一场 米兰。公爵府中一室")
        self.assertEqual(sections[-1]["label"], "注释")
        self.assertEqual(sections[-1]["blocks"][0]["tag"], "hr")
        self.assertEqual(sum(s.get("sceneNumber") is not None for s in load_work("part0007")["sections"] if s.get("actNumber") == 0), 2)

    def test_exact_original_body_text_and_image_sequence_when_source_available(self):
        source = Path(os.environ.get("SHAKESPEARE_CHINESE_SOURCE", "/workspace/shared/shakespeare-source-staging/extracted/original-epub"))
        if (source / "original-epub").is_dir():
            source /= "original-epub"
        if not (source / "text" / "part0004.html").is_file():
            self.skipTest("Set SHAKESPEARE_CHINESE_SOURCE for independent original EPUB comparison")
        for work in self.works:
            original = ET.parse(source / work["source"]["path"]).getroot().find("{*}body")
            self.assertEqual("".join(original.itertext()), "".join(b["text"] for b in blocks(work)))
            self.assertEqual(len(original), len(blocks(work)))
            source_images = [Path(n.attrib["src"]).name for n in original.iter() if importer.local_name(n.tag) == "img"]
            output_images = [Path(attrs["src"]).name for b in blocks(work) for tag, attrs in Fragment(b["html"]).nodes if tag == "img"]
            self.assertEqual(source_images, output_images)
            source_credit = next("".join(n.itertext()).strip() for n in original if importer.local_name(n.tag) == "p" and "".join(n.itertext()).strip() == work["translatorCredit"])
            self.assertEqual(source_credit, work["translatorCredit"])


class ImporterTests(unittest.TestCase):
    def test_sanitizer_blocks_active_content_and_external_links(self):
        node = ET.fromstring('<p id="one" onclick="evil()" style="color:red">Hello<a href="https://example.com/a">world</a><a href="javascript:evil()">X</a><a href="../../outside#one">Y</a><script>evil()</script>tail<iframe>hidden</iframe>end<a id="nested" href="part0004.html#one">note</a></p>')
        cleaned = importer.sanitize_element(node, "part0004", "text/part0004.html", {"text/part0004.html": {"one", "nested"}}, {})
        markup = ET.tostring(cleaned, encoding="unicode", method="html")
        self.assertNotIn("evil", markup)
        self.assertNotIn("hidden", markup)
        self.assertNotIn("style=", markup)
        self.assertNotIn("https:", markup)
        self.assertNotIn("javascript:", markup)
        self.assertIn('href="#epub-part0004-one"', markup)
        self.assertIn('id="epub-part0004-nested"', markup)
        self.assertEqual("".join(Fragment(markup).text), "HelloworldXYtailendnote")

    def test_child_tail_preserved_once_and_all_nested_anchors_registered(self):
        body = ET.fromstring('<body>lead<p id="head">A<b>B</b>C<a id="inside"></a>D</p>tail<h3 id="act">第一幕</h3>after<h4 id="scene">第一场 室内</h4>next<p>LAST</p>ending</body>')
        info = {"id": "part0004", "title": "Test", "translator": "朱生豪", "translatorCredit": "朱生豪译", "attributionStatus": "explicit", "kind": "play", "body": body, "sourcePath": "text/part0004.html"}
        transformed = importer.transform_work(info, {"text/part0004.html": {"head", "inside", "act", "scene"}}, {}, {})
        self.assertEqual("".join(body.itertext()), "".join(b["text"] for b in blocks(transformed)))
        self.assertEqual(len(blocks(transformed)), 4)
        self.assertEqual(transformed["source"]["anchorSections"]["inside"], transformed["sections"][0]["id"])

    def test_unsafe_archive_paths_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            archive = temp / "bad.epub"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("../escape.txt", "bad")
            with self.assertRaises(ValueError):
                importer.extract_epub(archive, temp / "out")


if __name__ == "__main__":
    unittest.main()
