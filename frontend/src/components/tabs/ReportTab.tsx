import React, { useState, useEffect } from 'react';
import { Button, Typography, message, Descriptions, Spin, Empty } from 'antd';
import { FileTextOutlined, ReloadOutlined } from '@ant-design/icons';
import { getIntegrationStatus, getIntegrationStatistics, TaskStatus, Statistics } from '../../api/client';

const { Text, Paragraph } = Typography;

const ReportTab: React.FC = () => {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [stats, setStats] = useState<Statistics | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem('last_integration_task');
    if (stored) {
      setTaskId(stored);
      loadStatistics(stored);
    }
  }, []);

  const loadStatistics = async (id: string) => {
    setLoading(true);
    try {
      const data = await getIntegrationStatistics(id);
      setStats(data);
    } catch (err) {
      console.error('获取统计失败');
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = () => {
    if (taskId) {
      loadStatistics(taskId);
    }
  };

  if (!taskId) {
    return (
      <div>
        <Text strong style={{ display: 'block', marginBottom: 12 }}>整合报告</Text>
        <Empty description="请先执行教材整合" />
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong>整合报告</Text>
        <Button icon={<ReloadOutlined />} size="small" onClick={handleRefresh} loading={loading}>刷新</Button>
      </div>
      <Spin spinning={loading}>
        {stats ? (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="教材数量">{stats.original_textbook_count}</Descriptions.Item>
            <Descriptions.Item label="原始字符数">{stats.total_original_chars.toLocaleString()}</Descriptions.Item>
            <Descriptions.Item label="压缩后字符数">{stats.total_compressed_chars.toLocaleString()}</Descriptions.Item>
            <Descriptions.Item label="压缩比">{(stats.compression_ratio * 100).toFixed(1)}%</Descriptions.Item>
            <Descriptions.Item label="决策总数">{stats.total_decisions}</Descriptions.Item>
            <Descriptions.Item label="合并操作">{stats.merge_count}</Descriptions.Item>
            <Descriptions.Item label="保留操作">{stats.keep_count}</Descriptions.Item>
            <Descriptions.Item label="删除操作">{stats.remove_count}</Descriptions.Item>
            <Descriptions.Item label="原始节点数">{stats.original_node_count}</Descriptions.Item>
            <Descriptions.Item label="压缩后节点数">{stats.compressed_node_count}</Descriptions.Item>
            <Descriptions.Item label="原始关系数">{stats.original_relation_count}</Descriptions.Item>
            <Descriptions.Item label="压缩后关系数">{stats.compressed_relation_count}</Descriptions.Item>
          </Descriptions>
        ) : (
          <Empty description="暂无统计数据" />
        )}
      </Spin>
    </div>
  );
};

export default ReportTab;
