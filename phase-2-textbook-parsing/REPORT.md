# Phase 2 代码审查报告

**审查日期**: 2026-05-11  
**审查范围**: 全仓库（后端Python/FastAPI + 前端React/TypeScript）  
**审查结论**: REQUEST_CHANGES

---

## 问题统计

| 等级 | 数量 | 说明 |
|------|------|------|
| P0 - Critical | 0 | 无 |
| P1 - High | 6 | 逻辑错误、显著架构问题 |
| P2 - Medium | 9 | 代码异味、可维护性 |
| P3 - Low | 5 | 风格、命名、小建议 |

---

## P1 - High

### 1. `src/shared/config.py:14` + `frontend/vite.config.ts:7` — CORS端口与前端端口不匹配

CORS配置允许 `localhost:5173`，但vite配置已改为端口 `5174`。前端所有API请求将被CORS策略拦截。

```python
# config.py 当前
CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

# 应改为
CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:5174"]
```

### 2. `src/api/routes/parse.py:16` — 内存状态存储，重启丢失

`_parse_status: dict[str, dict] = {}` 使用进程内存存储解析状态。服务器重启后所有状态丢失，前端轮询将永远等待。

建议：持久化到文件或数据库，或在启动时从 `_parsed.json` 文件重建状态。

### 3. `src/api/routes/kg.py:19` — 同样的内存状态问题

`_extraction_status: Dict[str, ExtractionTaskStatus] = {}` 与parse.py相同的问题。

### 4. `src/kg/extractor.py:69-70` — 空except块吞掉错误

```python
try:
    start = response.find('{')
    end = response.rfind('}') + 1
    if start >= 0 and end > start:
        return json.loads(response[start:end])
except:   # ← 捕获所有异常但不做任何处理
    pass
```

应至少记录日志，并改为 `except Exception as e`。

### 5. `src/api/routes/upload.py:62` + `src/api/routes/kg.py:103` — asyncio.create_task 无错误处理

```python
asyncio.create_task(_parse_file_async(file_id, file_path))
```

fire-and-forget模式。如果task抛出未捕获异常，不会有任何日志。应添加task完成回调。

### 6. `frontend/src/components/KnowledgeGraphPanel.tsx:94-112` — 轮询interval组件卸载时不清理

`setInterval`在`handleExtract`中创建，但如果组件在轮询期间卸载，interval不会被清除，导致内存泄漏和对已卸载组件的setState调用。

---

## P2 - Medium

### 7. `src/parsers/pdf_parser.py:15-19` + `txt_parser.py:13-17` + `docx_parser.py:15-19` — 重复的CHAPTER_PATTERNS定义

三个文件定义了完全相同的正则模式。应提取到共享模块。

### 8. `src/parsers/factory.py:34` — 使用已弃用的API

```python
loop = asyncio.get_event_loop()  # Python 3.10+ 已弃用
```

应改为 `asyncio.get_running_loop()` 或 `asyncio.to_thread()`。

### 9. `src/llm/client.py:11-28` — 每次调用创建新client实例

`get_llm_client()` 每次调用都创建新的 `AsyncOpenAI` 实例，浪费连接资源。应缓存client实例。

### 10. `src/api/routes/kg.py:167-185` — list_knowledge_graphs 加载所有图谱到内存

每次调用都遍历所有文件并反序列化完整JSON。当图谱数量增长时会造成性能问题。

### 11. `src/api/routes/upload.py:50` — 文件路径构造可能存在路径遍历风险

```python
file_path = Path("data/textbooks") / f"{file_id}_{file.filename}"
```

如果`file.filename`包含`../`，可能写入预期目录之外。应对filename做sanitize。

### 12. `src/shared/config.py:12` — DEBUG默认为True

生产环境部署时如果忘记设置`DEBUG=False`，会暴露详细错误信息。

### 13. `frontend/src/components/KnowledgeGraphPanel.tsx:61-69` — fetchGraph/useEffect依赖问题

`fetchGraph`在useEffect中被调用但未作为依赖，且未用useCallback包裹。可能导致闭包陈旧问题。

### 14. `frontend/src/components/FileList.tsx:79` — 5秒轮询过于激进

对所有已上传文件每5秒轮询一次。文件多时会产生大量请求。建议：仅在有parsing状态的文件时轮询。

### 15. `src/kg/extractor.py:18` — 使用MD5生成节点ID

MD5已不推荐使用，且截取前8字符（32bit）碰撞概率较高。建议使用SHA-256。

---

## P3 - Low

### 16. `src/models/parse_status.py:23` — datetime.now()无时区信息

应使用 `datetime.now(tz=timezone.utc)` 以避免时区歧义。

### 17. `src/shared/config.py:29` — ALLOWED_EXTENSIONS包含xlsx但无xlsx解析器

配置允许上传`.xlsx`文件，但没有对应的xlsx解析器。上传xlsx文件会触发解析失败。

### 18. `src/parsers/markdown_parser.py:92` — 传入空Path("")给_extract_title_from_filename

```python
title=self._extract_title_from_filename(Path("")),  # 空Path，会返回空字符串
```

### 19. 前端placeholder组件 — DialogueTab/RAGTab/ReportTab/IntegrationTab

所有按钮都是`disabled`状态，是预期的placeholder实现。但缺少TODO注释标明后续实现计划。

### 20. `src/api/routes/files.py:35-41` — 文件ID解析逻辑脆弱

通过`split("_", 1)`从文件名提取file_id。是隐式约定，没有强制保证。

---

## API Contract 审查

| 前端调用 | 后端路由 | 匹配状态 |
|----------|----------|----------|
| `GET /api/files/` | `GET /api/files/` | ✅ |
| `POST /api/upload` | `POST /api/upload/` | ⚠️ 尾部斜杠差异 |
| `GET /api/kg/graph/${fileId}` | `GET /api/kg/graph/{file_id}` | ✅ |
| `POST /api/kg/extract` | `POST /api/kg/extract` | ✅ |
| `GET /api/kg/status/${selectedFileId}` | `GET /api/kg/status/{file_id}` | ✅ |

---

## 架构建议

1. **状态持久化**：parse和kg的内存状态应迁移到Redis或SQLite，或至少在启动时从文件系统重建
2. **共享常量**：CHAPTER_PATTERNS、ALLOWED_EXTENSIONS等应集中定义
3. **错误边界**：前端应添加React Error Boundary组件
4. **日志标准化**：统一日志格式，添加request_id便于追踪
