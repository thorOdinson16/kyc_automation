import React from 'react';
import { useNavigate } from 'react-router-dom';

export default function Landing() {
  const nav = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="max-w-4xl w-full px-6">
        <div className="flex items-center justify-between mb-8">
          <div className="text-2xl font-bold">KYC AI</div>
          <button className="btn-primary" onClick={() => nav('/onboard')}>Start KYC</button>
        </div>

        <div className="card grid md:grid-cols-2 gap-6 items-center">
          <div>
            <h1 className="text-4xl font-extrabold mb-4">Dark AI KYC — Fast. Secure. Futuristic.</h1>
            <p className="text-sm text-[color:var(--muted)] mb-6">
              Complete identity verification in minutes.
            </p>
            <button className="btn-primary" onClick={() => nav('/onboard')}>Get started</button>
          </div>

          <div className="p-4 bg-gradient-to-br from-[#6f2bd90f] to-[#00e5ff0a] rounded-lg">
            <div className="h-48 flex items-center justify-center text-[color:var(--muted)] text-sm">
              Visual Preview Placeholder
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
