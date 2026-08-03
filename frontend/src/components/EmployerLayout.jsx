import { useEffect, useState } from 'react';
import { Badge } from 'antd';
import {
  DashboardOutlined,
  FileAddOutlined,
  FolderOpenOutlined,
  SolutionOutlined,
  FilterOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import api from '../api';
import AppLayout from './AppLayout';

const BASE_MENU = [
  { key: '/employer/dashboard', icon: <DashboardOutlined />, label: '首页' },
  { key: '/employer/post-job', icon: <FileAddOutlined />, label: '发布岗位' },
  { key: '/employer/my-jobs', icon: <FolderOpenOutlined />, label: '我的岗位' },
  { key: '/employer/applications', icon: <SolutionOutlined />, label: '申请与审阅', badgeKey: 'inbox' },
  { key: '/employer/screening', icon: <FilterOutlined />, label: '批筛复核' },
  { key: '/employer/help', icon: <QuestionCircleOutlined />, label: '帮助' },
];

export default function EmployerLayout() {
  const [pendingReview, setPendingReview] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await api.get('/applications/employer/inbox-summary');
        if (!cancelled) {
          setPendingReview(res.data?.pending_review_count || 0);
        }
      } catch {
        if (!cancelled) setPendingReview(0);
      }
    };
    load();
    const onUpdate = () => load();
    window.addEventListener('employer-inbox-updated', onUpdate);
    const timer = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(timer);
      window.removeEventListener('employer-inbox-updated', onUpdate);
    };
  }, []);

  const menuItems = BASE_MENU.map(({ badgeKey, ...item }) => {
    if (badgeKey === 'inbox' && pendingReview > 0) {
      return {
        ...item,
        label: (
          <Badge count={pendingReview} size="small" offset={[8, 0]}>
            <span>{item.label}</span>
          </Badge>
        ),
      };
    }
    return item;
  });

  return (
    <AppLayout
      brandTitle="快连 QLink"
      brandSubtitle="招聘管理"
      menuItems={menuItems}
      role="employer"
    />
  );
}
