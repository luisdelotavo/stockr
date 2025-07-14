"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createUserWithEmailAndPassword } from "firebase/auth";
import { auth } from "@/firebase/config";
import PublicRoute from "@/components/publicroute";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const handleRegister = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try {
      // Create Firebase auth user
      const userCredential = await createUserWithEmailAndPassword(auth, email, password);
      const firebaseUid = userCredential.user.uid;

      // Call your API to create a user in PostgreSQL database
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ firebase_uid: firebaseUid }),
      });

      const responseData = await response.json();
      if (!response.ok) {
        throw new Error(responseData.error || "Registration failed");
      }

      setMessage("Registration successful! Redirecting...");
      setTimeout(() => router.push("/login"), 1500);
    } catch (err: any) {
      setError(err.message || "Registration failed");
    }
  };

  return (
    <PublicRoute>
      <div className="flex flex-col items-start justify-center pl-20 h-full">
        {/* Header Section */}
        <header className="w-full">
          <h1 className="text-[10rem] tracking-[-0.1em] -ml-4">Register.</h1>
          <div className="flex justify-between items-center">
            <p className="text-2xl tracking-[-0.08em] flex-1 max-w-2xl">
              Create your account to continue to our platform
            </p>
          </div>
        </header>

        {/* Content Section */}
        <div className={`w-full tracking-[-0.08em]`}>
          <div className="mt-6 h-[400px]">
            {/* Form Section */}
            <div>
              {/* Display error or success messages */}
              {error && <div className="text-red-500 text-l mb-4">{error}</div>}
              {message && <div className="text-green-500 text-l mb-4">{message}</div>}
              <form onSubmit={handleRegister} className="space-y-4">
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
                    className="w-[500px] p-2 mt-1 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400"
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
                    className="w-[500px] p-2 mt-1 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400"
                  />
                </div>
                <button
                  type="submit"
                  className="w-[500px] py-2 bg-black text-white rounded-md hover:bg-gray-800 transition"
                >
                  Register
                </button>
              </form>
              <p className="text-l text-gray-600 mt-4">
                Already have an account?{" "}
                <a href="/login" className="underline">
                  Login
                </a>
              </p>
            </div>
          </div>
        </div>
      </div>
    </PublicRoute>
  );
}