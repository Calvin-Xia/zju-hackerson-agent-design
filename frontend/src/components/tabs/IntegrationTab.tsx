import React, { useState, useEffect, useRef } from 'react';
import { Button, Typography, message, Progress, Checkbox, Alert, Descriptions, Tag, Space } from 'antd';
import { MergeOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  fetchFiles,
  startIntegration,
  getIntegrationStatus,
  getIntegrationStatistics,
  FileItem,
  Statistics,
} from '../../api/client';

const { Text } = Typography;

const STATUS_LABELS: Record<string, string> = {
  pending: '排队中',
  processing: '整合中',
  completed: '已完成',
  failed: '失败',
};

const IntegrationTab: React.FC = () => {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [taskStatus, setTaskStatus] = useState<string>('');
  const [taskMessage, setTaskMessage] = useState<string>('');
  const [stats, setStats] = useState<Statistics | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadFiles = async () => {
    try {
      const data = await fetchFiles();
      // 只有解析完成的教材才有知识点可供整合
      setFiles(data.filter((f) => f.parse_status === 'completed'));
    } catch (err) {
      message.error(err instanceof Error ? err.message : '获取文件列表失败');
    }
  };

  useEffect(() => {
    loadFiles();
    const stored = localStorage.getItem('last_integration_task');
    if (stored) {
      setTaskId(stored);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  useEffect(() => {
    if (!taskId) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const status = await getIntegrationStatus(taskId);
        if (cancelled) return;
        setProgress(Math.max(0, Math.min(100, status.progress)));
        setTaskStatus(status.status);
        setTaskMessage(status.message ?? '');

        if (status.status === 'completed') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setLoading(false);
          message.success('整合完成');
          try {
            setStats(await getIntegrationStatistics(taskId));
          } catch {
            /* 统计拉取失败不影响任务完成的提示 */
          }
        } else if (status.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setLoading(false);
          message.error(`整合失败：${status.error_message ?? '未知错误'}`);
        }
      } catch (err) {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        setLoading(false);
        message.error(err instanceof Error ? err.message : '获取整合状态失败');
      }
    };

    void poll();
    pollRef.current = setInterval(poll, 1000);

    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [taskId]);

  const handleStart = async () => {
    if (selectedFiles.length < 2) {
      message.warning('请至少选择 2 本教材进行整合');
      return;
    }
    setLoading(true);
    setStats(null);
    setProgress(0);
    try {
      const result = await startIntegration(selectedFiles);
      localStorage.setItem('last_integration_task', result.task_id);
      setTaskId(result.task_id);
      setTaskStatus('pending');
    } catch (err) {
      setLoading(false);
      message.error(err instanceof Error ? err.message : '启动整合失败');
    }
  };

  const ratioPercent = stats ? stats.compression_ratio * 100 : 0;

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 12 }}>
        <Text strong>选择要整合的教材（至少 2 本）</Text>
        <Button size="small" icon={<ReloadOutlined />} onClick={loadFiles}>
          刷新
        </Button>
      </Space>

      <div
        style={{
          marginBottom: 16,
          maxHeight: 200,
          overflow: 'auto',
          border: '1px solid #d9d9d9',
          borderRadius: 6,
          padding: 8,
        }}
      >
        {files.length === 0 ? (
          <Text type="secondary">暂无解析完成的教材，请先在左侧上传</Text>
        ) : (
          <Checkbox.Group
            value={selectedFiles}
            onChange={(values) => setSelectedFiles(values as string[])}
            style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
          >
            {files.map((f) => (
              <Checkbox key={f.file_id} value={f.file_id}>
                {f.filename}
                {f.has_graph ? '' : '（尚未提取知识点）'}
              </Checkbox>
            ))}
          </Checkbox.Group>
        )}
      </div>

      {taskId && (
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary">
            状态：{STATUS_LABELS[taskStatus] ?? taskStatus}
            {taskMessage ? ` · ${taskMessage}` : ''}
          </Text>
          <Progress
            percent={Math.round(progress)}
            status={taskStatus === 'failed' ? 'exception' : taskStatus === 'completed' ? 'success' : 'active'}
          />
        </div>
      )}

      <Button
        type="primary"
        icon={<MergeOutlined />}
        block
        loading={loading}
        disabled={selectedFiles.length < 2}
        onClick={handleStart}
      >
        开始整合
      </Button>

      {stats && (
        <div style={{ marginTop: 16 }}>
          <Alert
            type={stats.is_within_limit ? 'success' : 'warning'}
            showIcon
            message={
              <Space>
                <span>压缩比 {ratioPercent.toFixed(1)}%</span>
                <Tag color={stats.is_within_limit ? 'green' : 'orange'}>
                  上限 {(stats.max_compression_ratio * 100).toFixed(0)}%
                </Tag>
                <Tag color={stats.is_within_limit ? 'green' : 'red'}>
                  {stats.is_within_limit ? '达标' : '超标'}
                </Tag>
              </Space>
            }
            style={{ marginBottom: 12 }}
          />
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="教材数量">{stats.original_textbook_count}</Descriptions.Item>
            <Descriptions.Item label="知识点">
              {stats.original_node_count} → {stats.compressed_node_count}
            </Descriptions.Item>
            <Descriptions.Item label="关系">
              {stats.original_relation_count} → {stats.compressed_relation_count}
            </Descriptions.Item>
            <Descriptions.Item label="字数">
              {stats.total_original_chars.toLocaleString()} → {stats.total_compressed_chars.toLocaleString()}
            </Descriptions.Item>
            <Descriptions.Item label="决策">
              合并 {stats.merge_count} / 保留 {stats.keep_count} / 删除 {stats.remove_count}
            </Descriptions.Item>
            <Descriptions.Item label="语义对齐">
              候选 {stats.alignment_candidates} 对，判定等价 {stats.aligned_pair_count} 对
            </Descriptions.Item>
            <Descriptions.Item label="摘要 / 丢弃">
              {stats.condensed_node_count} / {stats.dropped_node_count}
            </Descriptions.Item>
          </Descriptions>
        </div>
      )}
    </div>
  );
};

export default IntegrationTab;
