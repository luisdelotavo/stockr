"use client";

import React, { useEffect, useState } from "react";
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "@/firebase/config";
import ProtectedRoute from "@/components/protectedroute";

interface Transaction {
  id: string;
  ticker: string;
  shares: number;
  price: number;
  transaction_type: string;
  created_at: string;
}

async function getFirebaseIdToken(): Promise<string | null> {
  return new Promise((resolve) => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      unsubscribe();
      if (user) {
        const token = await user.getIdToken();
        resolve(token);
      } else {
        resolve(null);
      }
    });
  });
}

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const [user, setUser] = useState<any>(null);
  // Adding search functionality to match watchlist
  const [searchTerm, setSearchTerm] = useState("");

  // Fetch transactions from backend
  const fetchTransactions = async () => {
    setLoading(true);
    setError("");
    try {
      const token = await getFirebaseIdToken();
      if (!token) throw new Error("User not authenticated");
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/transactions`,
        {
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );
      if (!res.ok) throw new Error("Failed to fetch transactions");
      const data = await res.json();
      setTransactions(data.transactions || []);
    } catch (err: any) {
      setError(err.message || "An error occurred while fetching transactions.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);
    });
    fetchTransactions();
    return () => unsubscribe();
  }, []);

  // Optional delete transaction function (if needed)
  const deleteTransaction = async (transactionId: string) => {
    try {
      const token = await getFirebaseIdToken();
      if (!token) throw new Error("User not authenticated");
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/transactions/${transactionId}`,
        {
          method: "DELETE",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );
      if (!res.ok) throw new Error("Failed to delete transaction");
      setTransactions((prev) => prev.filter((txn) => txn.id !== transactionId));
    } catch (err: any) {
      setError(err.message || "Error deleting transaction.");
    }
  };

  // Helper function: filter transactions based on search term
  const filterTransactions = (term: string, list: Transaction[]) => {
    if (!term.trim()) return list;
    return list.filter((item) =>
      item.ticker.toLowerCase().includes(term.toLowerCase())
    );
  };

  // Use the filtered transactions for rendering
  const filteredTransactions = filterTransactions(searchTerm, transactions);

  return (
    <ProtectedRoute>
      <div>
        <div className="flex flex-col items-start justify-center pl-20 h-full">
          {/* Header Section */}
          <header className="w-full">
            <h1 className="text-[10rem] tracking-[-0.1em] -ml-4">Transactions.</h1>
            <div className="flex justify-between items-center">
              <p className="text-2xl tracking-[-0.08em] flex-1 max-w-2xl">
                Transaction History (Last 15 Days)
              </p>
              <div className="flex items-center gap-1">
                {/* Search Input */}
                <div className="relative w-96">
                  <input
                    type="text"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="tracking-[-0.08em] flex-1 max-w-2xl w-full p-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400"
                    placeholder="Search..."
                  />
                  <i className="fas fa-times absolute right-3 top-3 text-gray-400 cursor-pointer"></i>
                </div>
              </div>
            </div>
          </header>

          {/* Controls & Table Section */}
          <div className={`w-full tracking-[-0.08em]`}>
            <div className="mt-6 h-[400px] overflow-y-auto">
              {loading ? (
                <div className="p-4 text-center">Loading transactions...</div>
              ) : error ? (
                <p className="text-red-500">{error}</p>
              ) : (
                <table className="min-w-full bg-white">
                  <thead className="bg-gray-50 sticky top-0 z-10">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Ticker
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Shares
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Price
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Type
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Date
                      </th>
                      {/*
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Action
                      </th>
                      */}
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {filteredTransactions.length > 0 ? (
                      filteredTransactions.map((txn) => (
                        <tr key={txn.id} className="border-t border-gray-200">
                          <td className="py-4 px-6">{txn.ticker}</td>
                          <td className="py-4 px-6">{txn.shares}</td>
                          <td className="py-4 px-6">${txn.price.toFixed(2)}</td>
                          <td
                            className={`py-4 px-6 ${
                              txn.transaction_type === "buy"
                                ? "text-green-600"
                                : "text-red-600"
                            }`}
                          >
                            {txn.transaction_type.toUpperCase()}
                          </td>
                          <td className="py-4 px-6">
                            {new Date(txn.created_at).toLocaleDateString()}
                          </td>
                          {/*
                          <td className="py-4 px-6">
                            <button
                              onClick={() => deleteTransaction(txn.id)}
                              className="text-red-500 hover:text-red-700 focus:outline-none"
                            >
                              Delete
                            </button>
                          </td>
                          */}
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td
                          colSpan={5}
                          className={`px-6 py-4 tracking-[-0.08em] text-center`}
                        >
                          No transactions found.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      </div>
    </ProtectedRoute>
  );
}