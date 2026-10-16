/**
 * src/components/ProtectedRoute.jsx
 *
 * Wraps a route to require authentication and optionally a specific role.
 * Redirects unauthenticated users to /login.
 * Redirects wrong-role users to their default page.
 */

import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const ROLE_DEFAULT = {
  SUPER_ADMIN: '/superadmin',
  ADMIN: '/admin',
  ANALYST: '/workspace',
}

export default function ProtectedRoute({ children, allowedRoles }) {
  const { isAuthenticated, role } = useAuth()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (allowedRoles && !allowedRoles.includes(role)) {
    const redirect = ROLE_DEFAULT[role] ?? '/workspace'
    return <Navigate to={redirect} replace />
  }

  return children
}
