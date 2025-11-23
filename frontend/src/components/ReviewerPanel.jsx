import React, { useEffect, useState } from 'react';
import { kycAPI } from '../services/api.js';

export default function ReviewerPanel() {
  const [selected, setSelected] = useState(null);
  const [audit, setAudit] = useState([]);

  useEffect(() => {
    const id = localStorage.getItem('applicationId');
    if (id) loadApplication(id);
  }, []);

  const loadApplication = async (id) => {
    try {
      const r = await kycAPI.getResults(id);
      const a = await kycAPI.getAuditTrail(id);
      setSelected(r);
      setAudit(a.audit_trail || []);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="min-h-screen p-6">
      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-1 card">
          <h4 className="font-semibold mb-3">Applications</h4>
          <div className="space-y-2 text-sm text-[color:var(--muted)]">Use local demo: click 'Load Application' below</div>
          <button className="btn-primary mt-4" onClick={() => { const id = localStorage.getItem('applicationId'); if (id) loadApplication(id); }}>Load Application</button>
        </div>

        <div className="col-span-2 space-y-4">
          <div className="card">
            <h4 className="font-semibold">Summary</h4>
            <pre className="text-sm max-h-48 overflow-auto bg-black/20 p-3 rounded">{JSON.stringify(selected, null, 2)}</pre>
          </div>

          <div className="card">
            <h4 className="font-semibold">Audit Logs</h4>
            <div className="space-y-2">
              {audit.map(a => (
                <div key={a.log_id || Math.random()} className="p-3 bg-black/20 rounded">
                  <div className="text-xs text-[color:var(--muted)]">{a.timestamp}</div>
                  <div className="font-medium">{a.action_type}</div>
                  <pre className="text-xs mt-1">{JSON.stringify(a.action_details, null, 2)}</pre>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
