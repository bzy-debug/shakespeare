# 开发、内容与来源说明

静态 HTML / CSS / JavaScript，无生产构建依赖。打开 `index.html`，或运行 `python3 -m http.server 4173 --bind 127.0.0.1` 后访问 http://127.0.0.1:4173 。正文按剧目懒加载；Google Fonts 为可选外部字体，离线时使用系统字体。

## 收录范围

- 39 部戏剧，不收录独立诗歌集。保留戏剧中的序幕、引子、合唱和韵文台词。
- 中文底本：40,723 个原文块、1,069 个来源分节，234 次图片引用、216 张不同图片；注释链接与出处材料保留在底本入口。
- 英文底本：39,658 块、808 节、880,432 词。37 剧来自 MIT Shakespeare 固定来源快照，《爱德华三世》《两位贵亲戚》来自 Project Gutenberg。
- 主阅读器以英文完整台词块为依据，中英文使用同一场次导航。中文独有附属材料不进入对照正文。见[对照方法与覆盖](ALIGNMENT.md)。

## 版本、署名与对照层级

上传 EPUB 署名为“朱生豪等译”：30 部戏剧明确署名朱生豪，8 部署名其他译者。《泰尔亲王配力克里斯》原书署名“朱豪译”，保留原文并标为待核实，不自动改字。

所有中文显示文字来自上传文件，不补写译文。台词块内部不逐句对齐。英文全文与来源顺序保留；中文版拆段、合段或舞台指示位置不同时，记录精确来源并明确合组。不能可靠确定对应的英文块保持可读并提示待核对。

`source-reader.html` 提供同一 39 部戏剧的完整底本，包括作品内人物表、舞台说明、注释与图片。全书版权页、总前言、总目录、年表没有混入剧目。原 EPUB 保持不变。此前提取的诗歌文件在网站之外保留；仓库内固定英文原始来源压缩包是历史来源快照，包含不由网站使用的诗歌页。

《两位贵亲戚》是莎士比亚与弗莱彻合著，《爱德华三世》归属存在研究讨论；本项目按提供的合集收录，不自行裁定作者归属。

## 来源与重建

- [中文来源说明](../data/chinese-collection/README.md)、[中文清单](../data/chinese-collection/manifest.json)
- [英文来源说明](../data/english-collection/README.md)、[英文清单](../data/english-collection/sources/manifest.json)
- 中文 EPUB SHA-256：`e0385e88e1428b9accb344d45650a0f52ea1d917cbb12009036b2fb32fd9b747`
- MIT 固定提交：`6b82db852c7322dd33e95db347f0ddfc812c6409`，来自官方站点链接的 [TheMITTech/shakespeare](https://github.com/TheMITTech/shakespeare)。
- 输入 EPUB 的文件名不是获取地址；本次未从其中提到的网站下载书籍。

导入文件并不使现代译文、修订、注释或插图成为公版。网站公开发布基于提供方对公开传播授权的确认，保留各来源署名及版本限制。

`legacy-hamlet.html` 保留原项目 72 单元示例及原书签。该例采用维基文库固定修订版 1489093，讨论页注明来自 1978 年朱生豪译、吴兴华校版本，与现有纪念版分别标示。

## 检查

运行 `npm ci && npm test`；npm 仅安装开发测试所需 jsdom。提供原始 EPUB 展开目录时，设置 `SHAKESPEARE_CHINESE_SOURCE=/path/to/expanded/epub` 可逐字核对来源。`npm run rebuild:english` 和 `npm run rebuild:alignment` 均使用已保存输入离线构建。

[验证记录](../preview/QA.md) 分别说明自动检查与真实浏览器的范围。网站没有后端，生产入口为 `index.html`；GitHub Pages 从 `main` 根目录发布。
