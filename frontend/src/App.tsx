import React from 'react';
import { ConfigProvider, Layout, theme } from 'antd';
import MainLayout from './components/MainLayout';

const App: React.FC = () => {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 6,
        },
      }}
    >
      <Layout style={{ minHeight: '100vh' }}>
        <MainLayout />
      </Layout>
    </ConfigProvider>
  );
};

export default App;
