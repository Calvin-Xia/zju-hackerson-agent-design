# Phase 1: 项目搭建与基础框架 Spec

## Why
在5小时的黑客松比赛中，快速搭建项目骨架并跑通前后端是关键的第一步。本阶段需要建立完整的项目结构、基础Web界面和文件上传功能，为后续的知识图谱构建、RAG问答等核心功能奠定基础。

## What Changes
- 初始化项目结构，创建必要的配置文件
- 搭建单页应用(SPA)基础框架
- 实现文件上传区域（支持拖拽上传和点击选择）
- 建立前后端通信基础
- 配置开发环境和依赖管理

## Impact
- Affected specs: 无（初始阶段）
- Affected code:
  - 新增: `README.md`（项目说明）
  - 新增: `requirements.txt`（Python依赖）
  - 新增: `package.json`（前端依赖）
  - 新增: `src/`（源代码目录）
  - 新增: `docs/`（文档目录）
  - 新增: `report/`（报告目录）
  - 新增: `.gitignore`（版本控制配置）

## ADDED Requirements

### Requirement: 项目初始化
系统 SHALL 提供完整的项目结构和配置文件，确保其他开发者能够独立部署和运行。

#### Scenario: 项目结构创建
- **WHEN** 开发者克隆仓库后
- **THEN** 能看到清晰的目录结构
- **AND** 包含所有必要的配置文件
- **AND** README 中有详细的安装和运行说明

#### Scenario: 依赖管理
- **WHEN** 开发者执行安装命令
- **THEN** 所有依赖能正确安装
- **AND** 版本号明确锁定
- **AND** 包含 `.env.example` 配置示例

### Requirement: Web界面基础
系统 SHALL 提供单页应用(SPA)基础框架，支持所有功能模块的集成。

#### Scenario: 界面布局
- **WHEN** 用户访问系统
- **THEN** 显示完整的功能界面
- **AND** 左侧为教材管理区
- **AND** 中间为知识图谱可视化区（最大面积）
- **AND** 右侧为功能面板（Tab切换）

#### Scenario: 响应式基础
- **WHEN** 在1920×1080分辨率下显示
- **THEN** 页面布局正常
- **AND** 所有功能模块可操作

### Requirement: 文件上传功能
系统 SHALL 支持教材文件的上传，包括拖拽和点击选择两种方式。

#### Scenario: 拖拽上传
- **WHEN** 用户将文件拖拽到上传区域
- **THEN** 系统识别并上传文件
- **AND** 显示上传进度
- **AND** 上传完成后显示文件信息

#### Scenario: 点击选择
- **WHEN** 用户点击上传区域
- **THEN** 打开文件选择对话框
- **AND** 支持批量选择多个文件
- **AND** 支持的格式：PDF、Markdown、TXT、Word .docx（建议）、Excel（可选）

#### Scenario: 文件列表显示
- **WHEN** 文件上传完成后
- **THEN** 显示文件列表
- **AND** 包含：文件名、格式、大小、解析状态（解析中/已完成/失败）

### Requirement: 前后端通信
系统 SHALL 建立前后端API通信机制，支持数据的传输和处理。

#### Scenario: API接口设计
- **WHEN** 前端需要与后端交互
- **THEN** 使用RESTful API设计
- **AND** 支持JSON数据格式
- **AND** 包含错误处理机制

#### Scenario: 文件上传API
- **WHEN** 前端上传文件
- **THEN** 调用后端上传接口
- **AND** 返回上传结果和文件ID
- **AND** 支持大文件分片上传（如需要）

## MODIFIED Requirements
无（初始阶段）

## REMOVED Requirements
无（初始阶段）

## Technical Constraints
- 前端框架：React / Vue 3 / 原生HTML+JS均可
- 后端框架：推荐FastAPI (Python)
- 必须支持Web浏览器访问
- 页面在1920×1080分辨率下正常显示
- 5小时内完成基础搭建

## Dependencies
- 无外部依赖（初始阶段）

## Success Criteria
1. 项目结构清晰，包含所有必要文件
2. 开发者能按照README成功运行项目
3. 文件上传功能正常工作
4. 前后端通信正常
5. 基础界面布局符合要求
