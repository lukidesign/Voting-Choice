# iRun Logo 投票

一个简单的多人投票网页：12 个 Logo 设计方案，每人最多选 3 个，结果实时同步。

## 本地开发

```bash
python3 server.py
# 打开 http://localhost:8765
```

数据保存在 `votes.json`（已 gitignore）。

## 线上部署（Vercel + GitHub）

### 1. 推送到 GitHub

```bash
git init
git add .
git commit -m "init: iRun logo voting site"
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

### 2. 在 Vercel 导入

1. 打开 https://vercel.com/new ，用 GitHub 登录
2. 选中你的仓库 → Import → 直接 Deploy（无需修改任何配置）
3. 部署完成会得到一个网址，例如 `https://irun-vote.vercel.app`

此时网站可以打开，但**投票还存不下来** —— 因为 Serverless 函数没有持久化存储。

### 3. 添加 Vercel KV 存储

1. 在 Vercel 项目页面 → **Storage** → **Create Database** → 选 **Upstash KV**（或叫 Vercel KV）
2. 创建后点 **Connect Project**，连接到当前项目
3. 这一步会自动注入两个环境变量：`KV_REST_API_URL`、`KV_REST_API_TOKEN`
4. 触发一次重新部署（Deployments → 最新一条 → Redeploy），让函数读取到新环境变量

### 4. （可选）保护"清空"按钮

在 Vercel 项目设置 → Environment Variables 增加：

```
IRUN_RESET_TOKEN = 你设的密码
```

（前端目前没传 token，需要的时候让 Claude 帮你加。）

### 后续更新

```bash
git add .
git commit -m "更新 xxx"
git push
```

Vercel 会自动重新部署，几十秒后线上就更新了。

## 文件结构

```
iRun/
├── index.html            # 投票页面（前端）
├── api/
│   └── votes.py          # 线上 Serverless 函数（GET/POST/DELETE /api/votes）
├── server.py             # 本地开发服务，提供同样的 REST 接口
├── RunDo AI/             # 12 张 Logo 设计图
├── vercel.json           # Vercel 配置
└── README.md
```

## API

| 方法     | 路径         | 说明                               |
| -------- | ------------ | ---------------------------------- |
| `GET`    | `/api/votes` | 获取所有投票                       |
| `POST`   | `/api/votes` | 提交投票 `{name, choices, overwrite?}` |
| `DELETE` | `/api/votes` | 清空所有投票（可选 `{token}`）     |
