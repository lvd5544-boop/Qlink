import { useEffect, useState } from 'react';
import {
  Alert, Button, Card, Checkbox, Divider, List, Spin, Tag, Typography, message,
} from 'antd';
import api from '../api';

const { Text } = Typography;

const columnFor = (issue, option) => {
  if (issue.issue_type === 'hard_constraint') return '硬门槛';
  if (option.can_apply_now) return '现在可以优化';
  if (option.requires_evidence || issue.issue_type === 'evidence_gap') return '需要补充证据';
  return '需要真实提升';
};

const buttonText = {
  preview_rewrite: '预览改写', answer_question: '回答问题', open_evidence_followup: '补充证据',
  open_claim_passport: '查看主张',
  create_growth_plan: '创建成长计划', view_alternative_roles: '查看替代岗位',
};

const statusText = {
  default: '推荐策略（尚未重新模拟）',
  strategies_selected: '已重新模拟，尚未标记',
  rejected: '暂不采用',
  adopted: '已采纳',
  completed: '已完成',
};

const actionTypeText = {
  evidence_completion: '补充真实证据',
  resume_reframing: '调整简历表达',
  experience_building: '积累项目经验',
  hard_constraint: '核对硬性要求',
  skill_learning: '学习并完成实践',
};

const horizonText = {
  immediate: '今天可以开始',
  short_term: '预计 1–2 周',
  medium_term: '预计 4–8 周',
  long_term: '预计 3 个月以上',
};

const costText = {
  low: '投入较少',
  medium: '每周约 3–5 小时',
  high: '需要持续投入',
};

const buildGrowthPlan = (option, issue) => {
  const skills = option.planned_skills || [];
  const subject = skills.length ? skills.join('、') : '这项岗位能力';
  return {
    title: option.title,
    why: option.why || issue.diagnosis,
    horizon: horizonText[option.time_horizon] || '请根据实际情况安排',
    cost: costText[option.user_cost] || '请根据实际情况安排投入',
    steps: [
      `确定一个与“${subject}”直接相关的小型练习或真实任务，并写清要解决的问题。`,
      '完成一项可以展示的产出，例如代码、方案、分析报告、作品链接或复盘文档。',
      '记录你做了什么、为什么这样做、遇到什么约束，以及最后得到什么结果。',
      '把产出加入履历证据库，重新运行岗位诊断；只有新增事实通过核对后才会计入当前分数。',
    ],
    done: `至少形成 1 项可查看的真实产出，并能说明你的个人贡献。系统不会仅凭“学完了”提高当前分数。`,
  };
};

const sameSelection = (left, right) => JSON.stringify([...(left || [])].sort())
  === JSON.stringify([...(right || [])].sort());

const selectedTitlesFor = (simulation, selectedIds) => {
  const selectedSet = new Set(selectedIds || []);
  return (simulation?.issues || [])
    .flatMap((issue) => issue.strategy_options || [])
    .filter((option) => selectedSet.has(option.strategy_id))
    .map((option) => option.title);
};

const strategyEffectTag = (strategyId, selectedIds, selectionDirty, effectMap) => {
  if (!selectedIds.includes(strategyId)) return null;
  if (selectionDirty) return <Tag color="orange">等待重新模拟</Tag>;
  const effect = effectMap[strategyId];
  if (!effect) return null;
  if (effect.status === 'changes_score_if_removed') {
    const delta = Number(effect.marginal_delta || 0);
    return <Tag color="green">本次计分 {delta >= 0 ? '+' : ''}{delta.toFixed(2)}</Tag>;
  }
  if (effect.status === 'needs_supported_evidence') {
    return <Tag color="gold">补证后才计分</Tag>;
  }
  return <Tag>与其他策略重叠或当前不影响计分</Tag>;
};

