import {
  DashboardOutlined,
  UploadOutlined,
  MessageOutlined,
  UnorderedListOutlined,
  FileTextOutlined,
  SearchOutlined,
  MailOutlined,
  BarChartOutlined,
  FileSearchOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import AppLayout from './AppLayout';

const menuItems = [
  { key: '/candidate/dashboard', icon: <DashboardOutlined />, label: '首页' },
  { key: '/candidate/browse-jobs', icon: <SearchOutlined />, label: '浏览岗位' },
  { key: '/candidate/applied-jobs', icon: <FileSearchOutlined />, label: '已申请岗位' },
  { key: '/candidate/upload-resume', icon: <UploadOutlined />, label: '上传简历' },
  { key: '/candidate/my-resumes', icon: <FileTextOutlined />, label: '我的简历' },
  { key: '/candidate/interview', icon: <MessageOutlined />, label: '虚拟面试' },
  { key: '/candidate/jobs', icon: <UnorderedListOutlined />, label: '岗位推荐' },
  { key: '/candidate/invitations', icon: <MailOutlined />, label: '面试邀请' },
  { key: '/candidate/analytics', icon: <BarChartOutlined />, label: '数据分析' },
  { key: '/candidate/help', icon: <QuestionCircleOutlined />, label: '帮助' },
];

export default function CandidateLayout() {
  return (
    <AppLayout
      brandTitle="快连 QLink"
      brandSubtitle="求职者中心"
      menuItems={menuItems}
      role="candidate"
    />
  );
}
