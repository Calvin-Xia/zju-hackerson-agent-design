import React from 'react';
import { Button, Typography } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';

const { Text, Paragraph } = Typography;

const ReportTab: React.FC = () => {
  return (
    <div>
      <Text strong style={{ display: 'block', marginBottom: 12 }}>
        整合报告
      </Text>
      <div
        style={{
          height: 200,
          border: '1px solid #d9d9d9',
          borderRadius: 6,
          marginBottom: 16,
          padding: 12,
          overflow: 'auto',
        }}
      >
        <Paragraph type="secondary">
          完成教材整合后，报告将在此处显示
        </Paragraph>
      </div>
      <Button
        type="primary"
        icon={<FileTextOutlined />}
        block
        disabled
      >
        生成报告
      </Button>
    </div>
  );
};

export default ReportTab;
