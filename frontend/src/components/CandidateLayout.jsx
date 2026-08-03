import { useEffect, useState } from 'react';
import { Badge } from 'antd';
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
  ApartmentOutlined,
  SafetyCertificateOutlined,
  QuestionCircleOutlined,
  CompassOutlined,
} from '@ant-design/icons';
import api from '../api';
import AppLayout from './AppLayout';

const BASE_MENU = [
  { key: '/candidate/dashboard', icon: <DashboardOutlined />, label: '首页' },
  {
    key: 'target-job',
    icon: <SearchOutlined />,
    label: '找岗位',
    children: [
      { key: '/candidate/jobs', icon: <UnorderedListOutlined />, label: '岗位推荐' },
      { key: '/candidate/browse-jobs', icon: <SearchOutlined />, label: '搜索全部岗位' },
    ],
  },
  {
    key: 'resume-workbench',
    icon: <FileTextOutlined />,
    label: '优化简历',
    children: [
      { key: '/candidate/advisor', icon: <CompassOutlined />, label: '按岗位优化' },
      { key: '/candidate/my-resumes', icon: <FileTextOutlined />, label: '我的简历' },
      { key: '/candidate/upload-resume', icon: <UploadOutlined />, label: '上传简历' },
    ],
  },
  { key: '/candidate/interview', icon: <MessageOutlined />, label: 'AI 面试' },
  {
    key: 'application-progress',
    icon: <FileSearchOutlined />,
    label: '投递进度',
    children: [
      { key: '/candidate/applied-jobs', icon: <FileSearchOutlined />, label: '投递记录', badgeKey: 'clarification' },
      { key: '/candidate/invitations', icon: <MailOutlined />, label: '面试邀请' },
    ],
  },
  {
    key: 'more',
    icon: <ApartmentOutlined />,
    label: '更多',
    children: [
      { key: '/candidate/career-passport', icon: <ApartmentOutlined />, label: '我的经历与能力' },
      { key: '/candidate/evidence-vault', icon: <SafetyCertificateOutlined />, label: '补充材料（可选）' },
      { key: '/candidate/analytics', icon: <BarChartOutlined />, label: '市场参考' },
      { key: '/candidate/help', icon: <QuestionCircleOutlined />, label: '帮助' },
    ],
  },
];

const mapMenu = (items, pendingClarifications) => items.map(({ badgeKey, ...item }) => {
  const next = item.children
    ? { ...item, children: mapMenu(item.children, pendingClarifications) }
    : item;
  if (badgeKey === 'clarification' && pendingClarifications > 0) {
    return {
      ...next,
      label: (
        <Badge count={pendingClarifications} size="small" offset={[8, 0]}>
          <span>{item.label}</span>
        </Badge>
      ),
    };
  }
  return next;
});

export default function CandidateLayout() {
  const [pendingClarifications, setPendingClarifications] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await api.get('/applications/mine/clarification-summary');
        if (!cancelled) {
          setPendingClarifications(res.data?.pending_clarification_count || 0);
        }
      } catch {
        if (!cancelled) setPendingClarifications(0);
      }
    };
    load();
    const onUpdate = () => load();
    window.addEventListener('clarification-updated', onUpdate);
    // 与雇主侧对称：30s 轮询，降低消息断裂感
    const timer = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(timer);
      window.removeEventListener('clarification-updated', onUpdate);
    };
  }, []);

  const menuItems = mapMenu(BASE_MENU, pendingClarifications);

  return (
    <AppLayout
      brandTitle="快连 QLink"
      brandSubtitle="求职者中心"
      menuItems={menuItems}
      role="candidate"
    />
  );
}
