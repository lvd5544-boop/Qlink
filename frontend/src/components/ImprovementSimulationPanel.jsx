import { useEffect, useState } from 'react';
import {
  Alert, Button, Card, Checkbox, Divider, List, Spin, Tag, Typography, message,
} from 'antd';
import api from '../api';

const { Text } = Typography;

const columnFor = (issue, option) => {
  if (issue.issue_type === 'hard_constraint') return '需要先确认的要求';
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
  default: '推荐行动（尚未更新）',
  strategies_selected: '方案已更新，尚未标记',
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
      '把产出加入履历证据库，重新查看岗位准备建议；只有你确认的新增事实才会被使用。',
    ],
    done: `至少形成 1 项可查看的真实产出，并能说明你的个人贡献。只完成课程但没有实践产出，还不能说明你已经掌握。`,
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
  if (selectionDirty) return <Tag color="orange">等待更新</Tag>;
  const effect = effectMap[strategyId];
  if (!effect) return null;
  if (effect.status === 'changes_score_if_removed') {
    return <Tag color="green">会改变准备建议</Tag>;
  }
  if (effect.status === 'needs_supported_evidence') {
    return <Tag color="gold">先补充真实材料</Tag>;
  }
  return <Tag>与其他行动作用相近</Tag>;
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
      const res = await api.post(`/resumes/${resumeId}/jobs/${jobId}/improvement-simulation`, { strategy_ids: selected });
      const ids = res.data.selected_strategy_ids || [];
      setData(res.data);
      setSelected(ids);
      setAppliedSelected(ids);
      setStrategyStatus(res.data.strategy_status || { state: 'strategies_selected' });
      setSimulationNotice({
        type: 'success',
        message: `已更新 ${ids.length} 项行动`,
        description: ids.length
          ? '新的准备顺序已经保存。需要真实材料的事项仍会保持待确认。'
          : '暂未选择行动，你可以先从现在能完成的一项开始。',
      });
      message.success('行动方案已更新');
    } catch {
      message.error('更新行动方案失败，请稍后重试');
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
  const columns = ['现在可以优化', '需要补充证据', '需要真实提升', '需要先确认的要求'];
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
    <Card size="small" title="下一步行动" className="editorial-action-card" style={{ marginTop: 12 }}>
      <Alert
        className="editorial-guidance-card editorial-guidance-card-compact"
        type="info"
        showIcon
        message="比较不同准备方式"
        description="选择你愿意采取的行动，系统会帮你整理顺序；这不是面试或录用预测。"
        style={{ marginBottom: 12 }}
      />
      <Spin spinning={loading}>
        {!data ? <Text type="secondary">暂无可模拟的岗位匹配结果。</Text> : <>
          <div>
            <Text>已选择 {selected.length} 项行动</Text>
            <Tag color={selectionDirty ? 'orange' : 'green'}>
              {selectionDirty ? '选择已更改，等待更新' : (statusText[strategyStatus.state] || '状态已记录')}
            </Tag>
            {!selectionDirty && strategyStatus.state !== 'default' && selectedTitles.length > 0 && (
              <div><Text type="secondary">当前行动：{selectedTitles.join('、')}</Text></div>
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
            更新行动方案（{selected.length} 项）
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
