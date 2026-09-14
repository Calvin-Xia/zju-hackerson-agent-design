/**
 * 后端 API 客户端。
 *
 * 所有请求经 Vite 代理转发到 FastAPI（/api -> http://localhost:8001）。
 * 统一处理非 2xx 响应，把后端的 ``detail`` 字段作为错误信息抛出，
 * 便于 UI 直接展示「为什么失败」而不是笼统的「请求失败」。
 */

const API_BASE = '/api';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let detail = `请求失败（HTTP ${response.status}）`;
    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') {
        detail = body.detail;
      } else if (Array.isArray(body?.detail)) {
        detail = body.detail.map((item: { msg?: string }) => item.msg ?? '').join('；');
      }
    } catch {
      // 响应不是 JSON 时保留默认文案
    }
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function jsonInit(method: string, payload?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  };
}

// ----------------------------------------------------------------------
// 类型定义（与后端 Pydantic 模型对齐）
// ----------------------------------------------------------------------
export interface FileItem {
  file_id: string;
  filename: string;
  size: number;
  status: string;
  parse_status: string;
  chapter_count: number;
  total_chars: number;
  error_message: string | null;
  has_graph: boolean;
  textbook_title: string;
}

export interface TaskStatus {
  task_id: string;
  status: string;
  progress: number;
  message?: string | null;
  error_message?: string | null;
}

export interface RAGStatus {
  total_chunks: number;
  indexed_textbooks: number;
  is_ready: boolean;
  textbook_ids: string[];
  embedding_backend: string;
  dimension: number;
}

export interface IndexTaskStatus {
  task_id: string;
  status: string;
  progress: number;
  message?: string | null;
  error_message?: string | null;
  total_chunks: number;
}

export interface Citation {
  chunk_id: string;
  textbook: string;
  chapter: string;
  page: number;
  content: string;
  relevance_score: number;
  duplicate_sources: string[];
}

export interface QueryResponse {
  answer: string;
  citations: Citation[];
  source_chunks: string[];
  retrieved_count: number;
  top_score: number;
}

export interface ChatResponse {
  conversation_id: string;
  response: string;
  suggestions: string[];
}

export interface HistoryResponse {
  conversation_id: string;
  messages: Array<{ role: string; content: string; timestamp: string; metadata?: Record<string, unknown> }>;
}

export interface Statistics {
  original_textbook_count: number;
  total_original_chars: number;
  total_compressed_chars: number;
  compression_ratio: number;
  is_within_limit: boolean;
  max_compression_ratio: number;
  total_decisions: number;
  merge_count: number;
  keep_count: number;
  remove_count: number;
  original_node_count: number;
  compressed_node_count: number;
  original_relation_count: number;
  compressed_relation_count: number;
  condensed_node_count: number;
  dropped_node_count: number;
  alignment_candidates: number;
  aligned_pair_count: number;
}

export interface IntegrationDecision {
  decision_id: string;
  action: string;
  affected_nodes: string[];
  result_node: string | null;
  reason: string;
  confidence: number;
}

export interface AlignedPairDetail {
  node1_id: string;
  node2_id: string;
  node1_name: string;
  node2_name: string;
  similarity: number;
  confidence: number;
  reason: string;
}

export interface AlignmentDetail {
  candidates: number;
  pairs: number;
  verified_by_llm: number;
  pairs_detail: AlignedPairDetail[];
}

export interface GraphNode {
  id: string;
  name: string;
  definition: string;
  category: string;
  chapter: string;
  frequency: number;
  textbook_id?: string;
}

export interface GraphLink {
  source: string;
  target: string;
  relation_type: string;
  description: string;
}

export interface GraphData {
  file_id?: string;
  textbook_title?: string;
  nodes: GraphNode[];
  links: GraphLink[];
  categories?: string[];
  pagination?: { page: number; page_size: number; total: number; total_pages: number };
}

export interface ExtractionStatus {
  file_id: string;
  status: string;
  progress: number;
  error_message?: string | null;
  total_nodes?: number;
  total_relations?: number;
}

