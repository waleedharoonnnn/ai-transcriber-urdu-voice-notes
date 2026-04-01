import React, { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function SignupPage() {
  const { isAuthenticated, signup } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const navigate = useNavigate();

  if (isAuthenticated) return <Navigate to="/" replace />;

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await signup(email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.error ||
        err?.message ||
        "Signup failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-950 p-4">
      <div className="w-full max-w-md bg-zinc-900 border border-zinc-800 rounded-xl p-6">
        <h1 className="text-2xl font-semibold text-center text-white">
          Urdu Voice Notes
        </h1>
        <p className="text-center text-zinc-400 mt-2">Create your account</p>

        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <div>
            <label className="block text-sm text-zinc-300">Email</label>
            <input
              className="mt-1 w-full rounded-lg bg-zinc-950 border border-zinc-800 text-white px-3 py-2 outline-none focus:border-zinc-600"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="block text-sm text-zinc-300">Password</label>
            <input
              className="mt-1 w-full rounded-lg bg-zinc-950 border border-zinc-800 text-white px-3 py-2 outline-none focus:border-zinc-600"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              placeholder="At least 6 characters"
            />
          </div>

          {error ? (
            <div className="text-sm text-red-300 bg-red-950/40 border border-red-900 rounded-lg px-3 py-2">
              {String(error)}
            </div>
          ) : null}

          <button
            disabled={loading}
            className="w-full rounded-lg bg-white text-black font-medium py-2 disabled:opacity-60"
            type="submit"
          >
            {loading ? "Creating…" : "Sign up"}
          </button>
        </form>

        <div className="mt-5 text-center text-sm text-zinc-400">
          Already have an account?{" "}
          <Link className="text-white underline" to="/login">
            Sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
