import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { kycAPI } from '../services/api.js';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const nav = useNavigate();

  const login = async () => {
    if (!email || !password) {
      toast.error('Enter your email and password');
      return;
    }

    setSubmitting(true);
    try {
      const data = await kycAPI.login(email, password);

      if (data.role !== 'reviewer' && data.role !== 'admin') {
        localStorage.removeItem('token');
        localStorage.removeItem('role');
        toast.error('Staff access only. Applicants start from the home page.');
        return;
      }

      localStorage.setItem('token', data.access_token);
      localStorage.setItem('role', data.role);
      nav('/reviewer');
    } catch (err) {
      console.error('Login error:', err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="card w-full max-w-md">
        <h2 className="text-2xl font-bold mb-4">Staff Login</h2>
        <input
          className="input-field mb-3"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          className="input-field mb-4"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button
          className={`btn-primary w-full ${submitting ? 'opacity-60 cursor-not-allowed' : ''}`}
          onClick={login}
          disabled={submitting}
        >
          {submitting ? 'Signing in...' : 'Login'}
        </button>
        <button className="btn-secondary w-full mt-3" onClick={() => nav('/')}>
          Back
        </button>
      </div>
    </div>
  );
}
