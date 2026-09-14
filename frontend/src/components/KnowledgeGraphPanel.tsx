import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, Select, Button, Spin, Empty, Modal, Typography, Tag, message, Space, Input, Segmented, Alert } from 'antd';
import { RocketOutlined, ReloadOutlined, MergeOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import {
  fetchFiles,
  fetchGraph,
  extractKnowledge,
  getExtractionStatus,
  getIntegratedGraph,
  FileItem,
  GraphData,
  GraphLink,
  GraphNode,
} from '../api/client';
import { FILES_CHANGED_EVENT } from './FileList';


const { Text, Title, Paragraph } = Typography;
const { Search } = Input;

const CATEGORY_COLORS: Record<string, string> = {
  '核心概念': '#5470c6',
  '定理': '#91cc75',
  '方法': '#fac858',
  '现象': '#ee6666',
  '公式': '#9a60b4',
  '实验': '#fc8452',
};

const RELATION_LABELS: Record<string, string> = {
  prerequisite: '前置依赖',
  parallel: '并列关系',
  contains: '包含关系',
  applies_to: '应用关系',
};

const TEXTBOOK_COLORS = [
  '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de',
  '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc', '#48b8d0',
];

const getTextbookColor = (textbookId: string | undefined, textbookIds: string[]): string => {
  if (!textbookId) return TEXTBOOK_COLORS[0];
  const index = textbookIds.indexOf(textbookId);
  return TEXTBOOK_COLORS[index >= 0 ? index % TEXTBOOK_COLORS.length : 0];
};

const KnowledgeGraphPanel: React.FC = () => {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [sourceMode, setSourceMode] = useState<'textbook' | 'integrated'>('textbook');
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [integratedTaskId, setIntegratedTaskId] = useState<string | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [graphTitle, setGraphTitle] = useState('');
  const [loading, setLoading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [selectedRelation, setSelectedRelation] = useState<GraphLink | null>(null);
  const [relationModalVisible, setRelationModalVisible] = useState(false);
  const [colorMode, setColorMode] = useState<'category' | 'textbook'>('category');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const chartRef = useRef<ReactECharts>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadFiles = useCallback(async () => {
    try {
      const data = await fetchFiles();
      setFiles(data.filter((f) => f.parse_status === 'completed'));
    } catch (error) {
      console.error('获取文件列表失败', error);
      message.error(error instanceof Error ? error.message : '获取文件列表失败');
    }
  }, []);

  const selectedFile = files.find((f) => f.file_id === selectedFileId) ?? null;

  const loadTextbookGraph = useCallback(async (fileId: string) => {
    setLoading(true);
    try {
      const data = await fetchGraph(fileId);
      setGraphData(data);
      setGraphTitle(data.textbook_title || fileId);
    } catch {
      // 尚未抽取图谱时后端返回 404，这里静默显示空状态
      setGraphData(null);
      setGraphTitle('');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadIntegratedGraph = useCallback(async (taskId: string) => {
    setLoading(true);
    try {
      const data = await getIntegratedGraph(taskId);
      setGraphData({ nodes: data.nodes, links: data.links });
      setGraphTitle(`整合结果 · ${taskId}`);
    } catch (error) {
      setGraphData(null);
      setGraphTitle('');
      message.error(error instanceof Error ? error.message : '加载整合结果失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadFiles();
    const onChanged = () => void loadFiles();
    window.addEventListener(FILES_CHANGED_EVENT, onChanged);
    return () => {
      window.removeEventListener(FILES_CHANGED_EVENT, onChanged);
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [loadFiles]);

  useEffect(() => {
    if (sourceMode === 'textbook' && selectedFileId) {
      void loadTextbookGraph(selectedFileId);
    }
  }, [sourceMode, selectedFileId, loadTextbookGraph]);

  useEffect(() => {
    if (sourceMode !== 'integrated') return;
    const stored = localStorage.getItem('last_integration_task');
    setIntegratedTaskId(stored);
    if (stored) {
      void loadIntegratedGraph(stored);
    } else {
      setGraphData(null);
      setGraphTitle('');
    }
  }, [sourceMode, loadIntegratedGraph]);

  const handleExtract = async (force = false) => {
    if (!selectedFileId) return;
    setExtracting(true);
    try {
      const res = await extractKnowledge(selectedFileId, force);
      if (res.status === 'completed' && !force) {
        message.info('知识图谱已存在，正在加载');
        setExtracting(false);
        await loadTextbookGraph(selectedFileId);
        return;
      }
      message.success('知识点提取已开始，请稍候');
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const status = await getExtractionStatus(selectedFileId);
          if (status.status === 'completed') {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setExtracting(false);
            message.success(`知识点提取完成（${status.total_nodes ?? 0} 个知识点）`);
            await loadTextbookGraph(selectedFileId);
            window.dispatchEvent(new Event(FILES_CHANGED_EVENT));
          } else if (status.status === 'failed') {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setExtracting(false);
            message.error(status.error_message ?? '知识点提取失败');
          }
        } catch (error) {
          console.error('轮询抽取状态失败', error);
        }
      }, 3000);
    } catch (error) {
      setExtracting(false);
      message.error(error instanceof Error ? error.message : '启动提取失败');
    }
  };

  const handleChartClick = useCallback(
    (params: { dataType?: string; data?: Record<string, unknown> }) => {
      if (params.dataType === 'node' && params.data) {
        const node = graphData?.nodes.find((n) => n.id === params.data?.id);
        if (node) {
          setSelectedNode(node);
          setModalVisible(true);
        }
      } else if (params.dataType === 'edge' && params.data) {
        const link = graphData?.links.find(
          (l) => l.source === params.data?.source && l.target === params.data?.target,
        );
        if (link) {
          setSelectedRelation(link);
          setRelationModalVisible(true);
        }
      }
    },
    [graphData],
  );

  const getChartOption = () => {
    if (!graphData || graphData.nodes.length === 0) return {};

    const keyword = searchKeyword.trim().toLowerCase();
    const filteredNodes = keyword
      ? graphData.nodes.filter(
          (n) => n.name.toLowerCase().includes(keyword) || (n.definition ?? '').toLowerCase().includes(keyword),
        )
      : graphData.nodes;

    const nodeIds = new Set(filteredNodes.map((n) => n.id));
    const filteredLinks = keyword
      ? graphData.links.filter((l) => nodeIds.has(l.source) && nodeIds.has(l.target))
      : graphData.links;

    const categories = Array.from(new Set(graphData.nodes.map((n) => n.category)));
    const textbookIds = Array.from(
      new Set(graphData.nodes.map((n) => n.textbook_id || 'unknown')),
    );

    return {
      tooltip: {
        trigger: 'item',
        confine: true,
        formatter: (params: { dataType?: string; data?: any }) => {
          if (params.dataType === 'node') {
            const data = params.data;
            return `<strong>${data.name}</strong><br/>分类：${data.categoryName ?? '未分类'}<br/>章节：${data.chapter || '无'}<br/>频次：${data.frequency || 1}`;
          }
          if (params.dataType === 'edge') {
            const data = params.data;
            const type = RELATION_LABELS[data.relation_type] || data.relation_type || '关联';
            return `${data.sourceName ?? data.source} → ${data.targetName ?? data.target}<br/>关系：${type}`;
          }
          return '';
        },
      },
      legend: {
        data: colorMode === 'category' ? categories : textbookIds,
        orient: 'vertical',
        right: 10,
        top: 10,
        type: 'scroll',
      },
      series: [
        {
          type: 'graph',
          layout: 'force',
          data: filteredNodes.map((node) => ({
            id: node.id,
            name: node.name,
            symbolSize: Math.max(20, Math.min(60, 20 + (node.frequency || 1) * 8)),
            category:
              colorMode === 'category'
                ? categories.indexOf(node.category)
                : textbookIds.indexOf(node.textbook_id || 'unknown'),
            categoryName: node.category,
            chapter: node.chapter,
            frequency: node.frequency,
            itemStyle: {
              color:
                colorMode === 'category'
                  ? CATEGORY_COLORS[node.category] || '#5470c6'
                  : getTextbookColor(node.textbook_id, textbookIds),
            },
          })),
          // relation_type 必须带进 links，否则边的 tooltip 取不到关系类型
          links: filteredLinks.map((link) => ({
            source: link.source,
            target: link.target,
            relation_type: link.relation_type,
            description: link.description,
            sourceName: graphData.nodes.find((n) => n.id === link.source)?.name,
            targetName: graphData.nodes.find((n) => n.id === link.target)?.name,
          })),
          categories:
            colorMode === 'category'
              ? categories.map((name) => ({ name }))
              : textbookIds.map((id) => ({ name: id })),
          roam: true,
          draggable: true,
          label: { show: true, position: 'right', formatter: '{b}', fontSize: 12 },
          lineStyle: { color: '#aaa', curveness: 0.1 },
          emphasis: { focus: 'adjacency', lineStyle: { width: 4 } },
          force: { repulsion: 200, gravity: 0.1, edgeLength: 150 },
        },
      ],
    };
  };

  const canExtract = sourceMode === 'textbook' && !!selectedFileId;
  const hasGraph = !!selectedFile?.has_graph;

  return (
    <div style={{ height: '100%', minHeight: '500px', display: 'flex', flexDirection: 'column' }}>
      <Title level={4} style={{ marginBottom: 16 }}>
        知识图谱可视化
      </Title>

      <Card style={{ marginBottom: 16 }} styles={{ body: { padding: '12px' } }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Segmented
            block
            value={sourceMode}
            onChange={(value) => setSourceMode(value as 'textbook' | 'integrated')}
            options={[
              { label: '单本教材', value: 'textbook' },
              { label: '跨教材整合结果', value: 'integrated' },
            ]}
          />
          {sourceMode === 'textbook' ? (
            <Select
              placeholder="选择教材文件"
              style={{ width: '100%' }}
              value={selectedFileId}
              onChange={setSelectedFileId}
              options={files.map((f) => ({
                value: f.file_id,
                label: `${f.filename}${f.has_graph ? '' : '（未提取）'}`,
              }))}
            />
          ) : (
            <Text type="secondary">
              {integratedTaskId ? `当前展示整合任务 ${integratedTaskId} 的图谱` : '尚未执行整合'}
            </Text>
          )}

          <Space style={{ width: '100%' }} wrap>
            {sourceMode === 'textbook' && (
              <>
                <Button
                  type="primary"
                  icon={<RocketOutlined />}
                  onClick={() => handleExtract(false)}
                  disabled={!canExtract || extracting}
                  loading={extracting}
                >
                  {hasGraph ? '查看图谱' : '提取知识图谱'}
                </Button>
                {hasGraph && (
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={() => handleExtract(true)}
                    disabled={extracting}
                  >
                    重新提取
                  </Button>
                )}
              </>
            )}
            {sourceMode === 'integrated' && (
              <Button
                icon={<ReloadOutlined />}
                onClick={() => integratedTaskId && loadIntegratedGraph(integratedTaskId)}
                disabled={!integratedTaskId}
              >
                刷新
              </Button>
            )}
            {graphData && graphData.nodes.length > 0 && (
              <>
                <Search
                  placeholder="搜索知识点"
                  allowClear
                  style={{ width: 180 }}
                  onSearch={setSearchKeyword}
                  onChange={(e) => setSearchKeyword(e.target.value)}
                />
                <Button
                  type={colorMode === 'category' ? 'primary' : 'default'}
                  size="small"
                  onClick={() => setColorMode('category')}
                >
                  按分类
                </Button>
                <Button
                  type={colorMode === 'textbook' ? 'primary' : 'default'}
                  size="small"
                  onClick={() => setColorMode('textbook')}
                >
                  按教材
                </Button>
              </>
            )}
          </Space>
          {graphTitle && (
            <Text type="secondary">
              {graphTitle} · 知识点 {graphData?.nodes.length ?? 0} 个 · 关系 {graphData?.links.length ?? 0} 条
            </Text>
          )}
        </Space>
      </Card>

      <Card
        style={{
          flex: 1,
          overflow: 'hidden',
          position: isFullscreen ? 'fixed' : 'relative',
          top: isFullscreen ? 0 : undefined,
          left: isFullscreen ? 0 : undefined,
          width: isFullscreen ? '100vw' : undefined,
          height: isFullscreen ? '100vh' : undefined,
          zIndex: isFullscreen ? 1000 : undefined,
          minHeight: 400,
        }}
        styles={{ body: { height: '100%', padding: '12px', position: 'relative' } }}
      >
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
            <Spin size="large" />
          </div>
        ) : graphData && graphData.nodes.length > 0 ? (
          <>
            <Space style={{ position: 'absolute', right: 16, top: 16, zIndex: 10 }}>
              <Button
                size="small"
                onClick={() => chartRef.current?.getEchartsInstance()?.dispatchAction({ type: 'graphZoom', zoom: 1.2 })}
              >
                放大
              </Button>
              <Button
                size="small"
                onClick={() => chartRef.current?.getEchartsInstance()?.dispatchAction({ type: 'graphZoom', zoom: 0.8 })}
              >
                缩小
              </Button>
              <Button size="small" onClick={() => setIsFullscreen(!isFullscreen)}>
                {isFullscreen ? '退出全屏' : '全屏'}
              </Button>
            </Space>
            <ReactECharts
              ref={chartRef}
              option={getChartOption()}
              style={{ height: '100%', width: '100%' }}
              onEvents={{ click: handleChartClick }}
              notMerge
            />
          </>
        ) : sourceMode === 'integrated' && !integratedTaskId ? (
          <Alert
            type="info"
            showIcon
            icon={<MergeOutlined />}
            message="尚未执行跨教材整合"
            description="请先在右侧「整合操作」中完成整合，随后可在此查看整合后的知识图谱。"
            style={{ margin: 'auto', maxWidth: 420 }}
          />
        ) : (
          <Empty
            description={
              sourceMode === 'integrated'
                ? '整合结果为空'
                : selectedFileId
                ? hasGraph
                  ? '图谱为空，可尝试「重新提取」'
                  : '点击「提取知识图谱」开始提取'
                : '请先选择一个教材文件'
            }
            style={{ margin: 'auto' }}
          />
        )}
      </Card>

      <Modal title="知识点详情" open={modalVisible} onCancel={() => setModalVisible(false)} footer={null} width={520}>
        {selectedNode && (
          <div>
            <Title level={5}>{selectedNode.name}</Title>
            <Space wrap style={{ marginBottom: 16 }}>
              <Tag color={CATEGORY_COLORS[selectedNode.category]}>{selectedNode.category}</Tag>
              <Tag>频次: {selectedNode.frequency}</Tag>
              {selectedNode.textbook_id && <Tag color="blue">{selectedNode.textbook_id}</Tag>}
            </Space>
            <Paragraph>
              <Text strong>定义: </Text>
              {selectedNode.definition || '（无）'}
            </Paragraph>
            <Paragraph>
              <Text strong>章节: </Text>
              {selectedNode.chapter || '（无）'}
            </Paragraph>
          </div>
        )}
      </Modal>

      <Modal
        title="关系详情"
        open={relationModalVisible}
        onCancel={() => setRelationModalVisible(false)}
        footer={null}
        width={440}
      >
        {selectedRelation && (
          <div>
            <Paragraph>
              <Text strong>源节点: </Text>
              {graphData?.nodes.find((n) => n.id === selectedRelation.source)?.name ?? selectedRelation.source}
            </Paragraph>
            <Paragraph>
              <Text strong>目标节点: </Text>
              {graphData?.nodes.find((n) => n.id === selectedRelation.target)?.name ?? selectedRelation.target}
            </Paragraph>
            <Paragraph>
              <Text strong>关系类型: </Text>
              <Tag>{RELATION_LABELS[selectedRelation.relation_type] || selectedRelation.relation_type}</Tag>
            </Paragraph>
            <Paragraph>
              <Text strong>描述: </Text>
              {selectedRelation.description || '（无）'}
            </Paragraph>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default KnowledgeGraphPanel;
