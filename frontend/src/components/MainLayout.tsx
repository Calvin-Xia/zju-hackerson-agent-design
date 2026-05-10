import React from 'react';
import { Layout, theme } from 'antd';
import TextbookPanel from './TextbookPanel';
import KnowledgeGraphPanel from './KnowledgeGraphPanel';
import FunctionPanel from './FunctionPanel';

const { Sider, Content } = Layout;

const MainLayout: React.FC = () => {
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width="22%"
        style={{
          background: colorBgContainer,
          borderRadius: borderRadiusLG,
          margin: 8,
          overflow: 'auto',
        }}
      >
        <TextbookPanel />
      </Sider>
      <Content
        style={{
          margin: '8px 0',
          padding: 16,
          background: colorBgContainer,
          borderRadius: borderRadiusLG,
          flex: 1,
          overflow: 'hidden',
        }}
      >
        <KnowledgeGraphPanel />
      </Content>
      <Sider
        width="28%"
        style={{
          background: colorBgContainer,
          borderRadius: borderRadiusLG,
          margin: 8,
          overflow: 'auto',
        }}
      >
        <FunctionPanel />
      </Sider>
    </Layout>
  );
};

export default MainLayout;