// ----------------------------------------------------------------------
// 教材文件
// ----------------------------------------------------------------------
export function fetchFiles(): Promise<FileItem[]> {
  return request<FileItem[]>('/files/');
}

export function deleteFile(fileId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/files/${encodeURIComponent(fileId)}`, { method: 'DELETE' });
}

export function uploadTextbook(file: File): Promise<{ file_id: string; filename: string; size: number; message: string }> {
  const form = new FormData();
  form.append('file', file);
  return request('/upload/', { method: 'POST', body: form });
}

// ----------------------------------------------------------------------
// 解析 / 知识图谱
// ----------------------------------------------------------------------
export function parseTextbook(fileId: string): Promise<{ file_id: string; status: string; message: string }> {
  return request(`/parse/${encodeURIComponent(fileId)}/parse`, { method: 'POST' });
}

export function extractKnowledge(fileId: string, force = false): Promise<{ file_id: string; message: string; status: string }> {
  return request('/kg/extract', jsonInit('POST', { file_id: fileId, force }));
}

export function getExtractionStatus(fileId: string): Promise<ExtractionStatus> {
  return request<ExtractionStatus>(`/kg/status/${encodeURIComponent(fileId)}`);
}

export function fetchGraph(fileId: string, all = true): Promise<GraphData> {
  return request<GraphData>(`/kg/graph/${encodeURIComponent(fileId)}?all=${all ? 'true' : 'false'}`);
}

// ----------------------------------------------------------------------
// 跨教材整合
// ----------------------------------------------------------------------
export function startIntegration(fileIds: string[]): Promise<{ task_id: string; message: string }> {
  return request('/integration/merge', jsonInit('POST', { textbook_ids: fileIds }));
}

export function getIntegrationStatus(taskId: string): Promise<TaskStatus> {
  return request<TaskStatus>(`/integration/status/${encodeURIComponent(taskId)}`);
}

export function getIntegrationStatistics(taskId: string): Promise<Statistics> {
  return request<Statistics>(`/integration/statistics/${encodeURIComponent(taskId)}`);
}

export function getIntegrationDecisions(taskId: string): Promise<IntegrationDecision[]> {
  return request<IntegrationDecision[]>(`/integration/decisions/${encodeURIComponent(taskId)}`);
}

export function getIntegrationAlignment(taskId: string): Promise<AlignmentDetail> {
  return request<AlignmentDetail>(`/integration/alignment/${encodeURIComponent(taskId)}`);
}

export function getIntegratedGraph(taskId: string): Promise<{ nodes: GraphNode[]; links: GraphLink[]; statistics: Partial<Statistics> }> {
  return request(`/integration/graph/${encodeURIComponent(taskId)}`);
}

// ----------------------------------------------------------------------
// RAG
// ----------------------------------------------------------------------
export function getRAGStatus(): Promise<RAGStatus> {
  return request<RAGStatus>('/rag/status');
}

export function buildRAGIndex(fileIds: string[]): Promise<{ task_id: string; message: string }> {
  return request('/rag/index', jsonInit('POST', { file_ids: fileIds }));
}

export function getIndexTaskStatus(taskId: string): Promise<IndexTaskStatus> {
  return request<IndexTaskStatus>(`/rag/index/status/${encodeURIComponent(taskId)}`);
}

export function queryRAG(question: string): Promise<QueryResponse> {
  return request<QueryResponse>('/rag/query', jsonInit('POST', { question }));
}

export function clearRAGIndex(): Promise<{ message: string }> {
  return request('/rag/index', { method: 'DELETE' });
}

// ----------------------------------------------------------------------
// 多轮对话
// ----------------------------------------------------------------------
export function sendChatMessage(message: string, conversationId?: string): Promise<ChatResponse> {
  return request('/dialogue/chat', jsonInit('POST', { message, conversation_id: conversationId }));
}

export function getChatHistory(conversationId: string): Promise<HistoryResponse> {
  return request<HistoryResponse>(`/dialogue/history/${encodeURIComponent(conversationId)}`);
}

export function clearChatHistory(conversationId: string): Promise<{ message: string }> {
  return request(`/dialogue/history/${encodeURIComponent(conversationId)}`, { method: 'DELETE' });
}
