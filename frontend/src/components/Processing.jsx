import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { kycAPI } from '../services/api.js';

const STEPS = ['OCR', 'Face Match', 'Liveness', 'Entity Validation', 'Risk Scoring', 'Explainability'];

export default function Processing() {
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [status, setStatus] = useState('processing');

  useEffect(() => {
    const id = localStorage.getItem('applicationId');
    if (!id) {
      nav('/');
      return;
    }

    let mounted = true;
    const timer = setInterval(async () => {
      try {
        const current = await kycAPI.getStatus(id);
        if (!mounted) return;

        setStatus(current.status);
        setStep((n) => Math.min(n + 1, STEPS.length - 1));

        if (['approved', 'rejected', 'review_required'].includes(current.status)) {
          clearInterval(timer);
          nav('/results');
        }
      } catch (err) {
        console.error(err);
      }
    }, 2000);

    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [nav]);

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="card w-full max-w-lg text-center">
        <h2 className="text-2xl font-bold mb-2">Processing</h2>
        <p className="text-[color:var(--muted)] mb-6">
          Please wait while we analyse your documents ({status}).
        </p>

        <div className="space-y-2 text-left">
          {STEPS.map((name, index) => (
            <div
              key={name}
              className={`flex items-center text-sm ${
                index < step ? 'text-green-400' : index === step ? 'text-white' : 'text-[color:var(--muted)]'
              }`}
            >
              <span className="mr-3">{index < step ? '\u2713' : index === step ? '\u25CF' : '\u25CB'}</span>
              {name}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
