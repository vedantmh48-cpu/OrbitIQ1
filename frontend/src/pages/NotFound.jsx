import { Link } from "react-router-dom";
import { Satellite } from "lucide-react";
import Logo from "../components/Logo.jsx";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
      <Logo size={44} />
      <Satellite className="h-10 w-10 text-accent" opacity={0.4} />
      <h1 className="text-5xl font-extrabold text-white">404</h1>
      <p className="max-w-sm text-slate-400">
        The page you're looking for drifted into orbit. Let's get you back to solid ground.
      </p>
      <Link to="/" className="btn-primary">Return to SatQuery AI</Link>
    </div>
  );
}