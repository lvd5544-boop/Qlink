import {
  Button, Card, Col, Empty, Row, Space, Tag, Typography,
} from 'antd';
import { isEnglishDemoMode } from '../utils/demoMode';

const { Paragraph, Text } = Typography;

const DIRECTION_META_ZH = [
  { key: 'current', title: '当前方向', color: 'green', description: '优先选择与你当前目标或已有技能最接近的岗位。' },
  { key: 'adjacent', title: '相邻方向', color: 'blue', description: '复用已有经历，同时需要补充少量岗位化证据。' },
  { key: 'challenge', title: '挑战方向', color: 'orange', description: '跨度更大，需要先完成能力建设或作品任务。' },
];

const DIRECTION_META_EN = [
  { key: 'current', title: 'Current Direction', color: 'green', description: 'Closest to your current goal or demonstrated skills.' },
  { key: 'adjacent', title: 'Adjacent Direction', color: 'blue', description: 'Reuses your experience with a small evidence gap.' },
  { key: 'challenge', title: 'Stretch Direction', color: 'orange', description: 'Requires new capability evidence or a portfolio task.' },
];

function relationOf(job) {
  return job?.score_breakdown?.preference_policy?.role_relation || 'different';
}

function uniqueJobs(matchedJobs, availableJobs) {
  const rows = [];
  const seen = new Set();
  for (const job of [...matchedJobs, ...availableJobs]) {
    const id = String(job.job_id || job.id || '');
    if (!id || seen.has(id)) continue;
    seen.add(id);
    rows.push({ ...job, directionJobId: id, directionTitle: job.job_title || job.title || '未命名岗位' });
  }
  return rows;
}

function buildCareerDirections(matchedJobs = [], availableJobs = []) {
  const rows = uniqueJobs(matchedJobs, availableJobs);
  const exact = rows.filter((job) => relationOf(job) === 'exact');
  const adjacent = rows.filter((job) => relationOf(job) === 'adjacent');
  const challenge = rows
    .filter((job) => relationOf(job) === 'different')
    .sort((left, right) => Number(right.improvement_delta || 0) - Number(left.improvement_delta || 0));
  const used = new Set();
  const take = (preferred) => {
    const row = preferred.find((job) => !used.has(job.directionJobId));
    if (row) used.add(row.directionJobId);
    return row || null;
  };
  return { current: take(exact), adjacent: take(adjacent), challenge: take(challenge) };
}

export default function CareerPathExplorer({ matchedJobs = [], availableJobs = [], onSelect }) {
  const englishDemo = isEnglishDemoMode();
  const directions = buildCareerDirections(matchedJobs, availableJobs);
  const directionMeta = englishDemo ? DIRECTION_META_EN : DIRECTION_META_ZH;

  return (
    <Card
      size="small"
      title={englishDemo ? 'No target role yet? Compare three directions.' : '还没有目标岗位？先比较三个方向'}
      style={{ marginBottom: 16 }}
    >
      <Paragraph type="secondary">
        {englishDemo
          ? 'AI reasons from your background to propose directions. Choose one to reveal role requirements, evidence gaps and the next best action.'
          : '三个方向是探索入口，不是对能力的结论；选择示例岗位后，会进入同一套岗位要求与证据准备流程。'}
      </Paragraph>
      <Row gutter={[12, 12]}>
        {directionMeta.map((meta) => {
          const job = directions[meta.key];
          const displayTitle = englishDemo && /[\u3400-\u9FFF]/.test(job?.directionTitle || '')
            ? `Example Role · ${meta.title.replace(' Direction', '')}`
            : job?.directionTitle;
          return (
            <Col xs={24} md={8} key={meta.key}>
              <Card size="small" data-testid={`career-direction-${meta.key}`} style={{ height: '100%' }}>
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Tag color={meta.color}>{meta.title}</Tag>
                  <Text>{meta.description}</Text>
                  {job ? (
                    <>
                      <Text strong>{displayTitle}</Text>
                      <Button block onClick={() => onSelect?.(job.directionJobId)}>
                        {englishDemo ? 'Explore this role' : '选择这个示例岗位'}
                      </Button>
                    </>
                  ) : (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={englishDemo ? 'No example role available. Refine your preferences.' : '暂无合适示例岗位，可先调整偏好'}
                    />
                  )}
                </Space>
              </Card>
            </Col>
          );
        })}
      </Row>
    </Card>
  );
}
