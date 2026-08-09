import {
  Alert, List, Space, Tag, Typography,
} from 'antd';
import { isEnglishDemoMode } from '../utils/demoMode';

const { Text } = Typography;

const hasCjk = (value) => /[\u3400-\u9FFF]/.test(String(value || ''));

function safeEnglishLabel(value, fallback) {
  return value && !hasCjk(value) ? value : fallback;
}

function englishGuidanceAction(item, index, guidance) {
  const source = `${item.title || ''} ${item.why_for_you || ''} ${item.first_step || ''}`;
  const anchor = safeEnglishLabel(guidance?.anchor_experience || item.start_from, 'your selected experience');
  const target = safeEnglishLabel(guidance?.target_role, 'the target role');
  const profiles = [
    {
      matches: ['方法', '权衡', '约束', 'method', 'trade-off'],
      title: 'Explain Method and Trade-offs',
      why: `“${anchor}” shows what you did, but not yet why you chose the method, which constraints mattered, or how you made the trade-off.`,
      firstStep: 'Write down two options you considered, one real constraint, and why you made the final choice.',
      criteria: ['Option, constraint and decision are all clear', 'No invented numbers or unsupported facts'],
    },
    {
      matches: ['相关任务', '相关性', '岗位要求', 'relevance'],
      title: 'Surface the Most Relevant Task',
      why: `The connection between “${anchor}” and ${target} is not explicit enough. This is an evidence-framing gap—not proof that the capability is missing.`,
      firstStep: 'Select the real task that most closely matches one role requirement and move it to the first sentence of the experience.',
      criteria: ['One clear role-requirement-to-real-action link', 'Only existing facts are reordered'],
    },
    {
      matches: ['结果', '变化', 'outcome', 'impact'],
      title: 'Make the Outcome Verifiable',
      why: `“${anchor}” describes actions, but the resulting change, user or outcome is still unclear.`,
      firstStep: 'Add one true outcome: what you delivered, what problem changed, and who used or benefited from it.',
      criteria: ['At least one real outcome or before-and-after change', 'Unverified numbers remain blank'],
    },
    {
      matches: ['转向', '职业', 'career'],
      title: 'Clarify the Career Transition',
      why: `The bridge from your current experience to ${target} is not yet explicit or verifiable.`,
      firstStep: 'Write one transferable capability, one real experience that triggered the move, and one capability you are building now.',
      criteria: ['Past foundation, transition trigger and current action are clear', 'Intent is separated from demonstrated capability'],
    },
    {
      matches: ['作品', '产出', 'portfolio', 'sample'],
      title: 'Create a Verifiable Work Sample',
      why: `The current profile does not yet contain an output that demonstrates the required capability for ${target}.`,
      firstStep: 'Define one small deliverable—a repository, analysis, demo or case review—that can be completed within one week.',
      criteria: ['The output can be opened or demonstrated', 'Your contribution, inputs, method and limits are explicit'],
    },
    {
      matches: ['能力建设', '学习', 'skill'],
      title: 'Turn the Skill Gap into a Task',
      why: `The required capability is not yet supported by experience or evidence, so wording alone cannot close the gap.`,
      firstStep: 'Split the gap into one practice skill and one verifiable task with a deadline and output format.',
      criteria: ['One task directly related to the role requirement is completed', 'The completed work returns as a new claim and visible evidence'],
    },
    {
      matches: ['定位', '简介', 'role clarity'],
      title: 'Clarify Your Role Positioning',
      why: `The current summary does not make your connection to ${target} clear within a few seconds.`,
      firstStep: `Draft two lines using: target role + one core capability + the strongest evidence from “${anchor}”.`,
      criteria: ['Role, capability and experience evidence are all present', 'Basic contact details are excluded'],
    },
  ];
  const profile = profiles.find((candidate) => candidate.matches.some((keyword) => source.toLowerCase().includes(keyword.toLowerCase()))) || {
    title: 'Connect Existing Evidence',
    why: `QLink found potentially relevant material in “${anchor}”, but its role, scope or source is not yet clear enough to strengthen safely.`,
    firstStep: 'Confirm your role, time range, collaborators and a traceable source. A text description is enough.',
    criteria: ['The claim is user-confirmed and has enough context', 'At least one source is traceable without expanding permission'],
  };
  return { ...item, ...profile, priority: item.priority || index + 1 };
}

export default function PersonalizedGuidancePanel({
  guidance,
  fallback = [],
  title = '为你排序的下一步',
}) {
  const englishDemo = isEnglishDemoMode();
  const actions = guidance?.actions || [];
  const visibleActions = englishDemo
    ? (actions.length ? actions.map((item, index) => englishGuidanceAction(item, index, guidance)) : fallback)
    : (actions.length ? actions : fallback);
  const targetRole = safeEnglishLabel(guidance?.target_role, 'the target role');
  return (
    <div>
      <Text strong>{title}</Text>
      {guidance?.focus && (
        <Alert
          style={{ marginTop: 8 }}
          type="info"
          showIcon
          message={englishDemo
            ? `This round focuses only on the ${Math.max(actions.length, 1)} actions that most affect readiness for ${targetRole}—not a full resume rewrite.`
            : guidance.focus}
        />
      )}
      <List
        size="small"
        dataSource={visibleActions}
        renderItem={(item, index) => (
          <List.Item>
            {typeof item === 'string' ? (englishDemo ? 'Review the highest-impact evidence gap first.' : item) : (
              <List.Item.Meta
                title={(
                  <Space wrap>
                    <Tag color="blue">
                      {englishDemo ? 'Priority' : '优先级'} {item.priority || index + 1}
                    </Tag>
                    <Text strong>{englishDemo ? item.title : item.title}</Text>
                  </Space>
                )}
                description={(
                  <Space direction="vertical" size={3}>
                    <Text>{englishDemo ? item.why : item.why_for_you}</Text>
                    {item.start_from && (
                      <Text type="secondary">
                        {englishDemo
                          ? `Start from your “${safeEnglishLabel(item.start_from, 'selected experience')}” experience`
                          : `从你的「${item.start_from}」经历开始`}
                      </Text>
                    )}
                    {item.first_step && (
                      <Text>{englishDemo ? `First step: ${item.firstStep}` : `第一步：${item.first_step}`}</Text>
                    )}
                    {((englishDemo ? item.criteria : item.success_criteria) || []).length > 0 && (
                      <Text type="success">
                        {englishDemo ? 'Success criteria: ' : '完成标准：'}
                        {(englishDemo ? item.criteria : item.success_criteria).join(englishDemo ? '; ' : '；')}
                      </Text>
                    )}
                  </Space>
                )}
              />
            )}
          </List.Item>
        )}
      />
    </div>
  );
}
