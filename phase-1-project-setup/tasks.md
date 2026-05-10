# Phase 1: 项目搭建与基础框架 Tasks

## Task 1: 项目结构初始化
**Priority**: P0 (必须实现)
**Estimated Time**: 30分钟

### SubTask 1.1: 创建基础目录结构
- [ ] 创建 `src/` 目录（源代码）
- [ ] 创建 `docs/` 目录（文档）
- [ ] 创建 `report/` 目录（报告）
- [ ] 创建 `data/textbooks/` 目录（教材数据，不提交到Git）

### SubTask 1.2: 创建配置文件
- [ ] 创建 `.gitignore` 文件，排除教材PDF和敏感文件
- [ ] 创建 `.env.example` 文件，列出所有需要的环境变量
- [ ] 创建 `requirements.txt` 文件，列出Python依赖
- [ ] 创建 `package.json` 文件，列出前端依赖

### SubTask 1.3: 创建README.md
- [ ] 项目简介（学科知识整合智能体）
- [ ] 环境依赖（Python版本、Node版本）
- [ ] 安装步骤（pip install / npm install）
- [ ] 配置说明（.env文件）
- [ ] 启动命令
- [ ] 使用说明
- [ ] 项目结构说明

**Acceptance Criteria**:
- 开发者克隆仓库后能按照README成功运行项目
- 所有配置文件格式正确
- .gitignore正确排除敏感文件

## Task 2: 前端框架搭建
**Priority**: P0 (必须实现)
**Estimated Time**: 45分钟

### SubTask 2.1: 选择并初始化前端框架
- [ ] 选择前端框架（React/Vue 3/原生HTML+JS）
- [ ] 初始化项目结构
- [ ] 配置构建工具（如Vite/Webpack）

### SubTask 2.2: 创建基础布局组件
- [ ] 创建主布局组件（左中右三栏）
- [ ] 左侧：教材管理区（宽度20-25%）
- [ ] 中间：知识图谱可视化区（最大面积）
- [ ] 右侧：功能面板（宽度25-30%）

### SubTask 2.3: 实现Tab切换功能
- [ ] 右侧面板实现Tab切换
- [ ] Tab选项：整合操作 / RAG问答 / 对话 / 报告
- [ ] Tab内容区域正确显示

### SubTask 2.4: 响应式设计基础
- [ ] 确保1920×1080分辨率下正常显示
- [ ] 基本的CSS样式配置
- [ ] 字体和颜色方案定义

**Acceptance Criteria**:
- 打开浏览器能看到完整的功能界面
- 所有功能模块可操作
- Tab切换正常工作
- 1920×1080分辨率下布局正常

## Task 3: 文件上传功能实现
**Priority**: P0 (必须实现)
**Estimated Time**: 60分钟

### SubTask 3.1: 创建文件上传组件
- [ ] 设计上传区域UI（拖拽区域 + 点击按钮）
- [ ] 实现拖拽上传功能
- [ ] 实现点击选择文件功能
- [ ] 支持批量上传多个文件

### SubTask 3.2: 文件格式验证
- [ ] 前端验证文件格式（PDF、MD、TXT必须，DOCX/Excel可选）
- [ ] 显示文件大小信息
- [ ] 格式不支持时显示错误提示

### SubTask 3.3: 文件列表组件
- [ ] 显示已上传文件列表
- [ ] 每个文件显示：文件名、格式、大小、解析状态
- [ ] 解析状态：解析中/已完成/失败
- [ ] 支持删除已上传文件

### SubTask 3.4: 文件上传API
- [ ] 后端创建文件上传接口 `POST /api/upload`
- [ ] 接收文件并保存到 `data/textbooks/` 目录
- [ ] 返回文件ID和上传结果
- [ ] 错误处理（文件过大、格式不支持等）

**Acceptance Criteria**:
- 拖拽文件到上传区域能正常上传
- 点击上传区域能打开文件选择对话框
- 文件列表正确显示所有信息
- 上传失败时有明确错误提示

## Task 4: 后端框架搭建
**Priority**: P0 (必须实现)
**Estimated Time**: 45分钟

### SubTask 4.1: 初始化后端项目
- [ ] 创建FastAPI项目结构
- [ ] 配置依赖管理（requirements.txt）
- [ ] 创建主应用入口文件

### SubTask 4.2: 基础API路由
- [ ] 创建健康检查接口 `GET /api/health`
- [ ] 创建文件上传接口 `POST /api/upload`
- [ ] 创建文件列表接口 `GET /api/files`
- [ ] 配置CORS（跨域资源共享）

### SubTask 4.3: 错误处理中间件
- [ ] 全局异常处理
- [ ] 统一错误响应格式
- [ ] 日志记录配置

### SubTask 4.4: 静态文件服务
- [ ] 配置静态文件服务（前端资源）
- [ ] 配置上传文件访问路径
- [ ] 生产环境优化

**Acceptance Criteria**:
- 后端服务能正常启动
- API接口能正常响应
- 前端能成功调用后端接口
- 错误处理机制正常工作

## Task 5: 前后端联调
**Priority**: P0 (必须实现)
**Estimated Time**: 30分钟

### SubTask 5.1: API通信测试
- [ ] 测试文件上传API
- [ ] 测试文件列表API
- [ ] 测试健康检查API

### SubTask 5.2: 错误处理测试
- [ ] 测试网络错误处理
- [ ] 测试文件格式错误处理
- [ ] 测试服务器错误处理

### SubTask 5.3: 性能优化
- [ ] 文件上传进度显示
- [ ] 加载状态提示
- [ ] 基本的用户体验优化

**Acceptance Criteria**:
- 前端上传文件能成功保存到后端
- 文件列表能正确显示
- 错误情况有友好提示
- 用户体验流畅

## Task 6: 开发环境配置
**Priority**: P1 (建议实现)
**Estimated Time**: 20分钟

### SubTask 6.1: 开发脚本配置
- [ ] 配置前端开发服务器（热重载）
- [ ] 配置后端开发服务器（自动重启）
- [ ] 创建启动脚本（同时启动前后端）

### SubTask 6.2: 环境变量管理
- [ ] 创建 `.env.example` 文件
- [ ] 配置环境变量加载逻辑
- [ ] 敏感信息不提交到版本控制

### SubTask 6.3: 代码规范配置
- [ ] 配置ESLint/Prettier（如使用JavaScript）
- [ ] 配置Python代码格式化（如black/isort）
- [ ] 创建 `.editorconfig` 文件

**Acceptance Criteria**:
- 开发者能快速启动开发环境
- 代码格式化工具正常工作
- 环境变量管理规范

# Task Dependencies

- [Task 1] 必须在 [Task 2, 3, 4] 之前完成，项目结构是所有工作的基础
- [Task 2] 和 [Task 4] 可以并行进行，前后端独立开发
- [Task 3] 依赖 [Task 2] 和 [Task 4]，需要前后端都完成后才能联调
- [Task 5] 必须在 [Task 2, 3, 4] 完成后进行
- [Task 6] 可以与 [Task 1-5] 并行进行

# Priority Order

1. **P0 - 高优先级**: Task 1, Task 2, Task 3, Task 4, Task 5（核心功能）
2. **P1 - 中优先级**: Task 6（开发环境配置）

# Estimated Total Time: 4小时30分钟

# Notes
- 前30分钟必须完成项目骨架搭建
- 前后端可以并行开发，节省时间
- 优先实现核心功能，优化和配置可以后续补充
- 保持代码简洁，避免过度设计
