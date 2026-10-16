import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import ProtectedRoute from './components/ProtectedRoute';
import { useAuth } from './context/AuthContext';

// ---------------------------------------------------------------------------
// Route-level code splitting (Plan D)
// Each page is loaded lazily so Vite emits a separate chunk per route.
// The common ProtectedRoute + AuthContext stay in the main bundle since they
// are needed on every navigation before the page chunk is resolved.
// ---------------------------------------------------------------------------
const LandingPage   = lazy(() => import('./pages/LandingPage'));
const LoginPage     = lazy(() => import('./pages/LoginPage'));
const SignupPage    = lazy(() => import('./pages/SignupPage'));
const WorkspacePage = lazy(() => import('./pages/WorkspacePage'));
const OrgAdminPage  = lazy(() => import('./pages/OrgAdminPage'));
const SuperAdminPage = lazy(() => import('./pages/SuperAdminPage'));

// ---------------------------------------------------------------------------
// Full-screen loading fallback shown while a route chunk is being fetched.
// Uses the app's design-system tokens so it blends with the rest of the UI.
// ---------------------------------------------------------------------------
function PageLoader() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        gap: '16px',
        backgroundColor: 'var(--background)',
      }}
    >
      <div
        style={{
          width: '36px',
          height: '36px',
          border: '3px solid var(--surface-container)',
          borderTopColor: 'var(--primary)',
          borderRadius: '50%',
          animation: 'spin 0.75s linear infinite',
        }}
      />
      <p style={{ color: 'var(--on-surface-variant)', fontSize: '14px', margin: 0 }}>
        Loading…
      </p>
      {/* Keyframe defined inline so it requires no extra CSS file */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export default function App() {
  const { user, loading } = useAuth();

  // AuthContext resolves before any lazy page chunk is requested, so the
  // "Loading…" screen here covers both token validation AND chunk fetch on
  // first load, avoiding a double-flash.
  if (loading) {
    return <PageLoader />;
  }

  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />

        {/* Primary role-scoped portals */}
        <Route
          path="/workspace"
          element={
            <ProtectedRoute>
              <WorkspacePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedRoute allowedRoles={['ADMIN', 'SUPER_ADMIN']}>
              <OrgAdminPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/superadmin"
          element={
            <ProtectedRoute allowedRoles={['SUPER_ADMIN']}>
              <SuperAdminPage />
            </ProtectedRoute>
          }
        />

        {/* Universal dashboard redirector */}
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <DashboardRouter user={user} />
            </ProtectedRoute>
          }
        />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

function DashboardRouter({ user }) {
  if (!user) return <Navigate to="/login" replace />;

  switch (user.role) {
    case 'SUPER_ADMIN':
      return <Navigate to="/superadmin" replace />;
    case 'ADMIN':
      return <Navigate to="/admin" replace />;
    case 'ANALYST':
    default:
      return <Navigate to="/workspace" replace />;
  }
}
