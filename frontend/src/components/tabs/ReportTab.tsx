import React, { useState, useEffect } from 'react';
import { Button, Typography, message, Descriptions, Spin, Empty, Alert, Tag, Table, Tabs, Space } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import {
  getIntegrationStatistics,
  getIntegrationDecisions,
  getIntegrationAlignment,
  Statistics,
  IntegrationDecision,
  AlignmentDetail,
} from '../../api/client';

const { Text } = Typography;

const ACTION_LABELS: Record<string, { text: string; color: string }> = {
  merge: { text: '合并', color: 'blue' },
  keep: { text: '保留', color: 'green' },
  remove: { text: '删除', color: 'red' },
};

const ReportTab: React.FC = () => {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [stats, setStats] = useState<Statistics | null>(null);
  const [decisions, setDecisions] = useState<IntegrationDecision[]>([]);
  const [alignment, setAlignment] = useState<AlignmentDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const loadAll = async (id: string) => {
    setLoading(true);
    try {
      setStats(await getIntegrationStatistics(id));
      // 决策与对齐明细属于锦上添花，失败时不影响主报告展示
      getIntegrationDecisions(id).then(setDecisions).catch(() => setDecisions([]));
      getIntegrationAlignment(id).then(setAlignment).catch(() => setAlignment(null));
    } catch (err) {
      message.error(err instanceof Error ? err.message : '获取统计数据失败');
      setStats(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const stored = localStorage.getItem('last_integration_task');
    if (stored) {
      setTaskId(stored);
      void loadAll(stored);
    }
  }, []);

  if (!taskId) {
    return (
      <div>
        <Text strong style={{ display: 'block', marginBottom: 12 }}>
          整合报告
        </Text>
        <Empty description="请先在「整合操作」中执行教材整合" />
      </div>
    );
  }

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 12 }}>
        <Text strong>整合报告</Text>
        <Space size={4}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {taskId}
          </Text>
          <Button
            icon={<ReloadOutlined />}
            size="small"
            onClick={() => loadAll(taskId)}
            loading={loading}
          >
            刷新
          </Button>
        </Space>
      </Space>

      <Spin spinning={loading}>
        {stats ? (
          <>
            <Alert
              type={stats.is_within_limit ? 'success' : 'warning'}
              showIcon
              style={{ marginBottom: 12 }}
              message={
                <Space wrap>
                  <span>压缩比 {(stats.compression_ratio * 100).toFixed(1)}%</span>
                  <Tag color={stats.is_within_limit ? 'green' : 'red'}>
                    {stats.is_within_limit ? '满足 ≤ 30% 要求' : '超过 30% 上限'}
                  </Tag>
                </Space>
              }
            />
            <Tabs
              size="small"
              items={[
                {
                  key: 'summary',
                  label: '汇总',
                  children: (
                    <Descriptions column={1} bordered size="small">
                      <Descriptions.Item label="教材数量">{stats.original_textbook_count}</Descriptions.Item>
                      <Descriptions.Item label="原始字符数">
                        {stats.total_original_chars.toLocaleString()}
                      </Descriptions.Item>
                      <Descriptions.Item label="压缩后字符数">
                        {stats.total_compressed_chars.toLocaleString()}
                      </Descriptions.Item>
                      <Descriptions.Item label="压缩比">
                        {(stats.compression_ratio * 100).toFixed(1)}%
                      </Descriptions.Item>
                      <Descriptions.Item label="知识点">
                        {stats.original_node_count} → {stats.compressed_node_count}
                      </Descriptions.Item>
                      <Descriptions.Item label="关系">
                        {stats.original_relation_count} → {stats.compressed_relation_count}
                      </Descriptions.Item>
                      <Descriptions.Item label="决策总数">{stats.total_decisions}</Descriptions.Item>
                      <Descriptions.Item label="合并 / 保留 / 删除">
                        {stats.merge_count} / {stats.keep_count} / {stats.remove_count}
                      </Descriptions.Item>
                      <Descriptions.Item label="摘要 / 丢弃节点">
                        {stats.condensed_node_count} / {stats.dropped_node_count}
                      </Descriptions.Item>
                    </Descriptions>
                  ),
                },
                {
                  key: 'decisions',
                  label: `决策 (${decisions.length})`,
                  children: (
                    <Table
                      size="small"
                      rowKey="decision_id"
                      dataSource={decisions}
                      pagination={{ pageSize: 8, size: 'small' }}
                      columns={[
                        {
                          title: '动作',
                          dataIndex: 'action',
                          width: 70,
                          render: (action: string) => {
                            const meta = ACTION_LABELS[action] ?? { text: action, color: 'default' };
                            return <Tag color={meta.color}>{meta.text}</Tag>;
                          },
                        },
                        { title: '理由', dataIndex: 'reason' },
                        {
                          title: '置信度',
                          dataIndex: 'confidence',
                          width: 80,
                          render: (value: number) => value.toFixed(2),
                        },
                      ]}
                    />
                  ),
                },
                {
                  key: 'alignment',
                  label: `语义对齐 (${alignment?.pairs ?? 0})`,
                  children: alignment && alignment.pairs_detail.length > 0 ? (
                    <Table
                      size="small"
                      rowKey={(row) => `${row.node1_id}-${row.node2_id}`}
                      dataSource={alignment.pairs_detail}
                      pagination={{ pageSize: 8, size: 'small' }}
                      columns={[
                        {
                          title: '知识点对',
                          render: (_: unknown, row) => (
                            <Text>
                              {row.node1_name} ↔ {row.node2_name}
                            </Text>
                          ),
                        },
                        {
                          title: '相似度',
                          dataIndex: 'similarity',
                          width: 90,
                          render: (value: number) => value.toFixed(3),
                        },
                        { title: '判定依据', dataIndex: 'reason' },
                      ]}
                    />
                  ) : (
                    <Empty
                      description={
                        alignment
                          ? `候选 ${alignment.candidates} 对，未判定出等价知识点`
                          : '暂无对齐数据'
                      }
                    />
                  ),
                },
              ]}
            />
          </>
        ) : (
          <Empty description="暂无统计数据（整合可能尚未完成）" />
        )}
      </Spin>
    </div>
  );
};

export default ReportTab;
