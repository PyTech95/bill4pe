import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('bill4pe_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      localStorage.removeItem('bill4pe_token');
      localStorage.removeItem('bill4pe_user');
    }
    // Normalize FastAPI error detail into a plain, renderable string so components
    // that do `toast.error(err.response.data.detail)` never crash React with an
    // object/array child (422 validation errors return an array of objects).
    const d = err?.response?.data?.detail;
    if (d != null && typeof d !== 'string') {
      let msg;
      if (Array.isArray(d)) {
        msg = d.map((e) => (e && (e.msg || e.message)) || (typeof e === 'string' ? e : JSON.stringify(e))).join(', ');
      } else if (typeof d === 'object') {
        msg = d.msg || d.message || JSON.stringify(d);
      } else {
        msg = String(d);
      }
      err.response.data.detail = msg;
    }
    return Promise.reject(err);
  }
);

export default api;
