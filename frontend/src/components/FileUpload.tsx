import React, { useCallback } from 'react';
import { InboxOutlined } from '@ant-design/icons';
import { Upload, message } from 'antd';
import type { UploadProps } from 'antd';

const { Dragger } = Upload;

const ALLOWED_EXTENSIONS = ['pdf', 'md', 'txt', 'docx', 'xlsx'];

const FileUpload: React.FC = () => {
  const props: UploadProps = {
    name: 'file',
    multiple: true,
    action: '/api/upload',
    accept: ALLOWED_EXTENSIONS.map((ext) => `.${ext}`).join(','),
    beforeUpload: (file) => {
      const extension = file.name.split('.').pop()?.toLowerCase();
      if (!extension || !ALLOWED_EXTENSIONS.includes(extension)) {
        message.error(`不支持的文件格式: ${file.name}`);
        return false;
      }
      const isLt200M = file.size / 1024 / 1024 < 200;
      if (!isLt200M) {
        message.error('文件大小不能超过200MB!');
        return false;
      }
      return true;
    },
    onChange(info) {
      const { status } = info.file;
      if (status === 'done') {
        message.success(`${info.file.name} 上传成功`);
      } else if (status === 'error') {
        message.error(`${info.file.name} 上传失败`);
      }
    },
    onDrop(e) {
      console.log('Dropped files', e.dataTransfer.files);
    },
  };

  return (
    <Dragger {...props}>
      <p className="ant-upload-drag-icon">
        <InboxOutlined />
      </p>
      <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
      <p className="ant-upload-hint">
        支持 PDF、Markdown、TXT、Word、Excel 格式
      </p>
    </Dragger>
  );
};

export default FileUpload;
