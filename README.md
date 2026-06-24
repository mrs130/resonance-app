# 共振 Resonance

共振是一款面向校园与城市生活场景的朋友匹配 App 原型。它通过生活记录、地点打卡和社交意愿，帮助用户发现更合拍的人，并给出清晰、可解释的推荐理由。

## 在线体验

- 用户端 Demo：<https://resonance-app-yrzurbmupro4fvblbm6zpj.streamlit.app/>
- 代码仓库：<https://github.com/mrs130/resonance-app>

打开网页后，可以直接选择 **进入演示模式** 体验完整流程；也可以使用注册/登录功能体验账号资料流程。

## 产品定位

很多社交产品把“认识新朋友”简化成头像、距离和一句简介，但现实里的连接往往来自更细的生活线索：最近在学什么、常去哪里、想找怎样的伙伴、是否有共同的节奏。

共振希望把这些低敏感度的生活信号整理成可理解的用户画像，再用它来推荐朋友。推荐结果不仅展示匹配度，也展示“为什么推荐”“可以从什么话题开始聊”，让用户更容易迈出第一步。

## 核心体验

- **生活记录**：记录学习、运动、兴趣、项目和日常状态。
- **地点打卡**：保存到访地点、活动内容和可见范围。
- **朋友匹配**：根据记录、标签、地点和社交目标推荐潜在朋友。
- **推荐解释**：展示共同点、互补点和破冰话题。
- **动态发现**：浏览公开记录，发现附近或相似兴趣的人。
- **足迹整理**：按时间线查看自己的地点和活动记录。
- **隐私分级**：支持私密、仅用于匹配、公开三种可见范围。

## 演示内容

当前 Demo 内置了 9 个模拟用户，覆盖学习搭子、项目伙伴、运动伙伴、户外活动、产品设计、开源协作等常见社交场景。即使不配置任何第三方 API，也可以完整体验记录、打卡、匹配、动态和个人资料页面。

如果配置 Supabase，App 会启用注册、登录和用户资料保存。生活记录、地点打卡和匹配数据目前仍保留为原型演示数据。

## 本地运行

### 用户端

```powershell
python -m streamlit run app.py --server.port 8501
```

打开：

```text
http://localhost:8501
```

### 后台端

```powershell
python -m streamlit run admin_app.py --server.port 8502
```

打开：

```text
http://localhost:8502
```

## 安装步骤

### Windows

```powershell
cd resonance-app
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

也可以双击 `run_windows.bat` 启动用户端。

### macOS / Linux

```bash
cd resonance-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

## 可选配置

项目可以在无密钥状态下运行。需要接入真实服务时，在 `.env` 或 Streamlit Secrets 中配置：

```env
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-v4-flash
AMAP_WEB_SERVICE_KEY=
```

- `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY`：启用注册、登录和用户资料保存。
- `DEEPSEEK_API_KEY`：用于生活记录的标签、情绪、社交意愿和摘要提取。
- `AMAP_WEB_SERVICE_KEY`：用于根据经纬度查询真实附近 POI。

密钥不要提交到 GitHub。本地开发使用 `.env`，线上部署使用 Streamlit Secrets。

## 技术实现

- 前端与应用服务：Streamlit
- 数据处理：Pandas
- 匹配算法：TF-IDF 相似度 + 标签、意图、地点和城市规则加权
- 本地存储：SQLite
- 账号与资料：Supabase Auth / profiles
- 地图与地点：Folium、streamlit-folium、高德 Web 服务 API
- 可选文本分析：DeepSeek API

匹配逻辑不会让大模型直接判断两个人是否“适合”。当前版本会先把非私密记录和打卡活动转换成低敏感度标签，再结合社交目标、地点类型和城市信息计算匹配度，并展示可解释原因。

## 原型边界

这是一个课程项目和产品验证原型，不是可直接上线的社交平台。正式上线前仍需要补充真实身份安全、内容审核、举报处理、未成年人保护、隐私合规、位置模糊化和生产级数据治理。

## 部署

部署说明见 [DEPLOYMENT.md](DEPLOYMENT.md)。本项目是 Streamlit 应用，推荐使用 Streamlit Community Cloud 部署；GitHub Pages 只能托管静态网页，不适合直接运行本项目。
