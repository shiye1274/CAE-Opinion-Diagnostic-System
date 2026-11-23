import { useState } from 'react';
import { Alert, Button, Card, Input, Space, Table, Tag } from 'antd';
import { checkCompliance, ComplianceResult } from '../api';

const { TextArea } = Input;

const SEV_COLOR: Record<string, string> = { high: 'red', medium: 'orange', low: 'gold' };
const CAT_LABEL: Record<string, string> = {
  RELIGION: '宗教禁忌', POLITICS: '政治地缘', GENDER: '性别与家庭',
  CUSTOM: '社会习俗', STEREOTYPE: '刻板归因',
};

const SAMPLE = `Our new EV is perfect for Gulf families, with 550km real range even at 50°C.
Celebrate Ramadan sale with beer and wine gift packs! Cheap Chinese quality is history.`;

export default function Compliance() {
  const [text, setText] = useState('');
  const [result, setResult] = useState<ComplianceResult | null>(null);
  const [busy, setBusy] = useState(false);

  const run = () => {
    if (!text.trim()) return;
    setBusy(true);
    checkCompliance(text).then(setResult).finally(() => setBusy(false));
  };

  return (
    <Card>
      <TextArea
        rows={7} value={text} onChange={e => setText(e.target.value)}
        placeholder="粘贴待发布的阿语/英语/中文营销文案或公关声明，系统将基于文化合规规则库自动标红风险表达…"
      />
      <Space style={{ marginTop: 12 }}>
        <Button type="primary" loading={busy} onClick={run}>审查文案</Button>
        <Button onClick={() => setText(SAMPLE)}>填入示例</Button>
      </Space>

      {result && (
        <div style={{ marginTop: 20 }}>
          <Alert
            type={result.risk_level === 'HIGH' ? 'error' : result.risk_level === 'CLEAN' ? 'success' : 'warning'}
            message={`风险等级：${result.risk_level}`}
            description={result.summary}
            style={{ marginBottom: 16 }}
          />
          <Table
            rowKey="rule_id" size="small" pagination={false}
            dataSource={result.hits}
            columns={[
              { title: '规则', dataIndex: 'rule_id', width: 70 },
              { title: '维度', dataIndex: 'category', render: (c: string) =>
                <Tag>{CAT_LABEL[c] ?? c}</Tag> },
              { title: '等级', dataIndex: 'severity', width: 90, render: (s: string) =>
                <Tag color={SEV_COLOR[s]}>{s.toUpperCase()}</Tag> },
              { title: '命中上下文', dataIndex: 'matched', ellipsis: true },
              { title: '本土化改写建议', dataIndex: 'advice', ellipsis: true },
            ]}
          />
        </div>
      )}
    </Card>
  );
}
