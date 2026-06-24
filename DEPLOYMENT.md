# 部署到 Streamlit Community Cloud

本项目是 Streamlit App，推荐用 Streamlit Community Cloud 部署。GitHub Pages 只能托管静态网页，不适合直接运行这个 Python/Streamlit 应用。

## 一键网页演示方案

1. 把最新代码推送到 GitHub。
2. 打开 <https://share.streamlit.io/>，用 GitHub 登录。
3. 点击 `Create app`。
4. 选择仓库 `mrs130/resonance-app`、要部署的分支，以及入口文件 `app.py`。
5. Python 版本建议选 `3.11` 或默认版本。
6. `Advanced settings` 里的 secrets 可以先留空；本项目没有 Key 也会自动进入演示模式。
7. 部署成功后复制 `https://...streamlit.app` 链接，替换 README 顶部的在线演示链接。

## 交作业时建议提交

- GitHub 仓库链接：`https://github.com/mrs130/resonance-app`
- 在线演示链接：部署成功后的 `https://...streamlit.app`
- 给老师的提示：打开后直接点击“进入演示模式”，无需注册、无需 API Key。

## 可选：后台页面

`admin_app.py` 是后台管理原型。如果也想给老师看后台，可以在 Streamlit Community Cloud 再创建一个 app，入口文件选择 `admin_app.py`。用户端和后台会是两个不同的网页链接。
