import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { AppLayout } from './components/nav/AppLayout'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import SearchResults from './pages/SearchResults'
import AccountView from './pages/AccountView'
import GraphPage from './pages/GraphPage'
import InvestigationsPage from './pages/InvestigationsPage'
import CaseDetailPage from './pages/CaseDetailPage'
import CaseGraphPage from './pages/CaseGraphPage'
import RiskPolicyPage from './pages/RiskPolicyPage'
import RecoveryPage from './pages/RecoveryPage'
import RecoveryDashboardPage from './pages/RecoveryDashboardPage'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public routes — reachable without a session */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          {/* Everything else lives behind authentication, inside the navbar shell */}
          <Route
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/search" element={<SearchResults />} />
            <Route path="/accounts" element={<Navigate to="/graph" replace />} />
            <Route path="/accounts/:accountNumber" element={<AccountView />} />
            <Route path="/graph" element={<GraphPage />} />
            <Route path="/investigations" element={<InvestigationsPage />} />
            <Route path="/investigations/:caseId" element={<CaseDetailPage />} />
            <Route path="/investigations/:caseId/graph" element={<CaseGraphPage />} />
            <Route path="/admin/risk-policy" element={<RiskPolicyPage />} />
            <Route path="/recovery" element={<RecoveryDashboardPage />} />
            <Route path="/recovery/:caseId" element={<RecoveryPage />} />
          </Route>

          {/* Defaults */}
          <Route path="/" element={<Navigate to="/graph" replace />} />
          <Route path="*" element={<Navigate to="/graph" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
