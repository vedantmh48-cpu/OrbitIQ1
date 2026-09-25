import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute, { GuestRoute } from "./components/ProtectedRoute.jsx";
import Layout from "./components/Layout.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import ForgotPassword from "./pages/ForgotPassword.jsx";
import ResetPassword from "./pages/ResetPassword.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Results from "./pages/Results.jsx";
import ResultDetail from "./pages/ResultDetail.jsx";
import History from "./pages/History.jsx";
import Datasets from "./pages/Datasets.jsx";
import GeoTools from "./pages/GeoTools.jsx";
import ChangeAnalysis from "./pages/ChangeAnalysis.jsx";
import Saved from "./pages/Saved.jsx";
import Settings from "./pages/Settings.jsx";
import HowToUse from "./pages/HowToUse.jsx";
import WeatherForecast from "./pages/WeatherForecast.jsx";
import CalamityPrediction from "./pages/CalamityPrediction.jsx";
import NotFound from "./pages/NotFound.jsx";

export default function App() {
  return (
    <Routes>
      {/* Login-first entry: the application opens on authentication. Signed-in
          visitors are handed straight to the workspace by GuestRoute. */}
      <Route path="/" element={<GuestRoute><Login /></GuestRoute>} />
      <Route path="/login" element={<GuestRoute><Login /></GuestRoute>} />
      <Route path="/register" element={<GuestRoute><Register /></GuestRoute>} />
      <Route path="/forgot-password" element={<GuestRoute><ForgotPassword /></GuestRoute>} />
      <Route path="/reset-password" element={<GuestRoute><ResetPassword /></GuestRoute>} />

      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <Layout><Dashboard /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/results"
        element={
          <ProtectedRoute>
            <Layout><Results /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/results/:resultId"
        element={
          <ProtectedRoute>
            <Layout><ResultDetail /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/history"
        element={
          <ProtectedRoute>
            <Layout><History /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/datasets"
        element={
          <ProtectedRoute>
            <Layout><Datasets /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/weather"
        element={
          <ProtectedRoute>
            <Layout><WeatherForecast /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/predictions"
        element={
          <ProtectedRoute>
            <Layout><CalamityPrediction /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/geotools"
        element={
          <ProtectedRoute>
            <Layout><GeoTools /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/change-analysis"
        element={
          <ProtectedRoute>
            <Layout><ChangeAnalysis /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/saved"
        element={
          <ProtectedRoute>
            <Layout><Saved /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <Layout><Settings /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/howto"
        element={
          <ProtectedRoute>
            <Layout><HowToUse /></Layout>
          </ProtectedRoute>
        }
      />
      <Route path="/404" element={<NotFound />} />
      <Route path="*" element={<Navigate to="/404" replace />} />
    </Routes>
  );
}