# 中文戏剧来源导入

此目录来自用户提供的《莎士比亚全集》EPUB，ISBN 978-7-02-010568-7，人民文学出版社。它是多译者版本；本项目不据此主张全部文本为朱生豪译文或公共领域作品。

## 范围与署名

- `part0004` 至 `part0042`，39 部剧作；诗歌不进入网站数据。
- 剧作署名：30 部明确署名朱生豪、8 部明确署名其他译者、1 部原书署名“朱豪译”。后者作为来源待核署名保留，不自动更正为朱生豪。
- 每部作品保留正文、标题、人物表、译者和校者署名、注释、内嵌文字图像及原始顺序。原 EPUB 的封面、版权页和总目录等卷首出版材料不作为新的作品条目。
- 40,723 个原始 body 子元素各处理一次；其文本、嵌套元素和尾部文本均完整保留。共有 1,069 个阅读节、234 次图像引用（216 个独立图像文件）、2,050 个嵌套锚点及 1,008 个注释往返链接。
- 本次导入不进行 OCR。图片形式的人物表或文字仍以原图呈现，不能被普通文本搜索完整覆盖。

## 文件与前端契约

- `catalog.js` 定义 `window.SHAKESPEARE_CHINESE_CATALOG`，可先行加载。`file` 是相对于应用根目录的作品脚本路径。
- `works/partNNNN.js` 按需加载，注册 `window.SHAKESPEARE_CHINESE[id]`，不会重置已加载的其他作品。
- `catalog.json` 是同一目录信息的可检查 JSON 版本。
- `manifest.json` 记录来源 EPUB SHA-256、数量、图像 SHA-256 和验证说明。各作品的 `source.textSha256` 是原始 body 全部文本的精确串联 SHA-256，包含空白和尾部文本。
- `images/` 保存全部被作品引用的本地图像，无需访问外部书站。

作品具有 `id`、`title`、`translator`、`translatorCredit`、`attributionStatus`、`kind`、`sections` 和 `source`。`translatorCredit` 保留原书署名中的空格；`attributionNote` 解释待核署名。

阅读节中的 `label` 保留幕/场上下文。`h3` 自成一个节，即使只有幕标题，也不会被删除；`h4` 切分场次；原书末尾注释从分隔线起独立成节。原书明确标注时提供 `actNumber` / `sceneNumber`，但这些数字并不意味着已完成中英逐场校准。

每个 block 含 `id`、`html`、`text`、`sourceAnchor` 和 `tag`。HTML 采用允许列表清理，去除命名空间和脚本/外部链接。所有源 ID 包括嵌套脚注锚点改写为 `epub-作品ID-原始锚点`。同作品的脚注链接同时有该格式的 `href` 和原始 `data-source-anchor`。阅读器应使用 `source.anchorSections[原始锚点]` 加载目标节，再定位到改写后的元素 ID，以支持跨节注释跳转。

原书 class 前加 `epub-`。图像皆有 `epub-image`，其中 `epub-inline` 为原书字形图，应显示 `height: 1em; width: auto`；普通图像显示自然尺寸并限制 `max-width: 100%`。`epub-center`、`epub-block`、`epub-block1`、`epub-note` 等可用于对齐、舞台提示和注释排版。

`englishId` 只表达同一作品，英文与中文来自独立版本，不承诺逐句或逐场对应。主阅读器的角色台词对应另存于 `data/aligned-collection/`，并不修改这里的底本。

## 重建

只需要 Python 标准库，无网络请求。保留用户原始 EPUB，在仓库根目录运行：

```sh
python3 scripts/import_chinese.py --epub /path/to/source.epub
```

也可使用原书已解压目录，或包含 `original-epub/` 与 `manifest.json` 的先前提取目录：

```sh
python3 scripts/import_chinese.py --source /path/to/extracted
```

原书 EPUB SHA-256：`e0385e88e1428b9accb344d45650a0f52ea1d917cbb12009036b2fb32fd9b747`。直接 EPUB 方式将重新计算此校验和；提取目录方式采用相邻清单中已有的来源校验和，若没有该清单则记为 null。

导入器校验 39 部戏剧标题与预期顺序，从每部作品自身页面提取译者署名，拒绝丢失图像、重复 ID、不安全 ZIP 路径或清理后文本损失。它面向这一 EPUB 的结构，其他版本应先核对作品边界及署名，不能直接假定兼容。

## 验证

```sh
python3 -m unittest discover -s tests -p 'test_chinese_import.py' -v
SHAKESPEARE_CHINESE_SOURCE=/path/to/expanded/epub python3 -m unittest discover -s tests -p 'test_chinese_import.py' -v
```

第一种检查交付内容的数量、HTML 清理、文本校验和、图片字节校验和、锚点有效性、完整性及导入器安全边界。提供原 EPUB 解压目录后，还将独立比较每部作品完整 body 文本、所有图像的顺序和原始译者署名。本次交付已针对原书执行该独立检查。
