import axios from 'axios';

const api = axios.create({ baseURL: '/api/v1', timeout: 30000 });

// ---- 类型 ----
export interface Overview {
  total_docs: number; total_ugc: number; total_words: number;
  arabic_ratio: number;
  by_language: { language: string; n: number }[];
  by_layer: { layer: string; n: number }[];
  by_country: { country: string; n: number }[];
  by_lang_variant: { lang_variant: string; n: number }[];
}
export interface DocItem {
  doc_id: string; source_id: string; source_layer: string; language: string;
  lang_variant: string; country: string; title: string; published: string;
  word_count: number; url: string; content_type: string;
}
export interface KwicHit {
  doc_id: string; language: string; country: string; published: string;
  left: string; keyword: string; right: string;
}
export interface ComplianceHit {
  rule_id: string; category: string; severity: string;
  matched: string; term: string; advice: string;
}
export interface ComplianceResult {
  scene: string; risk_level: string; categories: string[];
  hits: ComplianceHit[]; summary: string;
}
export interface BrandVolume {
  brand_id: string; name: string; group: string;
  total: number; ar: number; en: number; zh: number;
}

// ---- 接口 ----
export const getOverview = () => api.get<Overview>('/stats/overview').then(r => r.data);
export const getDocuments = (params: Record<string, unknown>) =>
  api.get<{ total: number; items: DocItem[] }>('/documents', { params }).then(r => r.data);
export const getDocument = (docId: string) => api.get('/documents/' + docId).then(r => r.data);
export const getKwic = (term: string, lang?: string, limit = 50) =>
  api.get<{ hits: KwicHit[]; total: number }>('/kwic', { params: { term, lang, limit } }).then(r => r.data);
export const checkCompliance = (text: string, scene = 'ad') =>
  api.post<ComplianceResult>('/compliance/check', { text, scene }).then(r => r.data);
export const getBrandVolume = () =>
  api.get<{ brands: BrandVolume[] }>('/brands/volume').then(r => r.data);
