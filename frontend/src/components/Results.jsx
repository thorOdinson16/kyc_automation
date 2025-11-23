import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { kycAPI } from '../services/api.js';
import toast from 'react-hot-toast';

export default function Results() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [audit, setAudit] = useState([]);

  useEffect(() => { load(); }, []);

  const load = async () => {
    const id = localStorage.getItem('applicationId');
    if (!id) {
      nav('/');
      return;
    }
    try {
      const r = await kycAPI.getResults(id);
      const a = await kycAPI.getAuditTrail(id);
      setData(r);
      setAudit(a.audit_trail || []);
    } catch (e) {
      console.error(e);
      toast.error('Failed to load results');
    }
  };

  if (!data) return <div className="min-h-screen flex items-center justify-center">Loading...</div>;

  const statusColor = data?.status === 'approved' ? 'text-green-400' : data?.status === 'rejected' ? 'text-red-400' : 'text-yellow-400';

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-full max-w-4xl space-y-4">
        <div className={"card text-center " + (statusColor)}>
          <h2 className="text-2xl font-bold">{(data.status || '').toUpperCase()}</h2>
          <p className="text-[color:var(--muted)]">Application ID: {data?.application_id}</p>
          <p className="mt-2">Risk score: {data?.risk_score ?? 'N/A'}</p>
        </div>

        <div className="card">
          <h4 className="font-semibold mb-3">Explainability</h4>
          <pre className="text-sm max-h-56 overflow-auto bg-black/20 p-3 rounded">{JSON.stringify(data?.explainability, null, 2)}</pre>
        </div>

        <div className="card">
          <h4 className="font-semibold mb-3">Audit Trail</h4>
          <div className="space-y-2">
            {audit.map((a) => (
              <div key={a.log_id || Math.random()} className="p-3 bg-black/20 rounded">
                <div className="text-xs text-[color:var(--muted)]">{a.timestamp}</div>
                <div className="font-medium">{a.action_type}</div>
                <pre className="text-xs mt-1">{JSON.stringify(a.action_details, null, 2)}</pre>
              </div>
            ))}
          </div>
        </div>

        <div className="flex gap-3">
          <button className="btn-primary flex-1" onClick={() => { localStorage.removeItem('applicationId'); nav('/'); }}>Start New</button>
          <button className="btn-secondary flex-1" onClick={() => nav('/reviewer')}>Reviewer</button>
        </div>
      </div>
    </div>
  );
}
