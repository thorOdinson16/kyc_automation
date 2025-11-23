import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { kycAPI } from '../services/api.js';
import toast from 'react-hot-toast';

export default function Onboard() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();

  const submit = async () => {
    setLoading(true);
    try {
      const res = await kycAPI.createApplication({ name, email, phone });
      if (res?.application_id) {
        localStorage.setItem('applicationId', res.application_id);
        toast.success('Application created');
        nav('/upload');
      } else {
        toast.error('Unexpected response');
      }
    } catch (err) {
      toast.error('Failed to create application');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-full max-w-lg">
        <div className="card">
          <h2 className="text-xl font-bold mb-4">Your details</h2>
          <div className="space-y-3">
            <input className="input-field" placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} />
            <input className="input-field" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <input className="input-field" placeholder="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
            <div className="flex gap-3">
              <button className="btn-primary flex-1" onClick={submit}>{loading ? 'Creating...' : 'Continue'}</button>
              <button className="btn-secondary flex-1" onClick={() => { localStorage.clear(); nav('/'); }}>Cancel</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
