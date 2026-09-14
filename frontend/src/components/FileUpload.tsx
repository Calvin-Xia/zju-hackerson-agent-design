import React from 'react';
import { InboxOutlined } from '@ant-design/icons';
import { Upload, message } from 'antd';
import type { UploadProps } from 'antd';
import { uploadTextbook } from '../api/client';
import { FILES_CHANGED_EVENT } from './FileList';

const { Dragger } = Upload;

const ALLOWED_EXTENSIONS = ['pdf', 'md', 'txt', 'docx', 'xlsx'];
const MAX_SIZE_MB = 200;

const FileUpload: React.FC = () => {
  const props: UploadProps = {
    name: 'file',
    multiple: true,
    showUploadList: { showRemoveIcon: false },
    accept: ALLOWED_EXTENSIONS.map((ext) => `.${ext}`).join(','),
    beforeUpload: (file) => {
      const extension = file.name.split('.').pop()?.toLowerCase();
      if (!extension || !ALLOWED_EXTENSIONS.includes(extension)) {
        message.error(`不支持的文件格式: ${file.name}`);
        return Upload.LIST_IGNORE;
      }
      if (file.size / 1024 / 1024 >= MAX_SIZE_MB) {
        message.error(`文件大小不能超过 ${MAX_SIZE_MB}MB: ${file.name}`);
        return Upload.LIST_IGNORE;
      }
      return true;
    },
    // 用自有 API 客户端上传，保证错误提示与后端 detail 一致
    customRequest: async ({ file, onSuccess, onError }) => {
      try {
        const result = await uploadTextbook(file as File);
        message.success(`${(file as File).name} 上传成功，已开始解析`);
        window.dispatchEvent(new Event(FILES_CHANGED_EVENT));
        onSuccess?.(result);
      } catch (err) {
        message.error(err instanceof Error ? err.message : `${(file as File).name} 上传失败`);
        onError?.(err as Error);
      }
    },
  };

  return (
    <Dragger {...props}>
      <p className="ant-upload-drag-icon">
        <InboxOutlined />
      </p>
      <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
      <p className="ant-upload-hint">支持 PDF、Markdown、TXT、Word、Excel 格式，单文件不超过 200MB</p>
    </Dragger>
  );
};

export default FileUpload;
