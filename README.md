# Shakespeare · 双语阅读原型

静态 HTML / CSS / JavaScript，无构建依赖。双击 `index.html` 即可打开；也可在本目录运行：

```sh
python3 -m http.server 4173 --bind 127.0.0.1
```

访问 http://127.0.0.1:4173 。

## 内容与交互

- 《哈姆雷特》第一幕第一场完整英文：MIT Shakespeare 公版原文，https://shakespeare.mit.edu/hamlet/hamlet.1.1.html 。保留原文诗行，角色采用来源中的 BERNARDO 拼法。
- 72 个双语单元，包括角色台词及独立舞台提示；中文采用朱生豪译本，以维基文库《汉姆莱脱／第一幕》修订版 1489093 为底本，使用该站的简体显示。保留底本措辞及人名（勃那陀、弗兰西斯科、玛昔勒斯等），不改写为现代译法。
- 双栏共享行高，点击同时高亮；窄屏改为每段英文在上、中文在下。
- 搜索中英文与角色名（⌘ / Ctrl K），点击结果跳转；支持书签、本场进度定位、三种阅读模式、字号、行距、三种纸张主题。
- 设置、书签与阅读位置保存在当前浏览器的 localStorage。直接打开文件时，存储支持取决于浏览器；建议通过本地服务器预览。
- 目录仅第一幕第一场可读，其余条目明确标为未收录。
- 正文及脚本均在本地；Google Fonts 为可选网络字体，离线时使用系统衬线字体。

## 文件

- `index.html`：页面结构与对话框
- `styles.css`：桌面与窄屏排版、阅读主题
- `app.js`：阅读交互和本地存储
- `data/english.json`：从来源提取的英文数据
- `data/scene.js`：带稳定 ID 的中英双语数据
- `data/zhu-shenghao-source.json`：朱生豪译文来源、固定版本链接、提取文本与三处舞台提示对齐说明
- `assets/globe-engraving.png`：内置 imagegen 生成的环球剧场装饰插画

插画提示词：Create an elegant antique copperplate architectural engraving of Shakespeare's Globe theatre for the header of a literary reading website. Landscape 3:2 composition, building centered in the lower middle, generous blank space around it. Exterior Elizabethan circular timber-frame theatre, polygonal structure, thatched roof sections and tiny flag, fine crosshatching and delicate thin sepia-gray ink lines, pale warm ivory background #f8f5ed. A few faint shrubs at ground level. Quiet, delicate, airy, authentic book frontispiece illustration. No text, no letters, no labels, no border, no drop shadow, no colors other than pale sepia ink and ivory. Fine detailed architectural line work, broad blank margins softly fading into ivory.

## 中文底本与对齐

译者署名依据：[维基文库《汉姆莱脱》](https://zh.wikisource.org/wiki/漢姆萊脫)。正文采用[第一幕固定修订版 1489093](https://zh.wikisource.org/w/index.php?title=漢姆萊脫/第一幕&oldid=1489093&variant=zh-hans)，获取日期 2026-10-12。

中文台词按人物发言对齐，保留完整措辞和标点。为匹配现有英文底本，独立显示舞台提示，并调整了“鬼上”“鸡啼”和第二次“鬼下”的展示位置；相邻连续台词据此拆段。详细位置记录在 `data/zhu-shenghao-source.json`。全场中文台词串联后与底本的台词串联文本逐字一致，九条舞台提示均保留。
