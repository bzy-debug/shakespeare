#!/usr/bin/env python3
"""Import only the 39 plays from the supplied Chinese EPUB, without downloads.

Usage:
    python3 scripts/import_chinese.py --epub /path/to/book.epub
    python3 scripts/import_chinese.py --source /path/to/extracted/original-epub

Only Python's standard library is used. The second form accepts an expanded EPUB
or the prior staging directory containing original-epub/ and manifest.json.
The edition's work boundaries are checked against its actual h2 headings. No
translator attribution is inferred from the book cover or English counterpart.
Poetry is intentionally outside the reader scope; the original EPUB is unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import tempfile
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile

REPOSITORY = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY / "data" / "chinese-collection"
WORKS = [
    ("维洛那二绅士", "two_gentlemen"), ("爱的徒劳", "lll"),
    ("罗密欧与朱丽叶", "romeo_juliet"), ("驯悍记", "taming_shrew"),
    ("错误的喜剧", "comedy_errors"), ("约翰王", "john"),
    ("仲夏夜之梦", "midsummer"), ("威尼斯商人", "merchant"),
    ("理查二世", "richardii"), ("亨利四世上篇", "1henryiv"),
    ("亨利四世下篇", "2henryiv"), ("温莎的风流娘儿们", "merry_wives"),
    ("无事生非", "much_ado"), ("终成眷属", "allswell"),
    ("亨利五世", "henryv"), ("皆大欢喜", "asyoulikeit"),
    ("泰尔亲王配力克里斯", "pericles"), ("第十二夜", "twelfth_night"),
    ("亨利六世上篇", "1henryvi"), ("亨利六世中篇", "2henryvi"),
    ("亨利六世下篇", "3henryvi"), ("雅典的泰门", "timon"),
    ("理查三世", "richardiii"), ("一报还一报", "measure"),
    ("亨利八世", "henryviii"), ("辛白林", "cymbeline"),
    ("李尔王", "lear"), ("科利奥兰纳斯", "coriolanus"),
    ("暴风雨", "tempest"), ("冬天的故事", "winters_tale"),
    ("特洛伊罗斯与克瑞西达", "troilus_cressida"), ("麦克白", "macbeth"),
    ("裘力斯·凯撒", "julius_caesar"), ("哈姆莱特", "hamlet"),
    ("安东尼与克莉奥佩特拉", "cleopatra"), ("泰特斯·安德洛尼克斯", "titus"),
    ("奥瑟罗", "othello"), ("爱德华三世", "edwardiii"),
    ("两位贵亲戚", "two_noble_kinsmen"),
]
ALLOWED_TAGS = frozenset("p b strong i em a h1 h2 h3 h4 h5 h6 br sup sub img hr span div ul ol li blockquote small".split())
# These may contain active content and are removed as entire subtrees.
DROP_TAGS = frozenset("script style iframe object embed form input button textarea select link meta base svg math".split())
SAFE_CLASS = re.compile(r"^[A-Za-z_][A-Za-z_0-9-]*$")
SAFE_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def sha256(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def element_text(element: ET.Element) -> str:
    return "".join(element.itertext())


def chinese_number(value: str) -> int | None:
    digits = dict(zip("〇零一二三四五六七八九", [0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9]))
    if value.isdecimal():
        return int(value)
    if value in digits:
        return digits[value]
    if "十" in value and value.count("十") == 1:
        tens, ones = value.split("十")
        if (not tens or tens in digits) and (not ones or ones in digits):
            return (digits.get(tens, 1) * 10) + digits.get(ones, 0)
    return None


def source_path(relative: str, current: str) -> str:
    """Resolve an EPUB-local URI without permitting traversal or remote URLs."""
    parsed = urlsplit(relative)
    if parsed.scheme or parsed.netloc or parsed.query:
        raise ValueError(f"Not an EPUB-local path: {relative!r}")
    path = posixpath.normpath(posixpath.join(posixpath.dirname(current), unquote(parsed.path)))
    if path == ".." or path.startswith("../") or path.startswith("/") or "\\" in path:
        raise ValueError(f"Unsafe EPUB path: {relative!r}")
    return path


def source_anchor(work_id: str, anchor: str) -> str:
    # The import checks source IDs and preserves their exact spelling after a prefix.
    return f"epub-{work_id}-{anchor}"


def sanitize_element(element: ET.Element, work_id: str, current: str,
                     anchors: dict[str, set[str]], assets: dict[str, str]) -> ET.Element | None:
    """Clone into a tiny HTML allowlist; never copy script, style, or event attrs."""
    tag = local_name(element.tag).lower()
    if tag in DROP_TAGS:
        return None
    result = ET.Element(tag if tag in ALLOWED_TAGS else "span")
    result.text = element.text
    result.tail = element.tail
    if element.get("id"):
        result.set("id", source_anchor(work_id, element.get("id")))
    classes = ["epub-" + item for item in element.get("class", "").split() if SAFE_CLASS.fullmatch(item)]
    if tag == "img":
        classes.append("epub-image")
        original = source_path(element.get("src", ""), current)
        if original not in assets:
            raise ValueError(f"Missing or unsupported source image: {original}")
        result.set("src", "data/chinese-collection/images/" + assets[original])
        result.set("alt", element.get("alt", ""))
        result.set("loading", "lazy")
        for attribute in ("width", "height"):
            if re.fullmatch(r"[1-9][0-9]{0,4}", element.get(attribute, "")):
                result.set(attribute, element.get(attribute))
    if classes:
        result.set("class", " ".join(classes))
    if tag == "a" and element.get("href"):
        parsed = urlsplit(element.get("href"))
        target_file = None
        if not parsed.scheme and not parsed.netloc and not parsed.query:
            try:
                target_file = source_path(parsed.path, current) if parsed.path else current
            except ValueError:
                pass
        target_anchor = unquote(parsed.fragment)
        # Only same-work, known source anchors are interactive; never preserve URLs.
        if not parsed.scheme and not parsed.netloc and not parsed.query and target_file == current and target_anchor in anchors[current]:
            result.set("href", "#" + source_anchor(work_id, target_anchor))
            result.set("data-source-anchor", target_anchor)
    for child in element:
        cleaned = sanitize_element(child, work_id, current, anchors, assets)
        if cleaned is not None:
            result.append(cleaned)
        elif child.tail:
            # Removing a dangerous subtree must not remove the following prose.
            if len(result):
                result[-1].tail = (result[-1].tail or "") + child.tail
            else:
                result.text = (result.text or "") + child.tail
    return result


def inspect_source(root: Path) -> tuple[list[dict], dict[str, set[str]], dict[str, str]]:
    works = []
    anchors = {}
    assets = {}
    for index, (expected_title, english_id) in enumerate(WORKS, 4):
        work_id = f"part{index:04d}"
        relative = f"text/{work_id}.html"
        body = ET.parse(root / relative).getroot().find("{*}body")
        if body is None:
            raise ValueError(f"Missing body: {relative}")
        title = next((element_text(child).strip() for child in body if local_name(child.tag) == "h2"), None)
        if title != expected_title:
            raise ValueError(f"Unexpected work title for {work_id}: {title!r}; expected {expected_title!r}")
        credit = next((element_text(child).strip() for child in body if local_name(child.tag) == "p" and re.fullmatch(r"[\u3400-\u9fff]{2,4}\s*译", element_text(child).strip())), None)
        if credit is None:
            raise ValueError(f"No explicit translator credit: {relative}")
        translator = re.sub(r"\s*译$", "", credit)
        ids = [node.get("id") for node in body.iter() if node.get("id")]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate source IDs in {relative}")
        anchors[relative] = set(ids)
        for node in body.iter():
            if local_name(node.tag) == "img":
                original = source_path(node.get("src", ""), relative)
                path = root / original
                if not path.is_file() or path.suffix.lower() not in SAFE_IMAGE_SUFFIXES:
                    raise ValueError(f"Missing or unsupported image {original}")
                basename = path.name
                if basename in assets.values() and assets.get(original) != basename:
                    raise ValueError(f"Image basename collision: {original}")
                assets[original] = basename
        works.append({"id": work_id, "title": title, "translator": translator,
                      "translatorCredit": credit,
                      "attributionStatus": "source-credit-uncertain" if translator == "朱豪" else "explicit",
                      "attributionNote": "原书署名为“朱豪译”，保留原文，不自动更正为朱生豪。" if translator == "朱豪" else None,
                      "kind": "play",
                      "englishId": english_id, "body": body, "sourcePath": relative})
    return works, anchors, assets


def transform_work(info: dict, anchors: dict[str, set[str]], assets: dict[str, str], source: dict) -> dict:
    body, current, work_id = info["body"], info["sourcePath"], info["id"]
    sections = []
    current_section = None
    context = ""
    act_number = None
    anchor_sections = {}
    image_occurrences = 0
    original_text = element_text(body)

    def start_section(label: str, kind: str, node: ET.Element | None = None) -> dict:
        section = {"id": f"{work_id}-section-{len(sections):03d}", "label": label, "kind": kind, "blocks": []}
        if node is not None:
            section["heading"] = element_text(node).strip()
            section["headingLevel"] = int(local_name(node.tag)[1:]) if local_name(node.tag) in ("h3", "h4") else None
            section["sourceAnchor"] = node.get("id")
        if act_number is not None and kind != "notes":
            section["actNumber"] = act_number
        sections.append(section)
        return section

    for index, child in enumerate(body):
        tag = local_name(child.tag)
        heading = element_text(child).strip()
        if tag == "h3":
            context = heading
            match = re.match(r"^第([〇零一二三四五六七八九十\d]+)幕", heading)
            act_number = chinese_number(match.group(1)) if match else (0 if heading == "序幕" else None)
            current_section = start_section(heading, "act" if act_number is not None else "heading", child)
        elif tag == "h4":
            label = f"{context} · {heading}" if context and context != heading else heading
            current_section = start_section(label, "scene" if info["kind"] == "play" else "poem", child)
            match = re.match(r"^第([〇零一二三四五六七八九十\d]+)场", heading)
            if match:
                current_section["sceneNumber"] = chinese_number(match.group(1))
        elif tag == "hr" and any("note" in node.get("class", "").split() for node in list(body)[index + 1:index + 2]):
            current_section = start_section("注释", "notes", child)
        if current_section is None:
            current_section = start_section("书前与人物" if info["kind"] == "play" else "书前与译者", "preface")
        cleaned = sanitize_element(child, work_id, current, anchors, assets)
        if cleaned is None:
            raise ValueError(f"Active top-level element in source: {current}, {tag}")
        # ET includes child.tail in serialization but excludes it from child.itertext().
        # Include body.text once, then each top-level child and its tail exactly once.
        leading = (body.text or "") if index == 0 else ""
        block_html = html.escape(leading) + ET.tostring(cleaned, encoding="unicode", method="html")
        block_text = leading + element_text(cleaned) + (cleaned.tail or "")
        block = {"id": f"{work_id}-{index:05d}", "html": block_html, "text": block_text,
                 "sourceAnchor": child.get("id"), "tag": tag}
        current_section["blocks"].append(block)
        for node in child.iter():
            if node.get("id"):
                anchor_sections[node.get("id")] = current_section["id"]
            if local_name(node.tag) == "img":
                image_occurrences += 1
    combined_text = "".join(block["text"] for section in sections for block in section["blocks"])
    if combined_text != original_text:
        raise ValueError(f"Text loss detected while sanitizing {work_id}")
    result = {key: value for key, value in info.items() if key not in ("body", "sourcePath") and value is not None}
    result["sections"] = sections
    result["language"] = "zh"
    result["alignment"] = "none"
    result["source"] = {**source, "path": current, "blockCount": len(body), "imageCount": image_occurrences,
                        "textSha256": sha256(original_text), "anchorSections": anchor_sections,
                        "note": "用户提供的多译者 EPUB；保留原书署名、注释与图像。未作逐句双语对齐。"}
    return result


def serialize_js(value: object) -> str:
    # Escaping < also prevents an accidental closing script tag if embedded later.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def import_collection(root: Path, output: Path, epub_sha256: str | None = None) -> dict:
    if (root / "original-epub").is_dir():
        root = root / "original-epub"
    staged_manifest = root.parent / "manifest.json"
    staged_source = json.loads(staged_manifest.read_text()).get("source", {}) if staged_manifest.is_file() else {}
    source = {"type": "user-provided-epub", "title": "莎士比亚全集", "publisher": "人民文学出版社",
              "isbn": "978-7-02-010568-7", "epubSha256": epub_sha256 or staged_source.get("sha256"),
              "attribution": "朱生豪等译（逐作保留原书署名）"}
    infos, anchors, assets = inspect_source(root)
    works = [transform_work(info, anchors, assets, source) for info in infos]
    # Prune only assets documented by a previous import. Original EPUB bytes and
    # unrelated files remain untouched when rebuilding an existing reader folder.
    previous_manifest = output / "manifest.json"
    old_images = json.loads(previous_manifest.read_text()).get("images", []) if previous_manifest.is_file() else []
    output.mkdir(parents=True, exist_ok=True)
    (output / "works").mkdir(exist_ok=True)
    (output / "images").mkdir(exist_ok=True)
    for original, filename in sorted(assets.items()):
        shutil.copyfile(root / original, output / "images" / filename)
    for index in range(43, 47):
        (output / "works" / f"part{index:04d}.js").unlink(missing_ok=True)
    for image in old_images:
        relative = PurePosixPath(image["path"])
        if len(relative.parts) == 2 and relative.parts[0] == "images" and relative.name not in assets.values():
            (output / "images" / relative.name).unlink(missing_ok=True)
    catalog = []
    for work in works:
        (output / "works" / (work["id"] + ".js")).write_text(
            "window.SHAKESPEARE_CHINESE = window.SHAKESPEARE_CHINESE || {};\n"
            f"window.SHAKESPEARE_CHINESE[{json.dumps(work['id'])}]=" + serialize_js(work) + ";\n", encoding="utf-8")
        item = {key: work[key] for key in ("id", "title", "translator", "translatorCredit", "attributionStatus", "attributionNote", "kind", "englishId", "englishIds") if key in work}
        item.update(sectionCount=len(work["sections"]), blockCount=work["source"]["blockCount"], imageCount=work["source"]["imageCount"], file="data/chinese-collection/works/" + work["id"] + ".js")
        catalog.append(item)
    (output / "catalog.js").write_text("window.SHAKESPEARE_CHINESE_CATALOG=" + serialize_js(catalog) + ";\n", encoding="utf-8")
    (output / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"schemaVersion": 1, "source": source,
               "scope": {"reader": "39 plays only", "includedWorkIds": [w["id"] for w in works],
                         "excludedSourceUnits": ["part0043", "part0044", "part0045", "part0046"],
                         "note": "Only the 39 play units are published in this reader. The complete original EPUB is preserved separately, including its poetry."},
               "counts": {"totalUnits": len(works), "playUnits": sum(w["kind"] == "play" for w in works),
                          "poetryUnits": sum(w["kind"] != "play" for w in works),
                          "sections": sum(len(w["sections"]) for w in works),
                          "blocks": sum(w["source"]["blockCount"] for w in works),
                          "imageOccurrences": sum(w["source"]["imageCount"] for w in works),
                          "uniqueImageFiles": len(assets),
                          "explicitZhuShenghaoPlays": sum(w["kind"] == "play" and w["translator"] == "朱生豪" and w["attributionStatus"] == "explicit" for w in works),
                          "otherExplicitPlayCredits": sum(w["kind"] == "play" and w["translator"] != "朱生豪" and w["attributionStatus"] == "explicit" for w in works),
                          "uncertainPlayCredits": sum(w["kind"] == "play" and w["attributionStatus"] != "explicit" for w in works)},
               "validation": {"allBodyTextPreserved": True, "textComparison": "exact concatenation for each included play, including all body-child tails", "sourceAnchors": sum(len(v) for v in anchors.values())},
               "images": [{"sourcePath": path, "path": "images/" + filename, "sha256": sha256((root / path).read_bytes())} for path, filename in sorted(assets.items())],
               "limitations": ["中文与英文采用独立来源，只按作品关联；未声称逐句或逐场校准。", "部分人物表和文字为原书图片，纯文本搜索无法覆盖这些图片。", "《泰尔亲王配力克里斯》原书署名为“朱豪译”，不自动更正。", "保留用户提供的现代多译者版本；不据此声称全部译文为朱生豪译或公版。"]}
    (output / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def extract_epub(epub: Path, destination: Path) -> None:
    """Expand only regular, safe archive members; never trust ZIP paths."""
    with zipfile.ZipFile(epub) as archive:
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in member.filename:
                raise ValueError(f"Unsafe ZIP member: {member.filename}")
            if ((member.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError(f"Symlink ZIP member: {member.filename}")
            if member.is_dir():
                continue
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--epub", type=Path)
    group.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.epub:
        checksum = sha256(args.epub.read_bytes())
        with tempfile.TemporaryDirectory(prefix="shakespeare-epub-") as temp:
            root = Path(temp)
            extract_epub(args.epub, root)
            summary = import_collection(root, args.output, checksum)
    else:
        summary = import_collection(args.source, args.output)
    print(json.dumps(summary["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
