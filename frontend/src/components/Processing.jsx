import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { kycAPI } from '../services/api.js';

const STEPS = [
  'Application',
  'OCR / text extraction',
  'Face match',
  'Liveness check',
  'Entity validation',
  'Risk scoring',
  'Explainability',
];

export default function Processing() {
  const nav = useNavigate();
  const [progress, setProgress] = useState({
    stage: 'Starting',
    step: 0,
    status: 'processing',
    elapsed_seconds: 0,
  });

  useEffect(() => {
    const id = localStorage.getItem('applicationId');
    if (!id) {
      nav('/');
      return;
    }

    let mounted = true;

    const poll = async () => {
      try {
        const current = await kycAPI.getProgress(id);
        if (!mounted) return;

        setProgress(current);

        if (['approved', 'rejected', 'review_required'].includes(current.status)) {
          clearInterval(timer);
          nav('/results');
        }
      } catch (err) {
        console.error(err);
      }
    };

    poll();
    const timer = setInterval(poll, 2000);

    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [nav]);

  const step = progress.step ?? 0;

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="card w-full max-w-lg text-center">
        <h2 className="text-2xl font-bold mb-2">Processing</h2>
        <p className="text-[color:var(--muted)] mb-1">
          Current step: <span className="text-white">{progress.stage}</span>
        </p>
        <p className="text-xs text-[color:var(--muted)] mb-6">
          {Math.round(progress.elapsed_seconds || 0)}s elapsed - this can take up to a minute
        </p>

        <div className="space-y-2 text-left">
          {STEPS.map((name, index) => (
            <div
              key={name}
              className={`flex items-center text-sm ${
                index < step
                  ? 'text-green-400'
                  : index === step
                  ? 'text-white'
                  : 'text-[color:var(--muted)]'
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
