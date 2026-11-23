import { useEffect, useState } from 'react';
import { Table, Input, Select, Button, Drawer, Tabs, Space, Tag, Typography } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { getDocuments, getDocument, getKwic, DocItem, KwicHit } from '../api';

const LANG_LABEL: Record<string, string> = { ar: '阿语', en: '英语', zh: '中文' };
const VARIANT_LABEL: Record<string, string> = {
  MSA: '标准阿语', Khaliji: '海湾方言', Arabizi: 'Arabizi', EN: '英语', ZH: '中文',
};

export default function CorpusExplorer() {
  const [items, setItems] = useState<DocItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [lang, setLang] = useState<string | undefined>();
  const [detail, setDetail] = useState<any>(null);
  const [kwTerm, setKwTerm] = useState('BYD');
  const [kwLang, setKwLang] = useState<string | undefined>();
  const [kwHits, setKwHits] = useState<KwicHit[]>([]);
  const [loading, setLoading] = useState(false);

  const load = (p = page) => {
    setLoading(true);
    getDocuments({ page: p, page_size: 15, keyword: keyword || undefined, lang })
      .then(r => { setItems(r.items); setTotal(r.total); setPage(p); })
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(1); }, []);   // 首次加载

  const runKwic = () => getKwic(kwTerm, kwLang).then(r => setKwHits(r.hits));

  const cols = [
    { title: '语言', width: 70, render: (_: unknown, r: DocItem) => <Tag color={r.language === 'ar' ? 'green' : r.language === 'en' ? 'blue' : 'red'}>{LANG_LABEL[r.language] ?? r.language}</Tag> },
    { title: '变体', width: 90, render: (_: unknown, r: DocItem) => VARIANT_LABEL[r.lang_variant] ?? r.lang_variant },
    { title: '国家', width: 60, dataIndex: 'country' },
    { title: '标题', ellipsis: true, dataIndex: 'title' },
    { title: '词数', width: 70, dataIndex: 'word_count' },
    { title: '操作', width: 80, render: (_: unknown, r: DocItem) => (
      <Button size="small" onClick={() => getDocument(r.doc_id).then(setDetail)}>详情</Button>
    )},
  ];

  return (
    <Tabs
      defaultActiveKey="list"
      items={[
        {
          key: 'list', label: '语料列表',
          children: (
            <>
              <Space style={{ marginBottom: 12 }} wrap>
                <Input placeholder="关键词（中/阿/英）" style={{ width: 280 }}
                  value={keyword} onChange={e => setKeyword(e.target.value)}
                  onPressEnter={() => load(1)} />
                <Select allowClear placeholder="语言" style={{ width: 120 }} value={lang}
                  onChange={v => { setLang(v); }}
                  options={[{ value: 'ar', label: '阿语' }, { value: 'en', label: '英语' }, { value: 'zh', label: '中文' }]} />
                <Button type="primary" icon={<SearchOutlined />} onClick={() => load(1)}>检索</Button>
                <span style={{ color: '#888' }}>共 {total} 条</span>
              </Space>
              <Table rowKey="doc_id" size="small" loading={loading}
                columns={cols} dataSource={items}
                pagination={{ current: page, pageSize: 15, total,
                  onChange: p => load(p), showSizeChanger: false }} />
              <Drawer width={640} open={!!detail} onClose={() => setDetail(null)}
                title={detail?.title}>
                <Typography.Paragraph copyable>
                  <b>来源：</b>{detail?.source_id} · {detail?.source_layer} · {detail?.country}
                </Typography.Paragraph>
                <Typography.Paragraph>
                  <b>URL：</b><a href={detail?.url} target="_blank" rel="noreferrer">{detail?.url}</a>
                </Typography.Paragraph>
                <Typography.Paragraph>
                  <b>正文：</b>
                  <div style={{ whiteSpace: 'pre-wrap', maxHeight: 480, overflow: 'auto' }}>
                    {detail?.text_clean}
                  </div>
                </Typography.Paragraph>
              </Drawer>
            </>
          ),
        },
        {
          key: 'kwic', label: 'KWIC 索引行',
          children: (
            <>
              <Space style={{ marginBottom: 12 }}>
                <Input placeholder="检索词（如 BYD / بطارية / 保修）" style={{ width: 260 }}
                  value={kwTerm} onChange={e => setKwTerm(e.target.value)}
                  onPressEnter={runKwic} />
                <Select allowClear placeholder="限定语言" style={{ width: 120 }} value={kwLang}
                  onChange={setKwLang}
                  options={[{ value: 'ar', label: '阿语' }, { value: 'en', label: '英语' }]} />
                <Button type="primary" onClick={runKwic}>生成索引行</Button>
                <span style={{ color: '#888' }}>命中 {kwHits.length} 行</span>
              </Space>
              {kwHits.map((h, i) => (
                <div key={i} style={{ fontFamily: 'monospace', padding: '4px 8px',
                  borderBottom: '1px solid #f0f0f0', direction: h.language === 'ar' ? 'rtl' : 'ltr' }}>
                  <Tag>{LANG_LABEL[h.language] ?? h.language}</Tag>
                  ...{h.left}<b style={{ background: '#ffe58f' }}>{h.keyword}</b>{h.right}...
                </div>
              ))}
            </>
          ),
        },
      ]}
    />
  );
}
