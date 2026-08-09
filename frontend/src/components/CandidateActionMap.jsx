import {
  Alert, Button, Card, Empty, List, Space, Tag, Typography,
} from 'antd';
import { isEnglishDemoMode } from '../utils/demoMode';
import { groupIssuesByRouteState } from './requirementReadinessState';

const { Text } = Typography;

const GROUP_META = {
  ready: {
    title: '已有证据：可以直接使用',
    color: 'success',
    description: '这些建议已经关联到你提供的经历，可先用于忠实改写或申请表达。',
  },
  clarify: {
    title: '信息不完整：需要立即追问',
    color: 'processing',
    description: '存在相关线索，但角色、方法、范围、结果或证据仍不完整。',
  },
  develop: {
    title: '暂未具备：生成发展任务',
    color: 'warning',
    description: '这不是“你不会”的结论；先确认确实没有相关经历，再决定是否投入行动。',
  },
  constraint: {
    title: '现实约束：单独确认',
    color: 'error',
    description: '地点、学历、证书或工作方式等条件应与能力分开处理。',
  },
  unknown: {
    title: '无法判断：请求补充信息',
    color: 'default',
    description: '当前材料不足，不强行判断；可以补充经历、证据或直接询问岗位方。',
  },
};

const GROUP_META_EN = {
  ready: {
    title: 'Evidence ready: use it now',
    color: 'success',
    description: 'These actions are already supported by experience you provided.',
  },
  clarify: {
    title: 'Information incomplete: ask now',
    color: 'processing',
    description: 'A useful signal exists, but your role, method, scope, result or proof is incomplete.',
  },
  develop: {
    title: 'Evidence missing: create a task',
    color: 'warning',
    description: 'First confirm the gap, then generate evidence through one focused development task.',
  },
  constraint: {
    title: 'Real-world constraint: check separately',
    color: 'error',
    description: 'Location, degree, certification and work conditions should stay separate from capability.',
  },
  unknown: {
    title: 'Unknown: request more information',
    color: 'default',
    description: 'The current material is insufficient, so the system does not force a conclusion.',
  },
};

function recommendedStrategy(issue) {
  return (issue.strategies || []).find((item) => item.recommended)
    || issue.strategies?.[0]
    || null;
}

function englishIssueTitle(issue) {
  const titles = {
    hard_constraint: 'Confirm this real-world constraint',
    capability: 'Build evidence for this capability',
    expression: 'Clarify your role and contribution',
    evidence: 'Add verifiable evidence for this claim',
    consistency: 'Resolve this inconsistency',
    relevance: 'Connect this experience to the target role',
    differentiation: 'Show what makes this evidence distinctive',
    career_narrative: 'Clarify the career story behind this move',
  };
  return titles[issue.category] || 'Provide more information before deciding';
}

export default function CandidateActionMap({ diagnostic, onResolveIssue }) {
  const englishDemo = isEnglishDemoMode();
  const groupMeta = englishDemo ? GROUP_META_EN : GROUP_META;
  const grouped = groupIssuesByRouteState(diagnostic?.issues || []);
  const visibleGroups = Object.entries(groupMeta);

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Alert
        showIcon
        type="info"
        message={englishDemo ? 'Reason about the missing evidence—not just the missing skill' : '先处理能改变这次申请的事项'}
        description={englishDemo
          ? 'QLink separates evidence you can use, information to clarify, development tasks and real-world constraints.'
          : '这是岗位准备情况：系统只整理你已提供的事实和信息缺口；没有写出来不等于没有能力。'}
      />
      {visibleGroups.map(([key, meta]) => (
        <Card
          key={key}
          data-testid={`readiness-${key}`}
          size="small"
          title={(
            <Space wrap>
              <Tag color={meta.color}>{grouped[key].length}</Tag>
              <Text strong>{meta.title}</Text>
            </Space>
          )}
        >
          <Text type="secondary">{meta.description}</Text>
          {key === 'clarify' && grouped[key].length > 3 && (
            <Alert
              type="info"
              message={englishDemo
                ? `Answer the 3 highest-value questions first. Save the other ${grouped[key].length - 3} for later.`
                : `先回答最重要的 3 个问题，其余 ${grouped[key].length - 3} 项稍后处理`}
              style={{ marginTop: 8 }}
            />
          )}
          {grouped[key].length ? <List
            style={{ marginTop: 8 }}
            size="small"
            dataSource={key === 'clarify' ? grouped[key].slice(0, 3) : grouped[key]}
            renderItem={(issue) => {
              const strategy = recommendedStrategy(issue);
              return (
                <List.Item>
                  <List.Item.Meta
                    title={englishDemo ? englishIssueTitle(issue) : issue.diagnosis}
                    description={(
                      <Space direction="vertical" size={2}>
                        {(issue.claim_ids || []).length > 0 && (
                          <Text type="secondary">
                            {englishDemo ? `${issue.claim_ids.length} linked experience item(s)` : `已关联你的经历 ${issue.claim_ids.length} 条`}
                          </Text>
                        )}
                        {strategy?.title && (
                          <Text>
                            {englishDemo ? 'Next action: generate the missing evidence' : `建议下一步：${strategy.title}`}
                          </Text>
                        )}
                        {strategy?.next_action && !englishDemo && <Text type="secondary">{strategy.next_action}</Text>}
                        {key === 'clarify' && (
                          <Space direction="vertical" size={2}>
                            <Button size="small" onClick={() => onResolveIssue?.(issue)}>
                              {englishDemo ? 'Answer and add evidence' : '回答并补充这条经历或证据'}
                            </Button>
                            <Text type="secondary">
                              {englishDemo ? 'Your answer becomes new evidence and updates readiness.' : '补充后重新分析会更新证据和准备状态。'}
                            </Text>
                          </Space>
                        )}
                      </Space>
                    )}
                  />
                </List.Item>
              );
            }}
          /> : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={englishDemo ? 'No item in this category' : '当前没有这一类事项'}
              style={{ marginTop: 8 }}
            />
          )}
        </Card>
      ))}
    </Space>
  );
}
