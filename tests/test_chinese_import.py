"""Integrity tests for the shipped Chinese collection and its safe EPUB importer.

Optional raw-source comparison:
    SHAKESPEARE_CHINESE_SOURCE=/path/to/expanded/epub python3 -m unittest discover -s tests
"""
import collections
import importlib.util
import json
import re
import html
import os
import shutil
import subprocess
import sys
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
        self.assertEqual([item["id"] for item in self.catalog], [f"part{x:04d}" for x in range(4, 43)])
        self.assertEqual(len(self.works), 39)
        plays = [w for w in self.works if w["kind"] == "play"]
        self.assertEqual(len(plays), 39)
        self.assertEqual(sum(w["translator"] == "朱生豪" for w in plays), 30)
        self.assertEqual(sum(w["translator"] != "朱生豪" and w["attributionStatus"] == "explicit" for w in plays), 8)
        uncertain = [w for w in plays if w["attributionStatus"] != "explicit"]
        self.assertEqual([(w["id"], w["translatorCredit"]) for w in uncertain], [("part0020", "朱豪译")])
        self.assertEqual(load_work("part0018")["translator"], "方平")
        self.assertTrue(all(w["kind"] == "play" for w in self.works))
        self.assertEqual({p.stem for p in (DATA / "works").glob("*.js")}, {w["id"] for w in self.works})
        self.assertEqual(self.manifest["scope"]["reader"], "39 plays only")
        self.assertEqual(self.manifest["counts"]["poetryUnits"], 0)
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
        self.assertEqual(len(seen_blocks), 40723)
        self.assertEqual(len(seen_sections), 1069)
        self.assertEqual(heading_counts["h3"], 200)
        self.assertEqual(heading_counts["h4"], 793)

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
        self.assertEqual(len(images), 234)
        self.assertEqual(len(set(images)), 216)
        self.assertEqual(len(all_links), 1008)
        self.assertEqual(source_ids, 2050)
        self.assertEqual({"data/chinese-collection/" + i["path"] for i in self.manifest["images"]}, set(images))
        self.assertEqual({p.name for p in (DATA / "images").iterdir() if p.is_file()}, {Path(i).name for i in images})
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


