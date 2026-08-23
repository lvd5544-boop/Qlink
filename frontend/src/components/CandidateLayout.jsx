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
  RocketOutlined,
  ExperimentOutlined,
  LockOutlined,
} from '@ant-design/icons';
import api from '../api';
import AppLayout from './AppLayout';
import { isEnglishDemoMode } from '../utils/demoMode';

const buildBaseMenu = (englishDemo) => [
  { key: '/candidate/dashboard', icon: <DashboardOutlined />, label: englishDemo ? 'Home' : '首页' },
  {
    key: '/candidate/advisor',
    icon: <RocketOutlined />,
    label: (
      <span className="featured-menu-label">
        <span>{englishDemo ? 'AI Job Workflow' : 'AI 求职工作流'}</span>
        <span className="featured-menu-badge">{englishDemo ? 'CORE' : '主推'}</span>
      </span>
    ),
  },
  {
    key: '/candidate/pilot',
    icon: <ExperimentOutlined />,
    label: englishDemo ? 'Pilot & Feedback' : '试用引导与反馈',
  },
  {
    key: 'target-job',
    icon: <SearchOutlined />,
    label: englishDemo ? 'Find Roles' : '找岗位',
    children: [
      { key: '/candidate/jobs', icon: <UnorderedListOutlined />, label: englishDemo ? 'Recommended Roles' : '岗位推荐' },
      { key: '/candidate/browse-jobs', icon: <SearchOutlined />, label: englishDemo ? 'Browse All Roles' : '搜索全部岗位' },
    ],
  },
  {
    key: 'resume-workbench',
    icon: <FileTextOutlined />,
    label: englishDemo ? 'Resume' : '优化简历',
    children: [
      { key: '/candidate/my-resumes', icon: <FileTextOutlined />, label: englishDemo ? 'My Resumes' : '我的简历' },
      { key: '/candidate/upload-resume', icon: <UploadOutlined />, label: englishDemo ? 'Upload Resume' : '上传简历' },
    ],
  },
  { key: '/candidate/interview', icon: <MessageOutlined />, label: englishDemo ? 'AI Interview' : 'AI 面试' },
  {
    key: 'application-progress',
    icon: <FileSearchOutlined />,
    label: englishDemo ? 'Applications' : '投递进度',
    children: [
      { key: '/candidate/applied-jobs', icon: <FileSearchOutlined />, label: englishDemo ? 'Application History' : '投递记录', badgeKey: 'clarification' },
      { key: '/candidate/invitations', icon: <MailOutlined />, label: englishDemo ? 'Interview Invitations' : '面试邀请' },
    ],
  },
  {
    key: 'more',
    icon: <ApartmentOutlined />,
    label: englishDemo ? 'More' : '更多',
    children: [
      { key: '/candidate/career-passport', icon: <ApartmentOutlined />, label: englishDemo ? 'Career Passport' : '我的经历与能力' },
      { key: '/candidate/evidence-vault', icon: <SafetyCertificateOutlined />, label: englishDemo ? 'Evidence Vault' : '补充材料（可选）' },
      { key: '/candidate/analytics', icon: <BarChartOutlined />, label: englishDemo ? 'Market Signals' : '市场参考' },
      { key: '/candidate/help', icon: <QuestionCircleOutlined />, label: englishDemo ? 'Help' : '帮助' },
      { key: '/candidate/security', icon: <LockOutlined />, label: englishDemo ? 'Account Security' : '账号安全' },
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
  const englishDemo = isEnglishDemoMode();
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

  const menuItems = mapMenu(buildBaseMenu(englishDemo), pendingClarifications);

  return (
    <AppLayout
      brandTitle={englishDemo ? 'QLink' : '快连 QLink'}
      brandSubtitle={englishDemo ? 'Candidate Workspace' : '求职者中心'}
      menuItems={menuItems}
      role="candidate"
    />
  );
}
