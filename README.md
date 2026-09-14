# 学科知识整合智能体

> AI全栈极速黑客松赛题 - 浙江大学未来学习中心·AI生态 2026

## 项目简介

学科知识整合智能体是一个基于 AI 的 Web 应用，帮助教师把多本教材整合为精华版本。
系统通过知识图谱可视化、语义对齐、RAG 问答等技术，实现跨教材的知识点去重、
整合与精准问答。

### 核心功能

1. **多格式教材解析**：支持 PDF、Markdown、TXT、Word（.docx）、Excel（.xlsx）
2. **知识图谱构建**：自动提取知识点与知识点之间的关系，并可视化
3. **跨教材整合**：语义对齐识别重复知识点，**压缩比 ≤ 30%**（赛题硬性要求），三种整合决策可解释
4. **RAG 精准问答**：基于教材内容作答，每个回答附带原文引用与来源定位
5. **多轮对话优化**：教师可通过自然语言对话理解/调整整合方案
6. **整合报告**：汇总压缩比、决策明细、语义对齐明细

## 环境依赖

- **Python**: >= 3.10
- **Node.js**: >= 18.0
- **npm**: >= 9.0

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt

cd frontend && npm install && cd ..
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少填写当前 LLM_PROVIDER 对应的 API Key
# 例如 LLM_PROVIDER=deepseek 时填写 DEEPSEEK_API_KEY
```

### 3. 启动

**一键启动（Windows）**

```bash
start-dev.bat
```

**分别启动**

```bash
# 后端
uvicorn src.main:app --reload --host 0.0.0.0 --port 8001

# 前端（另开终端）
cd frontend && npm run dev
```

访问 http://localhost:5174 （API 文档：http://localhost:8001/docs ）

**生产模式**：`cd frontend && npm run build` 后，后端会自动托管 `frontend/dist`，
直接访问 http://localhost:8001 即可。

**Docker**：`docker compose up --build`

## 使用说明

1. **上传教材**：左侧面板拖拽或点击上传，上传后自动开始解析
2. **构建图谱**：中间面板选择教材 → 「提取知识图谱」
3. **跨教材整合**：右侧「整合操作」勾选 ≥ 2 本教材 → 开始整合，完成后显示压缩比与决策统计
4. **查看整合结果**：中间面板切换到「跨教材整合结果」查看整合后的图谱
5. **RAG 问答**：右侧「RAG问答」先建立索引，再提问，回答附带引用来源
6. **对话 / 报告**：「对话」面板可与助手讨论整合方案；「报告」面板查看统计与决策明细

## 实现要点

### 语义对齐（`src/integration/alignment.py`）

- **向量化候选召回**：分块计算余弦相似度矩阵，避免上千知识点时的双层循环
- **一对一贪心匹配**：每个知识点最多与另一本教材的一个知识点配对，杜绝
  「一个节点被多条决策同时删除」导致的连锁误删与重复计数
- **分层判定**：同名知识点直接等价；高相似度直接判定；灰区可选 LLM 批量复核
  （一次 Prompt 处理多对，默认关闭以保持秒级完成）
- **全局对齐**：多本教材在全局层面做一次匹配，避免同一知识点在一组教材里保留、
  又在另一组里被删除

### 整合决策（`src/integration/decision.py`）

| 动作 | 语义 |
|------|------|
| `merge` | 同一概念且双方各有独有信息 → 描述取并集 |
| `keep` | 同一概念但相似度中等 → 保留更完整的一侧 |
| `remove` | 描述已被完全覆盖、无独有信息 → 删除 |

决策默认走**确定性规则**（不调用 LLM），因此整合是秒级且可复现的；
每一步都给出可读的中文理由。被删除节点上的关系会同步清理，不留悬空边。

### 压缩比控制（`src/integration/compression.py`）

需求定义：`压缩比 = 整合后字数 / 原始总字数 ≤ 30%`。采用三级递进策略：

1. **合并**（决策阶段）—— 去重同一概念，描述取并集；
2. **摘要** —— 按知识点重要度（频次、图度数、信息量）分配字数预算，
   做**抽取式**摘要，保留全部知识点结构，而不是砍掉大半内容；
3. **筛选** —— 若仍超预算，按重要度从低到高丢弃知识点，并始终至少保留一个节点，
   避免产出空图谱。

跨教材共享的核心概念（整合后频次 ≥ 2）受到保护，优先保留完整描述。

### RAG 问答（`src/rag/qa.py`）

- **相关性过滤**：低于阈值（按嵌入后端自适应）的片段直接丢弃；全部不相关时
  不调用 LLM，直接回答「当前知识库中未找到相关信息」，避免无关上下文诱导幻觉
- **近重复去重 + 来源多样性**：多本教材描述同一内容时只保留最相关的一段并记录其它来源；
  限制单本教材的最大片段数，避免上下文被一本书占满
- **上下文预算**：按剩余字数预算逐段裁剪，保证总长度不超上限
- **引用保证**：要求模型用 `[n]` 标注来源；完全漏写时自动补齐来源列表

### 嵌入后端

`EMBEDDING_BACKEND=auto`（默认）优先加载 `sentence-transformers` 语义模型；
**模型不可用（离线/未下载）时自动降级为无状态的 hashing 后端**（字符 1–3 gram
哈希投影，维度 384）。降级方案无需 fit，索引期与查询期向量严格一致，
服务重启不会漂移，但**检索质量偏字面匹配**。

- 健康检查 `GET /api/health` 会返回当前实际使用的后端；
- 使用语义模型请确保模型已下载到本地（`EMBEDDING_OFFLINE=true` 时不会联网重试）；
- 相似度阈值会随后端自动调整（语义模型 0.35 / hashing 0.18）；
- 切换后端后索引指纹（`embedding_signature`）不匹配，旧索引会被拒绝加载，
  需要重新建立索引 —— 这是为了避免「维度相同但语义不同」的脏数据被误用。

## 项目结构

```
.
├── README.md
├── requirements.txt
├── .env.example
├── Dockerfile / docker-compose.yml
├── src/                            # 后端
│   ├── main.py                     # 应用入口（CORS、健康检查、托管前端产物）
│   ├── api/
│   │   ├── router.py               # 路由注册
│   │   └── routes/                 # 各接口（薄层：调度 + 状态上报）
│   ├── parsers/                    # PDF/MD/TXT/DOCX/XLSX 解析器
│   ├── kg/                         # 知识图谱（模型、抽取、存储）
│   ├── integration/                # 跨教材整合（对齐/决策/压缩/流水线）
│   ├── rag/                        # 分块与问答
│   ├── embedding/                  # 嵌入服务（含 hashing 降级）
│   ├── vectorstore/                # 向量存储（FAISS，缺失时 numpy 精确检索）
│   ├── dialogue/                   # 多轮对话上下文
│   ├── llm/                        # LLM 调用与 Prompt
│   ├── models/                     # 数据模型
│   └── shared/                     # 配置、状态存储、文本工具
├── frontend/                       # React 19 + Vite + Ant Design
│   └── src/
│       ├── api/client.ts           # 统一 API 客户端与类型定义
│       └── components/
│           ├── KnowledgeGraphPanel.tsx
│           ├── FileList.tsx / FileUpload.tsx
│           └── tabs/               # 整合 / RAG / 对话 / 报告
├── docs/                           # 架构、需求、系统设计、接口文档
├── report/整合报告.md
├── tests/                          # pytest（90 个用例）
└── data/                           # 运行时数据（不提交）
    ├── textbooks/                  # 上传的原文件与解析结果
    ├── knowledge_graphs/           # 知识图谱
    ├── vectorstore/                # 向量索引
    ├── embedding_cache/            # 嵌入缓存
    ├── tasks/                      # 异步任务状态
    └── dialogue/                   # 对话历史
