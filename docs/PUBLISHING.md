# GitHub Pages 发布说明

本页是配置参考，不表示网站已发布。

项目是静态站点。经公开内容权限确认后，GitHub Pages 可选 `main` 分支的 `/(root)` 为发布源；入口是仓库根目录的 `index.html`。根目录的 `.nojekyll` 用于关闭 Jekyll 处理，原样提供静态文件。

项目页部署在 `/shakespeare/` 子路径下。页面脚本、样式、图片、按需加载的中英文作品与来源链接都使用相对路径；DOM 测试包含子路径加载场景。发布后仍需在真实地址检查首页、书架、正文、图片与脚注。

仓库改为公开会公开整个仓库及历史，不能只把首页视作公开范围。应先确认译文、修订、注释及插图等内容的再发布权限。Pages 设置与可见性变更需单独获得明确授权。

官方参考：

- [配置 GitHub Pages 发布源](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
- [创建 GitHub Pages 网站](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site)

文档核对日期：2026-10-12。
