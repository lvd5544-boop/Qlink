import { useEffect, useState } from 'react';
import { Alert, Button, Card, Checkbox, Divider, Spin, Tag, Typography, message } from 'antd';
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
  create_growth_plan: '创建成长计划', view_alternative_roles: '查看替代岗位',
};

export default function ImprovementSimulationPanel({ resumeId, jobId, onAction }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState([]);
  const [growthPlan, setGrowthPlan] = useState(null);

  useEffect(() => {
    if (!resumeId || !jobId) return undefined;
    let active = true;
    const load = async () => {
      setLoading(true);
      try {
        const res = await api.get(`/resumes/${resumeId}/jobs/${jobId}/improvement-simulation`);
        if (active) { setData(res.data); setSelected(res.data.selected_strategy_ids || []); }
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
      setData(res.data);
      setSelected(res.data.selected_strategy_ids || []);
    } finally { setLoading(false); }
  };

  const record = async (eventType) => {
    try {
      await api.post(`/resumes/${resumeId}/jobs/${jobId}/improvement-simulation/events`, { event_type: eventType, strategy_ids: selected });
      message.success('已记录你的策略状态；简历不会被自动修改。');
    } catch { message.error('记录策略状态失败'); }
  };

  const handleAction = (option, issue) => {
    if (option.next_action === 'create_growth_plan') {
      setGrowthPlan({ title: option.title, why: option.why, horizon: option.time_horizon, cost: option.user_cost });
      void record('adopted');
      return;
    }
    onAction?.(option, issue);
  };

  if (!jobId) return null;
  const columns = ['现在可以优化', '需要补充证据', '需要真实提升', '硬门槛'];
  const grouped = Object.fromEntries(columns.map((name) => [name, []]));
  (data?.issues || []).forEach((issue) => issue.strategy_options.forEach((option) => {
    grouped[columnFor(issue, option)].push({ issue, option });
  }));
  return (
    <Card size="small" title="可提升空间模拟" style={{ marginTop: 12 }}>
      <Alert type="info" showIcon message="模型内模拟，不代表面试或录用承诺。" style={{ marginBottom: 8 }} />
      <Spin spinning={loading}>
        {!data ? <Text type="secondary">暂无可模拟的岗位匹配结果。</Text> : <>
          <Text>当前 {Number(data.current_score).toFixed(1)} 分；模拟后 {Number(data.potential_score).toFixed(1)} 分</Text>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 8, marginTop: 10 }}>
            {columns.map((column) => <Card key={column} size="small" title={column}>
              {grouped[column].length === 0 ? <Text type="secondary">暂无对应路径</Text> : grouped[column].map(({ issue, option }) => <div key={option.strategy_id} style={{ marginBottom: 9 }}>
                <Text strong>{option.title}</Text><br />
                <Text type="secondary">{issue.diagnosis}</Text><br />
                <Tag>{option.action_type}</Tag><Tag>{option.time_horizon}</Tag>
                <Checkbox checked={selected.includes(option.strategy_id)} onChange={(event) => setSelected((old) => (event.target.checked ? [...old, option.strategy_id] : old.filter((id) => id !== option.strategy_id)))}>纳入模拟</Checkbox>
                <Button size="small" type="link" onClick={() => handleAction(option, issue)}>{buttonText[option.next_action] || '查看建议'}</Button>
              </div>)}
            </Card>)}
          </div>
          <Divider style={{ margin: '10px 0' }} />
          <Button size="small" onClick={recalculate}>按所选策略重新模拟</Button>
          <Button size="small" style={{ marginLeft: 8 }} onClick={() => record('rejected')}>暂不采用</Button>
          <Button size="small" style={{ marginLeft: 8 }} onClick={() => record('adopted')}>标记已采纳</Button>
          <Button size="small" style={{ marginLeft: 8 }} onClick={() => record('completed')}>标记已完成</Button>
          {growthPlan && <Alert style={{ marginTop: 10 }} type="success" showIcon message={`成长计划：${growthPlan.title}`} description={`${growthPlan.why} 时间范围：${growthPlan.horizon}；投入：${growthPlan.cost}。`} />}
        </>}
      </Spin>
    </Card>
  );
}