```

## API 接口

完整说明见 [docs/接口文档.md](docs/接口文档.md)。概要：

| 分组 | 接口 |
|------|------|
| 教材 | `POST /api/upload/`、`GET /api/files/`、`DELETE /api/files/{file_id}` |
| 解析 | `POST /api/parse/{file_id}/parse`、`GET /api/parse/status/{file_id}` |
| 知识图谱 | `POST /api/kg/extract`、`GET /api/kg/graph/{file_id}`、`GET /api/kg/graphs`、`GET /api/kg/status/{file_id}`、`PUT /api/kg/graph/{file_id}/node/{node_id}`、`PUT /api/kg/graph/{file_id}/relation`、`DELETE /api/kg/graph/{file_id}` |
| 跨教材整合 | `POST /api/integration/merge`、`GET /api/integration/status/{task_id}`、`GET /api/integration/statistics/{task_id}`、`GET /api/integration/decisions/{task_id}`、`GET /api/integration/alignment/{task_id}`、`GET /api/integration/graph/{task_id}`、`GET /api/integration/tasks` |
| RAG | `POST /api/rag/index`、`GET /api/rag/index/status/{task_id}`、`GET /api/rag/status`、`POST /api/rag/query`、`DELETE /api/rag/index` |
| 对话 | `POST /api/dialogue/chat`、`POST /api/dialogue/feedback`、`GET /api/dialogue/history/{conversation_id}`、`DELETE /api/dialogue/history/{conversation_id}` |
| 系统 | `GET /api/health` |

耗时操作（解析、抽取、整合、建索引）均为异步任务：接口返回 `task_id`，
再轮询对应 `status` 接口获取 `progress`（0–100）。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn（Python 3.10+） |
| 数据处理 | Pydantic v2 |
| 前端 | React 19 + TypeScript + Vite |
| 可视化 | ECharts（力导向图） |
| UI 组件 | Ant Design 5 |
| 大模型 | DeepSeek / 通义千问（DashScope）/ OpenAI 兼容接口 |
| 向量嵌入 | sentence-transformers（不可用时 hashing 降级） |
| 向量检索 | FAISS（未安装时自动降级为 numpy 精确检索） |
| 文件解析 | pdfplumber / python-docx / openpyxl（Markdown 与 TXT 自行解析） |
| 部署 | Docker / docker-compose |

> 说明：`VECTOR_DB`/ChromaDB 仅作为可扩展项保留，当前实现使用 FAISS/numpy。

## 测试

```bash
python -m pytest tests/ -q            # 全部用例
python -m pytest tests/test_integration.py -v
```

| 测试文件 | 用例数 | 覆盖内容 |
|----------|--------|----------|
| `test_graph_store.py` | 14 | 图谱存储 CRUD、更新、删除、损坏处理 |
| `test_integration.py` | 11 | 语义对齐、决策生成、压缩比 |
| `test_rag.py` | 11 | 分块、向量存储、问答 |
| `test_dialogue.py` | 14 | 上下文管理、API 端点 |
| `test_optimization.py` | 40 | 分块偏移、文本工具、RAG 引用/无答案判定、一对一匹配、决策语义、压缩达标、整合流水线端到端、存储原子性、配置解析 |

前端类型检查与构建：

```bash
cd frontend && npx tsc --noEmit && npm run build
```

## 文档

- [Agent 架构说明](docs/Agent架构说明.md)
- [需求分析](docs/需求分析.md)
- [系统设计](docs/系统设计.md)
- [接口文档](docs/接口文档.md)
- [整合报告](report/整合报告.md)

## License

MIT