export default function ImprovementSimulationPanel({ resumeId, jobId, onAction }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState([]);
  const [appliedSelected, setAppliedSelected] = useState([]);
  const [strategyStatus, setStrategyStatus] = useState({ state: 'default' });
  const [simulationNotice, setSimulationNotice] = useState(null);
  const [growthPlan, setGrowthPlan] = useState(null);

  useEffect(() => {
    if (!resumeId || !jobId) return undefined;
    let active = true;
    const load = async () => {
      setLoading(true);
      try {
        const res = await api.get(`/resumes/${resumeId}/jobs/${jobId}/improvement-simulation`);
        if (active) {
          const ids = res.data.selected_strategy_ids || [];
          setData(res.data);
          setSelected(ids);
          setAppliedSelected(ids);
          setStrategyStatus(res.data.strategy_status || { state: 'default' });
          setSimulationNotice(null);
        }
      } catch {
        if (active) setData(null);
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [resumeId, jobId]);

  const recalculate = async () => {
    setLoading(true);
    try {
      const previousScore = Number(data?.potential_score || 0);
      const res = await api.post(`/resumes/${resumeId}/jobs/${jobId}/improvement-simulation`, { strategy_ids: selected });
      const ids = res.data.selected_strategy_ids || [];
      const nextScore = Number(res.data.potential_score || 0);
      const scoreChanged = Math.abs(nextScore - previousScore) >= 0.005;
      setData(res.data);
      setSelected(ids);
      setAppliedSelected(ids);
      setStrategyStatus(res.data.strategy_status || { state: 'strategies_selected' });
      setSimulationNotice({
        type: scoreChanged ? 'success' : 'info',
        message: `已按 ${ids.length} 项策略完成重新模拟`,
        description: scoreChanged
          ? `模拟后分数由 ${previousScore.toFixed(2)} 更新为 ${nextScore.toFixed(2)}。`
          : `模拟后分数仍为 ${nextScore.toFixed(2)}。策略组合已经更新；本次调整与其他已选策略效果重叠，或尚无可用于计分的补充证据。`,
      });
      message.success('重新模拟完成，策略选择已保存');
    } catch {
      message.error('重新模拟失败，请稍后重试');
    } finally { setLoading(false); }
  };

  const record = async (eventType) => {
    try {
      const res = await api.post(`/resumes/${resumeId}/jobs/${jobId}/improvement-simulation/events`, { event_type: eventType, strategy_ids: selected });
      const nextStatus = res.data.strategy_status || { state: eventType };
      const ids = res.data.selected_strategy_ids || selected;
      setData(res.data);
      setSelected(ids);
      setStrategyStatus(nextStatus);
      setAppliedSelected(ids);
      const titles = selectedTitlesFor(res.data, ids);
      setSimulationNotice({
        type: 'success',
        message: `当前策略状态：${statusText[eventType]}`,
        description: `已记录 ${ids.length} 项策略${titles.length ? `：${titles.join('、')}` : ''}；简历内容不会被自动修改。`,
      });
      message.success(`已记录为“${statusText[eventType]}”；简历不会被自动修改。`);
    } catch { message.error('记录策略状态失败'); }
  };

  const handleAction = (option, issue) => {
    if (option.next_action === 'create_growth_plan') {
      setGrowthPlan(buildGrowthPlan(option, issue));
      void record('adopted');
      return;
    }
    if (onAction) {
      onAction(option, issue);
    } else {
      message.info('请进入履历主张区域继续处理');
    }
  };

  if (!jobId) return null;
  const columns = ['现在可以优化', '需要补充证据', '需要真实提升', '硬门槛'];
  const grouped = Object.fromEntries(columns.map((name) => [name, []]));
  (data?.issues || []).forEach((issue) => issue.strategy_options.forEach((option) => {
    grouped[columnFor(issue, option)].push({ issue, option });
  }));
  const selectionDirty = !sameSelection(selected, appliedSelected);
  const effectMap = Object.fromEntries(
    (data?.selection_effects || []).map((effect) => [effect.strategy_id, effect]),
  );
  const selectedTitles = selectedTitlesFor(data, selected);
  return (
    <Card size="small" title="可提升空间模拟" style={{ marginTop: 12 }}>
      <Alert type="info" showIcon message="模型内模拟，不代表面试或录用承诺。" style={{ marginBottom: 8 }} />
      <Spin spinning={loading}>
        {!data ? <Text type="secondary">暂无可模拟的岗位匹配结果。</Text> : <>
          <div>
            <Text>
              当前 {Number(data.current_score).toFixed(2)} 分；模拟后 {Number(data.potential_score).toFixed(2)} 分
              （{Number(data.potential_delta) >= 0 ? '+' : ''}{Number(data.potential_delta).toFixed(2)}）
            </Text>
            <Tag color="blue" style={{ marginLeft: 8 }}>已纳入 {selected.length} 项</Tag>
            <Tag color={selectionDirty ? 'orange' : 'green'}>
              {selectionDirty ? '选择已更改，等待重新模拟' : (statusText[strategyStatus.state] || '状态已记录')}
            </Tag>
            {!selectionDirty && strategyStatus.state !== 'default' && selectedTitles.length > 0 && (
              <div><Text type="secondary">当前策略组合：{selectedTitles.join('、')}</Text></div>
            )}
          </div>
          {simulationNotice && (
            <Alert
              showIcon
              type={simulationNotice.type}
              message={simulationNotice.message}
              description={simulationNotice.description}
              style={{ marginTop: 10 }}
            />
          )}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 8, marginTop: 10 }}>
            {columns.map((column) => <Card key={column} size="small" title={column}>
              {grouped[column].length === 0 ? <Text type="secondary">暂无对应路径</Text> : grouped[column].map(({ issue, option }) => <div key={option.strategy_id} style={{ marginBottom: 9 }}>
                <Text strong>{option.title}</Text><br />
                <Text type="secondary">{issue.diagnosis}</Text><br />
                <Tag>{actionTypeText[option.action_type] || '改进行动'}</Tag>
                <Tag>{horizonText[option.time_horizon] || '时间待安排'}</Tag>
                <Checkbox checked={selected.includes(option.strategy_id)} onChange={(event) => setSelected((old) => (event.target.checked ? [...old, option.strategy_id] : old.filter((id) => id !== option.strategy_id)))}>纳入模拟</Checkbox>
                <Button size="small" type="link" onClick={() => handleAction(option, issue)}>{buttonText[option.next_action] || '查看建议'}</Button>
                {strategyEffectTag(option.strategy_id, selected, selectionDirty, effectMap)}
              </div>)}
            </Card>)}
          </div>
          <Divider style={{ margin: '10px 0' }} />
          <Button size="small" type={selectionDirty ? 'primary' : 'default'} onClick={recalculate}>
            按所选策略重新模拟（{selected.length} 项）
          </Button>
          <Button size="small" style={{ marginLeft: 8 }} onClick={() => record('rejected')}>暂不采用</Button>
          <Button size="small" style={{ marginLeft: 8 }} onClick={() => record('adopted')}>标记已采纳</Button>
          <Button size="small" style={{ marginLeft: 8 }} onClick={() => record('completed')}>标记已完成</Button>
          {growthPlan && (
            <Card size="small" title={`我的成长计划：${growthPlan.title}`} style={{ marginTop: 10 }}>
              <Text>{growthPlan.why}</Text>
              <div style={{ marginTop: 8 }}>
                <Tag color="blue">{growthPlan.horizon}</Tag>
                <Tag>{growthPlan.cost}</Tag>
              </div>
              <Divider style={{ margin: '10px 0' }} />
              <Text strong>按这个顺序完成</Text>
              <List
                size="small"
                dataSource={growthPlan.steps}
                renderItem={(step, index) => <List.Item>{index + 1}. {step}</List.Item>}
              />
              <Alert
                type="info"
                showIcon
                message="什么情况下算完成"
                description={growthPlan.done}
              />
            </Card>
          )}
        </>}
      </Spin>
    </Card>
  );
}
