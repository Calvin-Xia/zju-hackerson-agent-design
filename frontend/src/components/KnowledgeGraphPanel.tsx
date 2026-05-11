import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, Select, Button, Spin, Empty, Modal, Typography, Tag, message, Space, Input } from 'antd';
import { RocketOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import axios from 'axios';

const { Text, Title, Paragraph } = Typography;
const { Search } = Input;

interface GraphNode {
  id: string;
  name: string;
  definition: string;
  category: string;
  chapter: string;
  frequency: number;
}

interface GraphLink {
  source: string;
  target: string;
  relation_type: string;
  description: string;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

interface FileItem {
  file_id: string;
  filename: string;
  parse_status: string;
}

const CATEGORY_COLORS: Record<string, string> = {
  '核心概念': '#5470c6',
  '定理': '#91cc75',
  '方法': '#fac858',
  '现象': '#ee6666',
};

const RELATION_LABELS: Record<string, string> = {
  'prerequisite': '前置依赖',
  'parallel': '并列关系',
  'contains': '包含关系',
  'applies_to': '应用关系',
};

const KnowledgeGraphPanel: React.FC = () => {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchFiles = async () => {
    try {
      const response = await axios.get('/api/files/');
      const parsedFiles = response.data.filter((f: FileItem) => f.parse_status === 'completed');
      setFiles(parsedFiles);
    } catch (error) {
      console.error('Failed to fetch files:', error);
    }
  };

  const fetchGraph = async (fileId: string) => {
    setLoading(true);
    try {
      const response = await axios.get(`/api/kg/graph/${fileId}`);
      setGraphData(response.data);
    } catch (error: any) {
      if (error.response?.status !== 404) {
        console.error('Failed to fetch graph:', error);
      }
      setGraphData(null);
    } finally {
      setLoading(false);
    }
  };

  const handleExtract = async () => {
    if (!selectedFileId) return;

    setExtracting(true);
    try {
      await axios.post('/api/kg/extract', { file_id: selectedFileId });
      message.success('知识点提取已开始，请稍候...');

      const pollInterval = setInterval(async () => {
        try {
          const statusResponse = await axios.get(`/api/kg/status/${selectedFileId}`);
          const status = statusResponse.data.status;

          if (status === 'completed') {
            clearInterval(pollInterval);
            pollIntervalRef.current = null;
            setExtracting(false);
            message.success('知识点提取完成！');
            fetchGraph(selectedFileId);
          } else if (status === 'failed') {
            clearInterval(pollInterval);
            pollIntervalRef.current = null;
            setExtracting(false);
            message.error('知识点提取失败');
          }
        } catch (error) {
          console.error('Failed to poll status:', error);
        }
      }, 3000);
      pollIntervalRef.current = pollInterval;
    } catch (error: any) {
      setExtracting(false);
      if (error.response?.data?.detail === 'Knowledge graph already exists') {
        message.info('知识图谱已存在');
        fetchGraph(selectedFileId);
      } else {
        message.error('启动提取失败');
      }
    }
  };

  useEffect(() => {
    fetchFiles();
  }, []);

  useEffect(() => {
    if (selectedFileId) {
      fetchGraph(selectedFileId);
    }
  }, [selectedFileId]);

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  const handleNodeClick = useCallback((params: any) => {
    if (params.dataType === 'node') {
      const node = graphData?.nodes.find(n => n.id === params.data.id);
      if (node) {
        setSelectedNode(node);
        setModalVisible(true);
      }
    }
  }, [graphData]);

  const getChartOption = () => {
    if (!graphData) return {};

    const filteredNodes = searchKeyword
      ? graphData.nodes.filter(n =>
          n.name.toLowerCase().includes(searchKeyword.toLowerCase()) ||
          n.definition.toLowerCase().includes(searchKeyword.toLowerCase())
        )
      : graphData.nodes;

    const nodeIds = new Set(filteredNodes.map(n => n.id));
    const filteredLinks = searchKeyword
      ? graphData.links.filter(l => nodeIds.has(l.source) && nodeIds.has(l.target))
      : graphData.links;

    const categories = Array.from(new Set(graphData.nodes.map(n => n.category)));

    return {
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          if (params.dataType === 'node') {
            return `<strong>${params.data.name}</strong><br/>分类: ${params.data.category}<br/>章节: ${params.data.chapter}<br/>频次: ${params.data.frequency}`;
          }
          if (params.dataType === 'edge') {
            return `${params.data.source} → ${params.data.target}<br/>关系: ${RELATION_LABELS[params.data.relation_type] || params.data.relation_type}`;
          }
          return '';
        },
      },
      legend: {
        data: categories,
        orient: 'vertical',
        right: 10,
        top: 10,
      },
      series: [{
        type: 'graph',
        layout: 'force',
        data: filteredNodes.map(node => ({
          ...node,
          symbolSize: Math.max(20, Math.min(60, 20 + node.frequency * 10)),
          category: categories.indexOf(node.category),
          itemStyle: {
            color: CATEGORY_COLORS[node.category] || '#5470c6',
          },
        })),
        links: filteredLinks.map(link => ({
          ...link,
          lineStyle: {
            curveness: 0.1,
          },
        })),
        categories: categories.map(name => ({ name })),
        roam: true,
        draggable: true,
        label: {
          show: true,
          position: 'right',
          formatter: '{b}',
          fontSize: 12,
        },
        lineStyle: {
          color: '#aaa',
          curveness: 0.1,
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: {
            width: 4,
          },
        },
        force: {
          repulsion: 200,
          gravity: 0.1,
          edgeLength: 150,
        },
      }],
    };
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Title level={4} style={{ marginBottom: 16 }}>
        知识图谱可视化
      </Title>

      <Card style={{ marginBottom: 16 }} styles={{ body: { padding: '12px' } }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Select
            placeholder="选择教材文件"
            style={{ width: '100%' }}
            value={selectedFileId}
            onChange={setSelectedFileId}
            options={files.map(f => ({
              value: f.file_id,
              label: f.filename,
            }))}
          />
          <Space style={{ width: '100%' }}>
            <Button
              type="primary"
              icon={<RocketOutlined />}
              onClick={handleExtract}
              disabled={!selectedFileId || extracting}
              loading={extracting}
            >
              {extracting ? '提取中...' : '提取知识图谱'}
            </Button>
            {graphData && (
              <Search
                placeholder="搜索知识点"
                allowClear
                style={{ width: 200 }}
                onSearch={setSearchKeyword}
                onChange={e => setSearchKeyword(e.target.value)}
              />
            )}
          </Space>
        </Space>
      </Card>

      <Card style={{ flex: 1, overflow: 'hidden' }} styles={{ body: { height: '100%', padding: '12px' } }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
            <Spin size="large" tip="加载中..." />
          </div>
        ) : graphData && graphData.nodes.length > 0 ? (
          <ReactECharts
            option={getChartOption()}
            style={{ height: '100%', width: '100%' }}
            onEvents={{ click: handleNodeClick }}
          />
        ) : (
          <Empty
            description={selectedFileId ? '点击"提取知识图谱"按钮开始提取' : '请先选择一个教材文件'}
            style={{ margin: 'auto' }}
          />
        )}
      </Card>

      <Modal
        title="知识点详情"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={null}
        width={500}
      >
        {selectedNode && (
          <div>
            <Title level={5}>{selectedNode.name}</Title>
            <Space wrap style={{ marginBottom: 16 }}>
              <Tag color={CATEGORY_COLORS[selectedNode.category]}>
                {selectedNode.category}
              </Tag>
              <Tag>频次: {selectedNode.frequency}</Tag>
            </Space>
            <Paragraph>
              <Text strong>定义: </Text>
              {selectedNode.definition}
            </Paragraph>
            <Paragraph>
              <Text strong>章节: </Text>
              {selectedNode.chapter}
            </Paragraph>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default KnowledgeGraphPanel;
