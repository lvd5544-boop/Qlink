import { useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Divider,
  Form,
  Input,
  InputNumber,
  List,
  Row,
  Segmented,
  Space,
  Tag,
  Typography,
} from 'antd';
import {
  buildRequirementChoices,
  formToJob,
  jobToForm,
} from './jobProfileEditorUtils';

const { Text } = Typography;

export default function JobProfileEditor({
  initialValue,
  saving,
  onSave,
  submitText = '确认要求并发布岗位',
  initialRequirementDecisions = [],
}) {
  const [form] = Form.useForm();
  const initialFormValue = jobToForm(initialValue);
  const [requirementChoices, setRequirementChoices] = useState(() => (
    buildRequirementChoices(initialFormValue, initialRequirementDecisions)
  ));

  const updateClassification = (key, classification) => {
    setRequirementChoices((rows) => rows.map((item) => (
      item.key === key ? { ...item, classification } : item
    )));
  };

  return (
    <Card
      type="inner"
      title="确认岗位并发布"
      style={{ marginTop: 20 }}
    >
      <Text type="secondary">
        检查岗位信息，并告诉系统哪些条件必须满足。完成后一次发布，无需再去其他页面配置。
      </Text>
      <Form
        form={form}
        layout="vertical"
        initialValues={initialFormValue}
        onValuesChange={(_, values) => {
          setRequirementChoices((current) => buildRequirementChoices(values, current));
        }}
        onFinish={(values) => onSave(formToJob(values, initialValue), requirementChoices)}
        style={{ marginTop: 16 }}
      >
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item name="title" label="岗位名称" rules={[{ required: true, message: '请填写岗位名称' }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item name="company_name" label="公司名称">
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} md={6}>
            <Form.Item name="location" label="工作地点"><Input /></Form.Item>
          </Col>
          <Col xs={24} md={6}>
            <Form.Item name="salary_range" label="薪资范围"><Input placeholder="如 20k-30k" /></Form.Item>
          </Col>
          <Col xs={24} md={6}>
            <Form.Item name="experience_years" label="经验年限"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
          </Col>
          <Col xs={24} md={6}>
            <Form.Item name="education" label="学历"><Input /></Form.Item>
          </Col>
        </Row>
        <Form.Item name="responsibilities" label="岗位职责（每行一条）">
          <Input.TextArea rows={5} />
        </Form.Item>
        <Form.Item name="requirements" label="任职要求">
          <Input.TextArea rows={4} />
        </Form.Item>
        <Form.Item name="required_skills" label="专业技能（逗号分隔）">
          <Input placeholder="Python, FastAPI, PostgreSQL" />
        </Form.Item>
        <Collapse
          ghost
          items={[
            {
              key: 'optional-job-fields',
              label: '更多岗位信息（可选）',
              forceRender: true,
              children: (
                <>
                  <Row gutter={16}>
                    <Col xs={24} md={12}>
                      <Form.Item name="soft_skills" label="软技能（逗号分隔）"><Input /></Form.Item>
                    </Col>
                    <Col xs={24} md={12}>
                      <Form.Item name="education_requirement" label="学历要求说明"><Input /></Form.Item>
                    </Col>
                    <Col xs={24} md={12}>
                      <Form.Item name="leadership_signals" label="领导力要求（逗号分隔）"><Input /></Form.Item>
                    </Col>
                    <Col xs={24} md={12}>
                      <Form.Item name="communication_signals" label="沟通能力要求（逗号分隔）"><Input /></Form.Item>
                    </Col>
                  </Row>
                  <Form.Item name="other_notes" label="其他说明"><Input.TextArea rows={3} /></Form.Item>
                </>
              ),
            },
          ]}
        />

        <Divider orientation="left">筛选重点</Divider>
        <Alert
          type="info"
          showIcon
          message="只把真正的一票否决条件设为“必须满足”"
          description="“重点参考”用于排序和查找相关经历；“仅作背景”只帮助理解岗位。信息没写清时系统会标记为待确认，不会直接淘汰候选人。"
          style={{ marginBottom: 12 }}
        />
        <List
          className="job-requirement-priority-list"
          dataSource={requirementChoices}
          locale={{ emptyText: '填写岗位职责或任职要求后，这里会自动生成筛选重点' }}
          renderItem={(item) => (
            <List.Item
              extra={(
                <Segmented
                  value={item.classification}
                  onChange={(value) => updateClassification(item.key, value)}
                  options={[
                    { label: '必须满足', value: 'hard' },
                    { label: '重点参考', value: 'preferred' },
                    { label: '仅作背景', value: 'context' },
                  ]}
                />
              )}
            >
              <List.Item.Meta
                title={item.text}
                description={<Tag>{item.label}</Tag>}
              />
            </List.Item>
          )}
        />
        <Space>
          <Button type="primary" htmlType="submit" loading={saving}>{submitText}</Button>
        </Space>
      </Form>
    </Card>
  );
}
