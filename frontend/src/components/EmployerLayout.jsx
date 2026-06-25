import {
  DashboardOutlined,
  FileAddOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import AppLayout from './AppLayout';

const menuItems = [
  { key: '/employer/dashboard', icon: <DashboardOutlined />, label: '首页' },
  { key: '/employer/post-job', icon: <FileAddOutlined />, label: '发布岗位' },
  { key: '/employer/my-jobs', icon: <FolderOpenOutlined />, label: '我的岗位' },
  { key: '/employer/help', icon: <QuestionCircleOutlined />, label: '帮助' },
];

export default function EmployerLayout() {
  return (
    <AppLayout
      brandTitle="快连 QLink"
      brandSubtitle="招聘管理"
      menuItems={menuItems}
      role="employer"
    />
  );
}
