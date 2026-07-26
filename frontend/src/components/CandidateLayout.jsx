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
  QuestionCircleOutlined,
} from '@ant-design/icons';
import api from '../api';
import AppLayout from './AppLayout';

const BASE_MENU = [
  { key: '/candidate/dashboard', icon: <DashboardOutlined />, label: '首页' },
  { key: '/candidate/browse-jobs', icon: <SearchOutlined />, label: '浏览岗位' },
  { key: '/candidate/applied-jobs', icon: <FileSearchOutlined />, label: '已申请岗位', badgeKey: 'clarification' },
  { key: '/candidate/upload-resume', icon: <UploadOutlined />, label: '上传简历' },
  { key: '/candidate/my-resumes', icon: <FileTextOutlined />, label: '我的简历' },
  { key: '/candidate/interview', icon: <MessageOutlined />, label: '虚拟面试' },
  { key: '/candidate/jobs', icon: <UnorderedListOutlined />, label: '岗位推荐' },
  { key: '/candidate/invitations', icon: <MailOutlined />, label: '面试邀请' },
  { key: '/candidate/analytics', icon: <BarChartOutlined />, label: '数据分析' },
  { key: '/candidate/help', icon: <QuestionCircleOutlined />, label: '帮助' },
];

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

  const menuItems = BASE_MENU.map(({ badgeKey, ...item }) => {
    if (badgeKey === 'clarification' && pendingClarifications > 0) {
      return {
        ...item,
        label: (
          <Badge count={pendingClarifications} size="small" offset={[8, 0]}>
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
      brandSubtitle="求职者中心"
      menuItems={menuItems}
      role="candidate"
    />
  );
}
