import { Navigate } from 'react-router-dom';

export default function ProtectedRoute({ role, children }) {
  const token = localStorage.getItem('token');
  const browserSession = localStorage.getItem('auth_session');
  const userRole = localStorage.getItem('role');

  if (!token && !browserSession) {
    return <Navigate to="/login" replace />;
  }

  if (role && userRole !== role) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
