import React from 'react';
import { useNavigate } from 'react-router-dom';

export default function Landing() {
  const nav = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="max-w-4xl w-full px-6">
        <div className="flex items-center justify-between mb-8">
          <div className="text-2xl font-bold">KYC AI</div>
          <div className="flex gap-3">
            <button className="btn-secondary" onClick={() => nav('/login')}>Staff Login</button>
            <button className="btn-primary" onClick={() => nav('/onboard')}>Begin Verification</button>
          </div>
        </div>

        <div className="card grid md:grid-cols-2 gap-6 items-center">
          <div>
            <h1 className="text-4xl font-extrabold mb-4 leading-tight">
              Next-Gen Digital Identity
              <span className="block text-purple-400">Fast. Secure. Autonomous.</span>
            </h1>

            <p className="text-sm text-[color:var(--muted)] mb-6 leading-relaxed">
              Experience AI-powered identity verification built for accuracy, trust,
              and lightning-fast onboarding. Upload your documents, take a selfie,
              and let our automated pipeline do the rest — securely and transparently.
            </p>

            <button className="btn-primary" onClick={() => nav('/onboard')}>
              Start Your KYC
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
