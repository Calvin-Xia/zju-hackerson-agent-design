import React from 'react';
import { Card, Tabs, Typography } from 'antd';
import IntegrationTab from './tabs/IntegrationTab';
import RAGTab from './tabs/RAGTab';
import DialogueTab from './tabs/DialogueTab';
import ReportTab from './tabs/ReportTab';

const { Title } = Typography;

const FunctionPanel: React.FC = () => {
  const tabItems = [
    {
      key: 'integration',
      label: '整合操作',
      children: <IntegrationTab />,
    },
    {
      key: 'rag',
      label: 'RAG问答',
      children: <RAGTab />,
    },
    {
      key: 'dialogue',
      label: '对话',
      children: <DialogueTab />,
    },
    {
      key: 'report',
      label: '报告',
      children: <ReportTab />,
    },
  ];

  return (
    <div style={{ padding: '16px' }}>
      <Title level={4} style={{ marginBottom: 16 }}>
        功能面板
      </Title>
      <Card styles={{ body: { padding: '12px' } }}>
        <Tabs
          defaultActiveKey="integration"
          destroyInactiveTabPane
          items={tabItems}
          style={{ height: '100%' }}
        />
      </Card>
    </div>
  );
};

export default FunctionPanel;
