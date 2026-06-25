import {
  Button, Col, Divider, Input, Row, Select,
} from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';

const { TextArea } = Input;
const { Option } = Select;

const SCHOOL_TIER_OPTIONS = ['985', '211', '双一流', '其他'];

export default function ResumeEditForm({
  data,
  onChange,
  onSave,
  saving = false,
}) {
  const updateField = (field, value) => {
    onChange({ ...data, [field]: value });
  };

  const updateSkill = (index, field, value) => {
    const skills = [...(data.skills || [])];
    skills[index] = { ...skills[index], [field]: value };
    onChange({ ...data, skills });
  };

  const addSkill = () => {
    onChange({
      ...data,
      skills: [...(data.skills || []), { name: '', level: 'intermediate' }],
    });
  };

  const removeSkill = (index) => {
    onChange({ ...data, skills: (data.skills || []).filter((_, i) => i !== index) });
  };

  const updateWorkExp = (index, field, value) => {
    const work = [...(data.work_experience || [])];
    work[index] = { ...work[index], [field]: value };
    onChange({ ...data, work_experience: work });
  };

  const addWorkExp = () => {
    onChange({
      ...data,
      work_experience: [
        ...(data.work_experience || []),
        { company: '', position: '', duration_years: 0, description: '' },
      ],
    });
  };

  const removeWorkExp = (index) => {
    onChange({
      ...data,
      work_experience: (data.work_experience || []).filter((_, i) => i !== index),
    });
  };

  return (
    <div style={{ fontSize: 13 }}>
      <h4 style={{ marginTop: 0 }}>编辑简历</h4>
      <Row gutter={[8, 8]}>
        <Col span={12}><label>姓名</label><Input size="small" value={data.name || ''} onChange={(e) => updateField('name', e.target.value)} /></Col>
        <Col span={12}><label>邮箱</label><Input size="small" value={data.email || ''} onChange={(e) => updateField('email', e.target.value)} /></Col>
        <Col span={12}><label>电话</label><Input size="small" value={data.phone || ''} onChange={(e) => updateField('phone', e.target.value)} /></Col>
        <Col span={12}><label>期望职位</label><Input size="small" value={data.expected_job_title || ''} onChange={(e) => updateField('expected_job_title', e.target.value)} /></Col>
        <Col span={12}><label>期望薪资</label><Input size="small" value={data.expected_salary || ''} onChange={(e) => updateField('expected_salary', e.target.value)} /></Col>
        <Col span={12}><label>期望地点</label><Input size="small" value={data.location_preference || ''} onChange={(e) => updateField('location_preference', e.target.value)} /></Col>
      </Row>

      <label style={{ display: 'block', marginTop: 8 }}>个人简介</label>
      <TextArea rows={2} size="small" value={data.summary || ''} onChange={(e) => updateField('summary', e.target.value)} />

      <Divider style={{ margin: '12px 0' }} />
      <h4 style={{ margin: '0 0 8px' }}>教育背景</h4>
      <Row gutter={[8, 8]}>
        <Col span={12}><label>院校</label><Input size="small" value={data.school || ''} onChange={(e) => updateField('school', e.target.value)} placeholder="如：复旦大学" /></Col>
        <Col span={12}><label>学历</label><Input size="small" value={data.education || ''} onChange={(e) => updateField('education', e.target.value)} placeholder="如：本科" /></Col>
        <Col span={12}><label>学位</label><Input size="small" value={data.degree || ''} onChange={(e) => updateField('degree', e.target.value)} placeholder="如：学士" /></Col>
        <Col span={12}>
          <label>院校层次</label>
          <Select
            size="small"
            style={{ width: '100%' }}
            allowClear
            placeholder="选择层次"
            value={data.school_tier || undefined}
            onChange={(v) => updateField('school_tier', v)}
            options={SCHOOL_TIER_OPTIONS.map((t) => ({ value: t, label: t }))}
          />
        </Col>
      </Row>

      <Divider style={{ margin: '12px 0' }} />
      <h4 style={{ margin: '0 0 8px' }}>技能</h4>
      {(data.skills || []).map((skill, idx) => (
        <Row gutter={4} key={idx} align="middle" style={{ marginBottom: 4 }}>
          <Col span={10}><Input size="small" placeholder="技能" value={skill.name} onChange={(e) => updateSkill(idx, 'name', e.target.value)} /></Col>
          <Col span={10}>
            <Select size="small" value={skill.level} onChange={(v) => updateSkill(idx, 'level', v)} style={{ width: '100%' }}>
              <Option value="beginner">初级</Option>
              <Option value="intermediate">中级</Option>
              <Option value="advanced">高级</Option>
              <Option value="expert">专家</Option>
            </Select>
          </Col>
          <Col span={4}><Button type="text" size="small" danger icon={<MinusCircleOutlined />} onClick={() => removeSkill(idx)} /></Col>
        </Row>
      ))}
      <Button type="dashed" size="small" icon={<PlusOutlined />} onClick={addSkill} block>添加技能</Button>

      <label style={{ display: 'block', marginTop: 10 }}>软实力（逗号分隔）</label>
      <Input
        size="small"
        value={(data.soft_skills || []).join(', ')}
        onChange={(e) => updateField('soft_skills', e.target.value.split(/[,，]/).map((s) => s.trim()).filter(Boolean))}
        placeholder="沟通协作, 项目管理, 跨部门推动"
      />

      <Divider style={{ margin: '12px 0' }} />
      <h4 style={{ margin: '0 0 8px' }}>工作经历</h4>
      {(data.work_experience || []).map((exp, idx) => (
        <div key={idx} style={{ marginBottom: 10, padding: 8, border: '1px solid #eee', borderRadius: 6 }}>
          <Row justify="space-between">
            <strong>经历 {idx + 1}</strong>
            <Button type="text" size="small" danger icon={<MinusCircleOutlined />} onClick={() => removeWorkExp(idx)} />
          </Row>
          <Row gutter={4} style={{ marginTop: 4 }}>
            <Col span={8}><Input size="small" placeholder="公司" value={exp.company} onChange={(e) => updateWorkExp(idx, 'company', e.target.value)} /></Col>
            <Col span={8}><Input size="small" placeholder="职位" value={exp.position} onChange={(e) => updateWorkExp(idx, 'position', e.target.value)} /></Col>
            <Col span={8}><Input size="small" type="number" placeholder="年限" value={exp.duration_years} onChange={(e) => updateWorkExp(idx, 'duration_years', parseFloat(e.target.value) || 0)} /></Col>
          </Row>
          <TextArea rows={2} size="small" style={{ marginTop: 4 }} placeholder="职责与成果" value={exp.description} onChange={(e) => updateWorkExp(idx, 'description', e.target.value)} />
        </div>
      ))}
      <Button type="dashed" size="small" icon={<PlusOutlined />} onClick={addWorkExp} block style={{ marginBottom: 12 }}>
        添加工作经历
      </Button>

      <Divider style={{ margin: '12px 0' }} />
      <h4 style={{ margin: '0 0 8px' }}>项目经历</h4>
      {(data.projects || []).map((proj, idx) => (
        <div key={idx} style={{ marginBottom: 10, padding: 8, border: '1px solid #e8f4ff', borderRadius: 6, background: '#f8fbff' }}>
          <Row justify="space-between">
            <strong>项目 {idx + 1}</strong>
            <Button type="text" size="small" danger icon={<MinusCircleOutlined />} onClick={() => {
              onChange({ ...data, projects: (data.projects || []).filter((_, i) => i !== idx) });
            }} />
          </Row>
          <Row gutter={4} style={{ marginTop: 4 }}>
            <Col span={12}>
              <Input
                size="small"
                placeholder="项目名称"
                value={proj.name}
                onChange={(e) => {
                  const projects = [...(data.projects || [])];
                  projects[idx] = { ...projects[idx], name: e.target.value };
                  onChange({ ...data, projects });
                }}
              />
            </Col>
            <Col span={12}>
              <Input
                size="small"
                placeholder="担任角色"
                value={proj.role}
                onChange={(e) => {
                  const projects = [...(data.projects || [])];
                  projects[idx] = { ...projects[idx], role: e.target.value };
                  onChange({ ...data, projects });
                }}
              />
            </Col>
            <Col span={24} style={{ marginTop: 4 }}>
              <Input
                size="small"
                placeholder="时间，如 2023.01-2023.06"
                value={proj.duration}
                onChange={(e) => {
                  const projects = [...(data.projects || [])];
                  projects[idx] = { ...projects[idx], duration: e.target.value };
                  onChange({ ...data, projects });
                }}
              />
            </Col>
          </Row>
          <TextArea
            rows={2}
            size="small"
            style={{ marginTop: 4 }}
            placeholder="项目描述与量化成果"
            value={proj.description}
            onChange={(e) => {
              const projects = [...(data.projects || [])];
              projects[idx] = { ...projects[idx], description: e.target.value };
              onChange({ ...data, projects });
            }}
          />
        </div>
      ))}
      <Button
        type="dashed"
        size="small"
        icon={<PlusOutlined />}
        onClick={() => onChange({
          ...data,
          projects: [...(data.projects || []), { name: '', role: '', duration: '', description: '' }],
        })}
        block
        style={{ marginBottom: 12 }}
      >
        添加项目经历
      </Button>

      <Button type="primary" block onClick={onSave} loading={saving}>
        保存并更新分数
      </Button>
    </div>
  );
}
