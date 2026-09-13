import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { kycAPI } from '../services/api.js';

export default function Onboard() {
  const nav = useNavigate();
  const [form, setForm] = useState({ name: '', email: '', phone: '' });
  const [submitting, setSubmitting] = useState(false);

  const update = (field) => (event) =>
    setForm((prev) => ({ ...prev, [field]: event.target.value }));

  const startApplication = async () => {
    if (!form.name.trim()) {
      toast.error('Please enter your full name');
      return;
    }

    setSubmitting(true);
    try {
      const application = await kycAPI.createApplication({
        name: form.name.trim(),
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
      });

      localStorage.setItem('applicationId', application.application_id);
      if (application.access_token) {
        localStorage.setItem('token', application.access_token);
      }
      toast.success('Application created. Let us verify your documents.');
      nav('/upload');
    } catch (err) {
      console.error('Create application error:', err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="card w-full max-w-lg">
        <h2 className="text-2xl font-bold mb-1">Your details</h2>
        <p className="text-sm text-[color:var(--muted)] mb-6">
          We only need a few details to begin your KYC verification.
        </p>

        <label className="block text-sm mb-1">Full name *</label>
        <input
          className="input-field mb-4"
          placeholder="Jane Doe"
          value={form.name}
          onChange={update('name')}
        />

        <label className="block text-sm mb-1">Email</label>
        <input
          className="input-field mb-4"
          type="email"
          placeholder="jane@example.com"
          value={form.email}
          onChange={update('email')}
        />

        <label className="block text-sm mb-1">Phone</label>
        <input
          className="input-field mb-6"
          placeholder="+91 90000 00000"
          value={form.phone}
          onChange={update('phone')}
        />

        <button
          className={`btn-primary w-full ${submitting ? 'opacity-60 cursor-not-allowed' : ''}`}
          onClick={startApplication}
          disabled={submitting}
        >
          {submitting ? 'Creating application...' : 'Continue to document upload'}
        </button>

        <button className="btn-secondary w-full mt-3" onClick={() => nav('/')}>
          Back
        </button>
      </div>
    </div>
  );
}
