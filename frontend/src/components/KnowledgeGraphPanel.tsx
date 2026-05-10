import React from 'react';
import { Card, Typography, Empty } from 'antd';

const { Title } = Typography;

const KnowledgeGraphPanel: React.FC = () => {
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Title level={4} style={{ marginBottom: 16 }}>
        知识图谱可视化
      </Title>
      <Card
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
        }}
        styles={{
          body: {
            flex: 1,
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
          },
        }}
      >
        <Empty
          description="上传教材后，知识图谱将在此处显示"
          style={{ margin: 'auto' }}
        />
      </Card>
    </div>
  );
};

export default KnowledgeGraphPanel;
