# TRAE Friends@City PIC-WALL Backend

这是一个基于 FastAPI 开发的图片墙（PicWall）后端服务。项目采用了现代 Python 技术栈，支持用户认证、图片上传与处理（分片上传）、以及基于 SQLite 的本地数据存储。

## 🛠 技术栈

- **框架**: [FastAPI](https://fastapi.tiangolo.com/)
- **ASGI 服务器**: [Uvicorn](https://www.uvicorn.org/)
- **ORM**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/)
- **数据验证与设置**: [Pydantic v2](https://docs.pydantic.dev/) & Pydantic-Settings
- **认证**: JWT (PyJWT), Argon2 (密码哈希)
- **图像处理**: [Pillow](https://python-pillow.org/), imageio-ffmpeg

## 📂 目录结构

```text
.
├── server/
│   ├── api/        # 路由处理器 (Routers)
│   ├── auth/       # 认证与权限校验
│   ├── core/       # 核心配置 (Config, DB, Error, Response)
│   ├── model/      # 数据库模型 (SQLAlchemy Models)
│   ├── schema/     # 数据验证模型 (Pydantic Schemas)
│   ├── service/    # 业务逻辑服务层
│   ├── store/      # 存储接口 (本地文件存储等)
│   ├── task/       # 异步任务或媒体处理任务
│   └── utils/      # 工具函数
├── storage/        # 存储目录
│   ├── avatar/     # 用户头像
│   ├── origin/     # 原始上传文件
│   ├── poster/     # 视频封面/海报
│   ├── temp/       # 分片上传临时目录
│   └── thumb/      # 缩略图
├── main.py         # 项目启动入口
├── picwall.db      # SQLite 数据库文件 (自动生成)
├── requirements.txt# 项目依赖
└── .gitignore      # Git 忽略文件配置
```

## 🚀 快速开始

### 1. 环境准备

请确保你的开发环境中已安装 Python 3.10 或更高版本。建议使用虚拟环境：

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

项目默认配置位于 `server/core/config.py`，你可以在项目根目录创建一个 `.env` 文件来覆盖默认配置：

```env
APP_NAME="TRAE Friends@City PIC-WALL"
HOST="0.0.0.0"
PORT=1309
DATABASE_URL="sqlite:///./picwall.db"
JWT_SECRET="your-super-secret-jwt-key"
CORS_ORIGINS="http://localhost:5273,http://127.0.0.1:5273"
```
*(注意：生产环境中请务必修改 `JWT_SECRET` 为高强度的密钥)*

### 4. 运行服务

直接运行 `main.py` 启动服务：

```bash
python main.py
```

或者使用 uvicorn 启动并开启热重载（推荐开发环境使用）：

```bash
uvicorn server.main:app --host 0.0.0.0 --port 1309 --reload
```

服务启动后，可以通过以下地址访问：
- API 服务地址：`http://localhost:1309`
- 交互式 API 文档 (Swagger UI)：`http://localhost:1309/docs`
- 备用 API 文档 (ReDoc)：`http://localhost:1309/redoc`

## 📦 存储与数据库

- **数据库**: 项目使用 SQLite 数据库，默认会在根目录生成 `picwall.db`。如果需要使用其他关系型数据库（如 PostgreSQL/MySQL），请修改 `.env` 中的 `DATABASE_URL`。
- **文件存储**: 所有上传的文件均存储在项目根目录的 `storage/` 文件夹下。该目录中的具体文件（如图片、视频、分片等）已配置为 `.gitignore` 忽略，确保不会被错误地提交到版本库中。

## 🤝 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 发起 Pull Request

## 📄 开源协议

本项目采用 MIT 协议 - 详情请查看 LICENSE 文件。
