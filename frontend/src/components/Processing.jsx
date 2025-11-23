import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { kycAPI } from '../services/api.js';

export default function Processing() {
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [status, setStatus] = useState('processing');

  useEffect(() => {
    const id = localStorage.getItem('applicationId');
    const steps = ['OCR', 'Face Match', 'Liveness', 'Entity', 'Risk', 'Explain'];
    let mounted = true;
    const t = setInterval(async () => {
      try {
        const s = await kycAPI.getStatus(id);
        if (!mounted) return;
        setStatus(s.status);
        setStep((n) => (n + 1) % steps.length);
        if (['approved', 'rejected', 'review_required'].includes(s.status)) {
          clearInterval(t);
          nav('/results');
        }
      } catch (e) {
        console.error(e);
      }
    }, 2000);

    return () => { mounted = false; clearInterval(t); };
  }, [nav]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="card w-full max-w-lg text-center">
        <h2 className="text-2xl font-bold mb-2">Processing</h2>
        <p className="text-[color:var(--muted)]">Please wait while we analyze your documents...</p>
      </div>
    </div>
  );
}
