import React, { createContext, useContext, useEffect, useState } from 'react';
import api from './api';

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('bill4pe_user') || 'null'); } catch { return null; }
  });
  const [loading, setLoading] = useState(false);

  const persist = (token, u) => {
    localStorage.setItem('bill4pe_token', token);
    localStorage.setItem('bill4pe_user', JSON.stringify(u));
    setUser(u);
  };

  const login = async (email, password) => {
    setLoading(true);
    try {
      const { data } = await api.post('/auth/login', { email, password });
      persist(data.token, data.user);
      return data.user;
    } finally { setLoading(false); }
  };

  const register = async (email, password, name, referrerCode = null) => {
    setLoading(true);
    try {
      const { data } = await api.post('/auth/register', {
        email, password, name, referrer_code: referrerCode,
      });
      persist(data.token, data.user);
      return data.user;
    } finally { setLoading(false); }
  };

  const logout = () => {
    localStorage.removeItem('bill4pe_token');
    localStorage.removeItem('bill4pe_user');
    setUser(null);
  };

  const refreshUser = async () => {
    try {
      const { data } = await api.get('/auth/me');
      localStorage.setItem('bill4pe_user', JSON.stringify(data));
      setUser(data);
    } catch { /* ignore */ }
  };

  useEffect(() => { if (user) refreshUser(); /* eslint-disable-next-line */ }, []);

  return (
    <AuthCtx.Provider value={{ user, loading, login, register, logout, refreshUser }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
