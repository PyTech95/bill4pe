import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { AuthProvider, useAuth } from '@/lib/auth';
import './App.css';

import Landing from '@/pages/Landing';
import Privacy from '@/pages/Privacy';
import Terms from '@/pages/Terms';
import Login from '@/pages/auth/Login';
import PhoneLogin from '@/pages/auth/PhoneLogin';
import Register from '@/pages/auth/Register';
import Splash from '@/pages/app/Splash';
import Categories from '@/pages/app/Categories';
import SubCategory from '@/pages/app/SubCategory';
import TravelSubCategory from '@/pages/app/TravelSubCategory';
import HotelSubCategory from '@/pages/app/HotelSubCategory';
import Capture from '@/pages/app/Capture';
import Editor from '@/pages/app/Editor';
import PayNow from '@/pages/app/PayNow';
import BillGen from '@/pages/app/BillGen';
import Dashboard from '@/pages/app/Dashboard';
import Wallet from '@/pages/app/Wallet';
import Trips from '@/pages/app/Trips';
import Reports from '@/pages/app/Reports';
import Profile from '@/pages/app/Profile';
import Referrals from '@/pages/app/Referrals';
import AppShell from '@/components/AppShell';

const Private = ({ children }) => {
  const { user } = useAuth();
  return user ? children : <Navigate to="/login" replace />;
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster position="top-center" richColors />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="/login" element={<Login />} />
          <Route path="/login/phone" element={<PhoneLogin />} />
          <Route path="/register" element={<Register />} />

          <Route path="/app" element={<Private><AppShell /></Private>}>
            <Route index element={<Splash />} />
            <Route path="categories" element={<Categories />} />
            <Route path="category/travel" element={<TravelSubCategory />} />
            <Route path="category/hotel" element={<HotelSubCategory />} />
            <Route path="category/:cat" element={<SubCategory />} />
            <Route path="capture/:cat/:sub" element={<Capture />} />
            <Route path="editor" element={<Editor />} />
            <Route path="pay" element={<PayNow />} />
            <Route path="bill/:id" element={<BillGen />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="wallet" element={<Wallet />} />
            <Route path="trips" element={<Trips />} />
            <Route path="reports" element={<Reports />} />
            <Route path="profile" element={<Profile />} />
            <Route path="referrals" element={<Referrals />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
