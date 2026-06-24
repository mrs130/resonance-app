
# 共振 Resonance — 生活记录与朋友匹配 App 原型

## 在线演示

- 用户端 Demo：<https://resonance-app-yrzurbmupro4fvblbm6zpj.streamlit.app/>
- 代码仓库：<https://github.com/mrs130/resonance-app>
- 老师打开后：点击 **进入演示模式**，无需注册、无需 API Key，即可查看完整原型。

部署步骤见 [DEPLOYMENT.md](DEPLOYMENT.md)。本项目是 Streamlit App，不能直接用 GitHub Pages 跑 Python 后端；推荐部署到 Streamlit Community Cloud。

这是一个可直接运行的 Streamlit MVP，用于验证以下闭环：

> 生活记录 / 地点打卡 → AI 或规则提取低敏感度标签 → 动态用户画像 → 可解释朋友匹配

## 已实现

- 9 个预置模拟用户，打开即可演示
- 生活记录、隐私权限、状态与社交意愿提取
- 地点打卡、地图展示、附近 POI
- 可选接入高德 Web 服务 API
- 可选接入 DeepSeek API
- 无 API Key 时自动回退到本地规则和演示 POI
- 基于 TF-IDF + 规则权重的朋友匹配
- 匹配原因、互补点与破冰话题
- SQLite 本地持久化

## 1. 安装与运行

### 两个本地网站

本项目现在有两个 Streamlit 入口：

```powershell
# 用户端网站
python -m streamlit run app.py --server.port 8501

# 后台网站
python -m streamlit run admin_app.py --server.port 8502
```

打开地址：

- 用户端：http://localhost:8501
- 后台端：http://localhost:8502

`localhost` 表示“你自己电脑上的本地网站”，交作业演示时直接打开浏览器访问即可。

### Windows

```powershell
cd resonance-app
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

也可以双击 `run_windows.bat`（前提是已安装 Python）。

### macOS / Linux

```bash
cd resonance-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

## 2. API 配置

编辑 `.env`：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-v4-flash
AMAP_WEB_SERVICE_KEY=
```

两个 Key 都可以留空，App 仍然可以完整演示。

### DeepSeek

配置后，生活记录会调用大模型提取：

- 兴趣/活动标签
- 情绪状态
- 社交意愿
- 中性摘要

密钥只放在本地 `.env`，不要提交到 GitHub。

### 高德地图

申请 **Web 服务 API 类型 Key**。配置后，打卡页会根据经纬度查询真实附近 POI。

注意：此 MVP 没有自动读取浏览器 GPS。为保证三天内稳定演示，当前使用手动经纬度输入。正式版可迁移到 Next.js / Flutter，再调用浏览器或手机定位权限。

## 3. 匹配算法

当前版本不是“让 LLM 直接判断两个人适不适合”，而是：

```text
非私密生活记录
+ 打卡活动
+ 社交目标
→ TF-IDF 语义相似度
→ 标签 / 意图 / 场所 / 城市规则加权
→ 匹配度与解释
```

示例权重：

- 语义相似度：38%
- 兴趣标签：24%
- 社交意图：18%
- 场所类型：10%
- 城市兼容：10%

后续可替换为 Embedding + pgvector / Milvus。

## 4. 数据库

数据库首次运行自动创建：

```text
data/resonance.db
```

表：

- `users`
- `life_logs`
- `checkins`

在“配置与隐私”页面可一键重置演示数据。

## 5. 适合继续修改的方向

优先级从高到低：

1. 改成 Next.js / Flutter 手机界面
2. Supabase 登录与 PostgreSQL
3. 浏览器/手机 GPS 定位
4. Embedding 向量画像
5. 双向“愿意认识”后才允许聊天
6. 共同活动创建与报名
7. 位置模糊化、敏感地点保护、内容审核
8. 推荐效果 A/B 测试

