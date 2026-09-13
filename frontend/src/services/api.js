import axios from 'axios';
import toast from 'react-hot-toast';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export const API_ORIGIN = new URL(API_BASE_URL, window.location.origin).origin;

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 120000,
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (res) => res,
  (err) => {
    let message = 'An unexpected error occurred';

    if (err.response) {
      const status = err.response.status;
      const detail = err.response.data?.detail;

      if (status === 400) message = detail || 'Invalid request';
      else if (status === 401) message = detail || 'Please sign in again';
      else if (status === 403) message = 'Insufficient permissions';
      else if (status === 404) message = detail || 'Resource not found';
      else if (status === 413) message = 'File too large (max 10MB)';
      else if (status === 422) message = 'Validation error: ' + (detail || 'Check your input');
      else if (status === 500) message = 'Server error. Please try again later';
      else if (detail) message = detail;
    } else if (err.request) {
      message = err.code === 'ECONNABORTED'
        ? 'Request timeout. Please try again'
        : 'Cannot connect to server. Please check your connection';
    }

    if (message) toast.error(message);
    return Promise.reject(err);
  }
);

export const kycAPI = {
  createApplication: async (data) => {
    const response = await api.post('/applications/', data);
    return response.data;
  },

  uploadDocument: async (applicationId, documentType, file, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await api.post(`/documents/${applicationId}/upload`, formData, {
      params: { document_type: documentType },
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          onProgress({ loaded: progressEvent.loaded, total: progressEvent.total });
        }
      },
    });
    return response.data;
  },

  uploadLivenessFrames: async (applicationId, files) => {
    const formData = new FormData();
    files.forEach((file) => formData.append('frames', file));

    const response = await api.post(`/documents/${applicationId}/upload/liveness`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  startVerification: async (applicationId) => {
    const response = await api.post(`/verification/${applicationId}/process`);
    return response.data;
  },

  getStatus: async (applicationId) => {
    const response = await api.get(`/applications/${applicationId}/status`);
    return response.data;
  },

  getResults: async (applicationId) => {
    const response = await api.get(`/verification/${applicationId}/results`);
    return response.data;
  },

  getAuditTrail: async (applicationId) => {
    const response = await api.get(`/audit/${applicationId}/trail`);
    return response.data;
  },

  listDocuments: async (applicationId) => {
    const response = await api.get(`/documents/application/${applicationId}/list`);
    return response.data;
  },

  listApplications: async (status) => {
    const response = await api.get('/applications/', {
      params: status && status !== 'all' ? { status_filter: status } : {},
    });
    return response.data;
  },

  overrideDecision: async (applicationId, decision, reason) => {
    const response = await api.post(`/applications/${applicationId}/override`, {
      decision,
      reason,
    });
    return response.data;
  },

  login: async (email, password) => {
    const response = await api.post('/auth/login', { email, password });
    return response.data;
  },
};

export default api;
