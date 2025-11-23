import axios from 'axios';
import toast from 'react-hot-toast';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000 // 60 second timeout for processing
});

// Request interceptor
api.interceptors.request.use(
  (config) => {
    console.log(`[API] ${config.method.toUpperCase()} ${config.url}`);
    return config;
  },
  (error) => {
    console.error('[API] Request error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor
api.interceptors.response.use(
  (res) => {
    console.log(`[API] Response:`, res.data);
    return res;
  },
  (err) => {
    console.error('[API] Error:', err.response || err);
    
    let message = 'An unexpected error occurred';

    if (err.response) {
      const status = err.response.status;
      const detail = err.response.data?.detail;

      if (status === 400) {
        message = detail || 'Invalid request';
      } else if (status === 404) {
        message = detail || 'Resource not found';
      } else if (status === 413) {
        message = 'File too large (max 10MB)';
      } else if (status === 422) {
        message = 'Validation error: ' + (detail || 'Check your input');
      } else if (status === 500) {
        message = 'Server error. Please try again later';
      } else if (detail) {
        message = detail;
      }
    } else if (err.request) {
      if (err.code === 'ECONNABORTED') {
        message = 'Request timeout. Please try again';
      } else {
        message = 'Cannot connect to server. Please check your connection';
      }
    }

    toast.error(message);
    return Promise.reject(err);
  }
);

export const kycAPI = {
  // Create application
  createApplication: async (data) => {
    try {
      const response = await api.post('/applications/', data);
      return response.data;
    } catch (error) {
      console.error('Create application error:', error);
      throw error;
    }
  },

  // Upload document with progress tracking
  uploadDocument: async (applicationId, documentType, file, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await api.post(
        `/documents/${applicationId}/upload`,
        formData,
        {
          params: { document_type: documentType },
          headers: { 'Content-Type': 'multipart/form-data' },
          onUploadProgress: (progressEvent) => {
            if (onProgress && progressEvent.total) {
              const percentCompleted = Math.round(
                (progressEvent.loaded * 100) / progressEvent.total
              );
              onProgress({ loaded: progressEvent.loaded, total: progressEvent.total });
            }
          }
        }
      );
      return response.data;
    } catch (error) {
      console.error('Upload document error:', error);
      throw error;
    }
  },

  // Start verification process
  startVerification: async (applicationId) => {
    try {
      const response = await api.post(`/verification/${applicationId}/process`);
      return response.data;
    } catch (error) {
      console.error('Start verification error:', error);
      throw error;
    }
  },

  // Get application status
  getStatus: async (applicationId) => {
    try {
      const response = await api.get(`/applications/${applicationId}/status`);
      return response.data;
    } catch (error) {
      console.error('Get status error:', error);
      throw error;
    }
  },

  // Get verification results
  getResults: async (applicationId) => {
    try {
      const response = await api.get(`/verification/${applicationId}/results`);
      return response.data;
    } catch (error) {
      console.error('Get results error:', error);
      throw error;
    }
  },

  // Get audit trail
  getAuditTrail: async (applicationId) => {
    try {
      const response = await api.get(`/audit/${applicationId}/trail`);
      return response.data;
    } catch (error) {
      console.error('Get audit trail error:', error);
      throw error;
    }
  }
};

export default api;