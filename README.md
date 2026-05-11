# 学科知识整合智能体

> AI全栈极速黑客松赛题 - 浙江大学未来学习中心·AI生态 2026

## 项目简介

学科知识整合智能体是一个基于AI的Web应用，旨在帮助教师将多本教材整合为精华版本。系统通过知识图谱可视化、语义对齐、RAG问答等技术，实现跨教材的知识点去重、整合与精准问答。

### 核心功能

1. **多格式教材解析**：支持PDF、Markdown、TXT等格式的教材文件上传与解析
2. **知识图谱构建**：自动提取知识点并构建可视化知识图谱
3. **跨教材整合**：语义对齐算法识别重复知识点，压缩比不超过30%
4. **RAG精准问答**：基于教材内容的问答，每个回答附带原文引用
5. **多轮对话优化**：教师可通过自然语言对话修改整合方案
6. **整合报告生成**：自动生成包含统计数据和案例分析的整合报告

## 环境依赖

- **Python**: >= 3.10
- **Node.js**: >= 18.0
- **npm**: >= 9.0

## 快速开始

### 1. 克隆仓库

```bash
git clone <repository-url>
cd <project-directory>
```

### 2. 安装后端依赖

```bash
pip install -r requirements.txt
```

### 3. 安装前端依赖

```bash
npm install
```

### 4. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API 密钥（DASHSCOPE_API_KEY 等）
```

### 5. 启动开发服务器

**方式一：一键启动（推荐）**
```bash
# Windows
start-dev.bat

# 或手动启动
```

**方式二：分别启动**

启动后端 (FastAPI):
```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8001
```

启动前端 (React + Vite):
```bash
cd frontend
npm run dev
```

访问 http://localhost:5174 即可使用系统。
API文档：http://localhost:8001/docs

## 项目结构

```
.
├── README.md                       # 项目说明
├── requirements.txt                # Python 依赖
├── package.json                    # 前端依赖
├── .env.example                    # 环境变量示例
├── .gitignore                      # Git 忽略配置
│
├── src/                            # 后端源代码
│   ├── main.py                     # 应用入口
│   ├── api/                        # API 路由
│   ├── parsers/                    # 教材解析器（PDF/MD/TXT/DOCX）
│   ├── kg/                         # 知识图谱模块
│   ├── integration/                # 跨教材整合模块
│   ├── rag/                        # RAG 问答模块
│   ├── dialogue/                   # 多轮对话模块
│   ├── llm/                        # LLM 调用模块
│   ├── embedding/                  # 向量嵌入模块
│   ├── vectorstore/                # 向量存储模块
│   ├── models/                     # 数据模型
│   └── shared/                     # 共享工具
│
├── frontend/                       # 前端源代码
│   ├── src/
│   │   ├── components/             # UI 组件
│   │   ├── pages/                  # 页面组件
│   │   └── api/                    # API 调用
│   └── public/                     # 静态资源
│
├── docs/                           # 文档
│   ├── Agent架构说明.md             # Agent 架构设计
│   ├── 需求分析.md                  # 需求分析
│   ├── 系统设计.md                  # 系统设计
│   └── 接口文档.md                  # API 文档
│
├── report/                         # 报告
│   └── 整合报告.md                  # 整合报告
│
├── data/textbooks/                 # 教材数据（不提交到 Git）
├── tests/                          # 测试文件
│
└── phase-*/                        # 开发阶段计划文件
    ├── spec.md                     # 规格说明
    ├── tasks.md                    # 任务列表
    └── checklist.md                # 检查清单
```

## API 接口

### 教材管理
- `POST /api/upload` - 上传教材文件
- `GET /api/files` - 获取文件列表
- `GET /api/parse/status/{file_id}` - 查询解析状态

### 知识图谱
- `POST /api/kg/extract` - 提取知识点
- `GET /api/kg/{textbook_id}` - 获取知识图谱
- `GET /api/kg/extract/status/{task_id}` - 查询提取状态

### 跨教材整合
- `POST /api/integration/merge` - 执行整合
- `GET /api/integration/status/{task_id}` - 查询整合状态
- `GET /api/integration/decisions` - 查询整合决策

### RAG 问答
- `POST /api/rag/index` - 建立向量索引
- `POST /api/rag/query` - 提问
- `GET /api/rag/status` - 查询索引状态

### 多轮对话
- `POST /api/dialogue/chat` - 发送消息
- `POST /api/dialogue/feedback` - 提交反馈
- `GET /api/dialogue/history` - 获取对话历史

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI (Python) |
| 前端框架 | React 19 + Vite |
| 知识图谱可视化 | D3.js / Cytoscape.js / ECharts |
| 大模型调用 | 通义千问 API / DeepSeek API / OpenAI API |
| 向量嵌入 | sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2) |
| 向量检索 | FAISS / ChromaDB |
| 文件解析 | pdfplumber / python-docx / openpyxl |
| UI 组件库 | Ant Design |
| 部署 | 魔搭创空间 / Vercel + Railway |

## 配置说明

所有配置通过 `.env` 文件管理，参考 `.env.example`：

- `DASHSCOPE_API_KEY`: 通义千问 API 密钥
- `LLM_PROVIDER`: 默认 LLM 提供商
- `EMBEDDING_MODEL`: 嵌入模型选择
- `VECTOR_DB`: 向量数据库选择
- `CHUNK_SIZE`: RAG 分块大小

## 使用说明

1. **上传教材**: 在左侧面板拖拽或点击上传教材文件
2. **构建图谱**: 系统自动解析教材并构建知识图谱，显示在中间区域
3. **跨教材整合**: 在右侧面板切换到"整合操作"Tab，选择教材执行整合
4. **RAG 问答**: 切换到"RAG问答"Tab，输入问题获取带引用的回答
5. **对话优化**: 切换到"对话"Tab，通过自然语言修改整合方案
6. **查看报告**: 切换到"报告"Tab，查看整合统计和报告

## License

MIT
