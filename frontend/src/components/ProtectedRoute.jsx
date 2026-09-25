import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { SessionBootScreen } from "./AuthLayout.jsx";

export default function ProtectedRoute({ children }) {
  const { user, loading, booting } = useAuth();
  const location = useLocation();

  if (booting || loading) return <SessionBootScreen />;
  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return children;
}

export function GuestRoute({ children }) {
  const { user, booting } = useAuth();
  if (booting) return <SessionBootScreen />;
  if (user) return <Navigate to="/dashboard" replace />;
  return children;
}