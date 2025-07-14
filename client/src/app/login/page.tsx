"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  signInWithEmailAndPassword,
  GoogleAuthProvider,
  signInWithPopup,
} from "firebase/auth";
import { auth } from "@/firebase/config";
import PublicRoute from "@/components/publicroute";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  // Email/password login
  const handleLogin = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try {
      const userCredentials = await signInWithEmailAndPassword(auth, email, password);
      const firebaseUid = userCredentials.user.uid;
    } catch (err: any) {
      setError(err.message);
    }
  };

  // Google login
  const handleGoogleLogin = async () => {
    const provider = new GoogleAuthProvider();
    try {
      await signInWithPopup(auth, provider);
      router.push("/");
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <PublicRoute>
      <div className="flex flex-col items-start justify-center pl-20 h-full">
        {/* Header Section */}
        <header className="w-full">
          <h1 className="text-[10rem] tracking-[-0.1em] -ml-4">Sign In.</h1>
          <div className="flex justify-between items-center">
            <p className="text-2xl tracking-[-0.08em] flex-1 max-w-2xl">
              Please login to continue to your account
            </p>
          </div>
        </header>

        {/* Content Section */}
        <div className={`w-full tracking-[-0.08em]`}>
          <div className="mt-6 h-[400px]">
            {/* Form Section */}
            <div>
              {error && <div className="text-red-500 text-l mb-4">{error}</div>}
              <form onSubmit={handleLogin} className="space-y-4">
                <div>
                  <label htmlFor="email" className="block text-l font-medium">
                    Email
                  </label>
                  <input
                    type="email"
                    id="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="w-[500px] p-2 mt-1 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-white"
                  />
                </div>
                <div>
                  <label htmlFor="password" className="block text-l font-medium">
                    Password
                  </label>
                  <input
                    type="password"
                    id="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="w-[500px] p-2 mt-1 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-white"
                  />
                </div>
                <button
                  type="submit"
                  className="w-[500px] py-2 bg-black text-white rounded-md hover:bg-gray-800 transition"
                >
                  Sign In
                </button>
              </form>

              <p className="text-l text-gray-600 mt-4">
                <a href="/forgot-password" className="underline">
                  Forgot password?
                </a>
              </p>

              {/* Commented out Google Sign-In button
              <button
                onClick={handleGoogleLogin}
                className="w-[500px] py-2 mt-4 bg-red-500 text-white rounded-md hover:bg-red-600 transition"
              >
                Sign in with Google
              </button>
              */}
            </div>
          </div>
        </div>
      </div>
    </PublicRoute>
  );
}