class EnglishScopeTests(unittest.TestCase):
    def test_play_catalogs_match_and_published_poetry_is_absent(self):
        chinese = json.loads((DATA / "catalog.json").read_text())
        english_dir = ROOT / "data" / "english-collection"
        english = json.loads((english_dir / "catalog.json").read_text())
        self.assertEqual(len(english), 39)
        self.assertEqual({w["englishId"] for w in chinese}, {w["id"] for w in english})
        self.assertTrue(all(w["kind"] == "play" for w in english))
        self.assertEqual({p.stem for p in english_dir.glob("*.js")} - {"catalog"}, {w["id"] for w in english})
        catalog_js = (english_dir / "catalog.js").read_text()
        self.assertEqual(json.loads(catalog_js.removeprefix("window.SHAKESPEARE_ENGLISH_CATALOG = ").removesuffix(";\n")), english)
        manifest = json.loads((english_dir / "sources" / "manifest.json").read_text())
        self.assertEqual(manifest["workCount"], 39)
        self.assertEqual(manifest["playCount"], 39)
        self.assertEqual(manifest["poetryCollectionCount"], 0)
        self.assertEqual(manifest["blockCount"], 39658)
        self.assertEqual(manifest["sectionCount"], 808)
        self.assertEqual(importer.sha256((english_dir / "sources" / manifest["mitSourceArchive"]).read_bytes()), manifest["mitArchiveSha256"])
        fixtures = json.loads((ROOT / "tests" / "fixtures" / "speech-turn-fixtures.json").read_text())
        for source in fixtures["sources"].values():
            self.assertEqual(importer.sha256((ROOT / source["englishPath"]).read_bytes()), source["englishSha256"])
            self.assertEqual(importer.sha256((ROOT / source["chinesePath"]).read_bytes()), source["chineseSha256"])

    def test_reviewed_role_cues_preserve_all_numbered_source_lines(self):
        english_dir = ROOT / "data" / "english-collection"
        cues = json.loads((english_dir / "sources" / "mit-embedded-role-cues.json").read_text())
        expected_cues = {(c["workId"], c["sourceAnchor"]): c for c in cues["occurrences"]}
        seen_cues = set()
        seen_split_prefixes = set()
        split_manifest = json.loads((english_dir / "sources" / "mit-split-role-prefixes.json").read_text())
        expected_splits = {(c["archiveEntry"].split("/")[0], c["sourceAnchor"]): c for c in split_manifest["occurrences"]}
        counts = collections.Counter()
        manifest = json.loads((english_dir / "sources" / "manifest.json").read_text())
        self.assertEqual(manifest["roleCueCount"], 108)
        self.assertEqual(cues["countsByWork"], {"1henryvi": 12, "2henryiv": 56, "2henryvi": 3, "coriolanus": 2, "henryviii": 1, "taming_shrew": 1, "timon": 33})
        with zipfile.ZipFile(english_dir / "sources" / manifest["mitSourceArchive"]) as archive:
            for item in json.loads((english_dir / "catalog.json").read_text()):
                if "sourceLineCount" not in item:
                    continue
                raw = archive.read(item["id"] + "/full.html").decode("utf-8")
                original_lines = [(match[1], html.unescape(match[2])) for match in re.finditer(r'<a\s+name=["\']?([\d.]+)["\']?>(.*?)</a>', raw, re.I | re.S)]
                self.assertEqual(len(original_lines), item["sourceLineCount"], item["id"])
                source_lines = dict(original_lines)
                payload = (english_dir / (item["id"] + ".js")).read_text().split("\n", 1)[1].split("=", 1)[1].strip().removesuffix(";")
                work = json.loads(payload)
                reconstructed = []
                for block in blocks(work):
                    if "sourceLine" not in block:
                        continue
                    lines = block["text"].split("\n")
                    prefix = block.get("sourceRolePrefix")
                    if prefix:
                        key = (item["id"], prefix["sourceAnchor"])
                        self.assertNotIn(key, seen_split_prefixes)
                        seen_split_prefixes.add(key)
                        self.assertEqual(prefix, expected_splits[key])
                        self.assertEqual(prefix["rawPrefix"], source_lines[prefix["sourceAnchor"]])
                        self.assertEqual(block["speaker"], prefix["joinedLabel"])
                        self.assertIn(prefix["originalHtml"], raw)
                        reconstructed.append(" ".join(prefix["rawPrefix"].split()))
                    correction = block.get("sourceMarkupCorrection")
                    if correction and correction["kind"] == "speaker_label_is_spoken_prefix":
                        self.assertTrue(lines[0].startswith(correction["rawLabelText"] + " "))
                        self.assertIn(correction["originalSpeakerMarkup"], raw)
                        lines[0] = lines[0][len(correction["rawLabelText"]) + 1:]
                        self.assertEqual(lines[0], correction["rawNumberedLineText"])
                    cue = block.get("sourceRoleCue")
                    if cue:
                        key = (item["id"], block["sourceLine"])
                        self.assertNotIn(key, seen_cues)
                        seen_cues.add(key)
                        expected = expected_cues[key]
                        self.assertEqual(cue["sourceAnchor"], block["sourceLine"])
                        self.assertEqual(cue["rawLineText"], source_lines[block["sourceLine"]])
                        self.assertEqual(cue["rawRolePrefix"], expected["rawRolePrefix"])
                        self.assertEqual(block["speaker"], expected["speaker"])
                        self.assertEqual(lines[0], " ".join(cue["rawLineText"].split("\t", 1)[1].split()))
                        lines[0] = cue["rawRolePrefix"] + "\t" + lines[0]
                        counts[item["id"]] += 1
                    reconstructed.extend(" ".join(line.split()) for line in lines)
                self.assertEqual(reconstructed, [" ".join(line.split()) for _, line in original_lines], item["id"])
        self.assertEqual(seen_cues, set(expected_cues))
        self.assertEqual(seen_split_prefixes, set(expected_splits))
        self.assertEqual(len(seen_split_prefixes), 320)
        self.assertEqual(dict(counts), cues["countsByWork"])

    def test_chief_justice_turns_and_non_role_tabs(self):
        directory = ROOT / "data" / "english-collection"
        def load(work_id):
            return json.loads((directory / (work_id + ".js")).read_text().split("\n", 1)[1].split("=", 1)[1].strip().removesuffix(";"))
        work = load("2henryiv")
        source_blocks = {b["sourceLine"]: b for b in blocks(work) if "sourceLine" in b}
        self.assertEqual(source_blocks["1.2.56"]["text"], "Wait, close; I will not see him.")
        self.assertEqual(source_blocks["1.2.56"]["speaker"], "FALSTAFF")
        self.assertEqual(source_blocks["1.2.57"]["text"], "What's he that goes there?")
        self.assertEqual(source_blocks["1.2.57"]["speaker"], "Lord Chief-Justice")
        self.assertEqual(source_blocks["1.2.58"]["speaker"], "Servant")
        self.assertEqual(source_blocks["1.2.59"]["speaker"], "Lord Chief-Justice")
        self.assertIn("Go, pluck him by the elbow; I must speak with him.", source_blocks["1.2.67"]["text"])
        self.assertEqual(source_blocks["1.2.67"]["speaker"], "Lord Chief-Justice")
        ordinary = next(b for b in blocks(work) if "Not I I tell thee what, Corporal Bardolph" in b["text"])
        self.assertNotEqual(ordinary.get("speaker"), "Not I")
        self.assertNotIn("sourceRoleCue", ordinary)
        # A separate upstream identity ambiguity is an explicit <b> source label.
        # This narrowly scoped extraction repair must not silently rename it.
        scene = next(s for s in load("timon")["sections"] if s["id"] == "3.2")
        self.assertTrue(any(b.get("speaker") == "LUCILIUS" for b in scene["blocks"]))

    def test_specific_markup_repairs_are_narrow_and_source_anchored(self):
        directory = ROOT / "data" / "english-collection"
        def load(work_id):
            return json.loads((directory / (work_id + ".js")).read_text().split("\n", 1)[1].split("=", 1)[1].strip().removesuffix(";"))
        for work_id, source_line, speaker, opening in [
            ("lll", "5.2.418", "BIRON", "Here stand I lady, dart thy skill at me;"),
            ("measure", "2.4.39", "ANGELO", "As long as you or I yet he must die."),
            ("julius_caesar", "1.1.63", "FLAVIUS", "This way will I disrobe the images,")]:
            block = next(b for b in blocks(load(work_id)) if b.get("sourceLine") == source_line)
            self.assertEqual(block["speaker"], speaker)
            self.assertEqual(block["text"].split("\n")[0], opening)
            self.assertIn("folger.edu", block["sourceMarkupCorrection"]["evidence"]["url"])
        for work_id, section_id, heading_line in [("1henryiv", "3.3", "3.2.182"), ("cymbeline", "2.3", "2.2.55")]:
            work = load(work_id)
            section = next(section for section in work["sections"] if section["id"] == section_id)
            self.assertEqual(section["scene"], 3)
            self.assertEqual(section["blocks"][0]["kind"], "heading")
            self.assertEqual(section["blocks"][0]["sourceLine"], heading_line)
            self.assertFalse(any(b.get("speaker") == "Scene III" for b in blocks(work)))
        edward = load("edwardiii")
        block = next(b for b in blocks(edward) if b.get("sourceAnchor") == "id00388")
        self.assertEqual(block["id"], "edwardiii:3.5:15")
        self.assertEqual(block["speaker"], "AUDLEY")
        self.assertEqual(block["text"], block["sourceMarkupCorrection"]["sourceText"])
        self.assertIsNone(block["sourceMarkupCorrection"]["rawSpeakerLabel"])
        self.assertIn("internetshakespeare.uvic.ca", block["sourceMarkupCorrection"]["evidence"]["url"])
        raw = (directory / "sources" / "gutenberg-1770.html").read_text()
        self.assertIn(block["sourceMarkupCorrection"]["rawSourceParagraph"], raw)

    def test_english_rebuild_is_plays_only_and_exactly_reproducible(self):
        english_dir = ROOT / "data" / "english-collection"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            shutil.copytree(english_dir / "sources", output / "sources")
            (output / "sonnets.js").write_text("stale prior poetry output")
            subprocess.run([sys.executable, str(ROOT / "scripts" / "import_english.py"), "--output", str(output)], check=True, capture_output=True, text=True)
            expected_files = {p.name for p in english_dir.glob("*.js")}
            self.assertEqual({p.name for p in output.glob("*.js")}, expected_files)
            for filename in expected_files | {"catalog.json"}:
                self.assertEqual((output / filename).read_bytes(), (english_dir / filename).read_bytes(), filename)
            self.assertEqual((output / "sources" / "manifest.json").read_bytes(), (english_dir / "sources" / "manifest.json").read_bytes())


