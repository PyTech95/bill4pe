import axios from "axios";

export const API = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`,
  withCredentials: true,
});

let refreshing = null;

API.interceptors.response.use(
  (res) => res,
  async (err) => {
    const orig = err.config;
    if (
      err.response?.status === 401 &&
      orig &&
      !orig._retry &&
      !orig.url.includes("/auth/")
    ) {
      orig._retry = true;
      try {
        refreshing = refreshing || API.post("/auth/refresh");
        await refreshing;
        refreshing = null;
        return API(orig);
      } catch (e) {
        refreshing = null;
      }
    }
    return Promise.reject(err);
  }
);

export function fmtErr(e) {
  const d = e?.response?.data?.detail;
  if (d == null) return e?.message || "Something went wrong. Please try again.";
  if (typeof d === "string") return d;
  if (Array.isArray(d))
    return d.map((x) => (x && typeof x.msg === "string" ? x.msg : JSON.stringify(x))).filter(Boolean).join(" ");
  if (d && typeof d.msg === "string") return d.msg;
  return String(d);
}
