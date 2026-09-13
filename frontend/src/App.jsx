import React from 'react';
import { Routes, Route } from 'react-router-dom';

import Landing from './components/Landing.jsx';
import Login from './components/Login.jsx';
import Onboard from './components/Onboard.jsx';
import UploadDocs from './components/UploadDocs.jsx';
import Processing from './components/Processing.jsx';
import Results from './components/Results.jsx';
import ReviewerPanel from './components/ReviewerPanel.jsx';
import { Toaster } from 'react-hot-toast';

export default function App() {
  return (
    <div>
      <Toaster position="top-right" />

      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/onboard" element={<Onboard />} />
        <Route path="/upload" element={<UploadDocs />} />
        <Route path="/processing" element={<Processing />} />
        <Route path="/results" element={<Results />} />
        <Route path="/reviewer" element={<ReviewerPanel />} />
      </Routes>
    </div>
  );
}