class ImporterTests(unittest.TestCase):
    def test_chinese_rebuild_prunes_only_old_reader_assets_when_source_available(self):
        source = Path(os.environ.get("SHAKESPEARE_CHINESE_SOURCE", "/workspace/shared/shakespeare-source-staging/extracted/original-epub"))
        if (source / "original-epub").is_dir():
            source /= "original-epub"
        if not (source / "text" / "part0004.html").is_file():
            self.skipTest("Set SHAKESPEARE_CHINESE_SOURCE for independent original EPUB rebuild")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "works").mkdir()
            (output / "images").mkdir()
            (output / "works" / "part0046.js").write_text("stale prior poetry output")
            (output / "images" / "poetry-old.jpeg").write_bytes(b"stale prior poetry image")
            (output / "images" / "unrelated.txt").write_text("keep unrelated files")
            (output / "manifest.json").write_text(json.dumps({"images": [{"path": "images/poetry-old.jpeg"}]}))
            expected_manifest = json.loads((DATA / "manifest.json").read_text())
            result = importer.import_collection(source, output, expected_manifest["source"]["epubSha256"])
            self.assertEqual(result, expected_manifest)
            self.assertFalse((output / "works" / "part0046.js").exists())
            self.assertFalse((output / "images" / "poetry-old.jpeg").exists())
            self.assertEqual((output / "images" / "unrelated.txt").read_text(), "keep unrelated files")
            self.assertEqual({p.name for p in (output / "works").glob("*.js")}, {p.name for p in (DATA / "works").glob("*.js")})
            for original in (DATA / "works").glob("*.js"):
                self.assertEqual((output / "works" / original.name).read_bytes(), original.read_bytes(), original.name)
            for filename in ("catalog.js", "catalog.json", "manifest.json"):
                self.assertEqual((output / filename).read_bytes(), (DATA / filename).read_bytes(), filename)

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
