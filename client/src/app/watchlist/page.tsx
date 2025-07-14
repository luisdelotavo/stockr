"use client";

import React, { useState, useEffect, FormEvent } from "react";
import { getAuth } from "firebase/auth";
import ProtectedRoute from "@/components/protectedroute";
import StockHistoricalChart from "@/components/stockhistoricalchart";
import CryptoHistoricalChart from "@/components/cryptohistoricalchart";
import AddStock from "@/components/addstock"; // New component import
import { createPortal } from "react-dom";

interface WatchlistItem {
  ticker: string;
  fundamentals?: {
    market_cap: string;
    company?: string;
    sector?: string;
    current_price?: string;
    change?: string;
    volume?: string;
    avg_volume?: string;
    "52_week_high"?: string;
    "52_week_low"?: string;
    pe_ratio?: string;
    lt_debt_equity?: string;
    price_fcf?: string;
    operating_margin?: string;
    beta?: string;
    forward_pe?: string;
    eps_this_year?: string;
    eps_ttm?: string;
    peg_ratio?: string;
    roe?: string;
    roa?: string;
    profit_margin?: string;
    sales?: string;
    debt_eq?: string;
    current_ratio?: string;
  };
  description?: string;
}

// This function retrieves your Firebase ID token. Adjust according to your Firebase auth logic.
async function getFirebaseIdToken(): Promise<string> {
  const auth = getAuth();
  return new Promise((resolve, reject) => {
    const unsubscribe = auth.onAuthStateChanged(async (user) => {
      unsubscribe(); // stop listening after the first change
      if (user) {
        const token = await user.getIdToken();
        resolve(token);
      } else {
        resolve("");
      }
    }, reject);
  });
}

export default function Home() {
  const [showAddStockModal, setShowAddStockModal] = useState(false);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [tickerInput, setTickerInput] = useState("");
  // New state for search term
  const [searchTerm, setSearchTerm] = useState("");
  // State to track which row's dropdown is open (using ticker as identifier)
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  // State to track which stock is being explored
  const [selectedStock, setSelectedStock] = useState<WatchlistItem | null>(null);
  const [dropdownPosition, setDropdownPosition] = useState<{ top: number; left: number }>({ top: 0, left: 0 });

  // Fetch the current watchlist from the backend
  useEffect(() => {
    const fetchWatchlist = async () => {
      try {
        const token = await getFirebaseIdToken();
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/api/watchlist/stocks`,
          {
            method: "GET",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
          }
        );
        if (!response.ok) {
          throw new Error("Failed to fetch watchlist");
        }
        const data = await response.json();
        setWatchlist(data);
      } catch (error) {
        console.error("Error fetching watchlist:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchWatchlist();
  }, []);

  // Helper function: filter watchlist based on search term
  const filterWatchlist = (term: string, list: WatchlistItem[]) => {
    return list.filter((item) =>
      item.ticker.toLowerCase().includes(term.toLowerCase())
    );
  };

  // Use the filtered watchlist for rendering
  const filteredWatchlist = filterWatchlist(searchTerm, watchlist);

  // Handler to add a stock using the ticker from AddStock component
  const handleAddStockTicker = async (ticker: string) => {
    if (!ticker.trim()) {
      alert("Please enter a ticker symbol");
      return;
    }
    try {
      const token = await getFirebaseIdToken();
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/watchlist`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ ticker }),
        }
      );
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Failed to add stock");
      }
      // Re-fetch the updated watchlist after successfully adding the stock
      const updatedResponse = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/watchlist/stocks`,
        {
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );
      const updatedWatchlist = await updatedResponse.json();
      setWatchlist(updatedWatchlist);
      setShowAddStockModal(false);
    } catch (error) {
      console.error("Error adding stock:", error);
      alert("Error adding stock: " + error);
    }
  };

  // Handler to delete a stock by calling the DELETE API endpoint
  const handleDeleteStock = async (ticker: string) => {
    try {
      const token = await getFirebaseIdToken();
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/watchlist/${ticker.toUpperCase()}`,
        {
          method: "DELETE",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Failed to delete stock");
      }
      // Remove the deleted ticker from the local watchlist state
      setWatchlist((prev) => prev.filter((item) => item.ticker !== ticker));
      setOpenDropdown(null);
    } catch (error) {
      console.error("Error deleting stock:", error);
      alert("Error deleting stock: " + error);
    }
  };

  // Toggle the dropdown for a given ticker
  const toggleDropdown = (ticker: string) => {
    setOpenDropdown((prev) => (prev === ticker ? null : ticker));
  };

  return (
    <ProtectedRoute>
      <div>
        <div className="flex flex-col items-start justify-center pl-20 h-full">
          {/* Header Section */}
          <header className="w-full">
            <h1 className="text-[10rem] tracking-[-0.1em] -ml-4">Watchlist.</h1>
            <div className="flex justify-between items-center">
              <p className="text-2xl tracking-[-0.08em] flex-1 max-w-2xl">
                Add stocks to your watchlist to track companies and get their latest metrics
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
                {/* This button now triggers the AddStock modal */}
                <button
                  onClick={() => setShowAddStockModal(true)}
                  className="w-10 h-10 flex items-center justify-center border rounded transition-all"
                >
                  <span className="relative w-5 h-5 flex items-center justify-center">
                    <i className="fas fa-plus text-gray-400"></i>
                  </span>
                </button>
              </div>
            </div>
          </header>

          {/* Controls & Table Section */}
          <div className={`w-full tracking-[-0.08em]`}>
            <div className="mt-6 h-[400px] overflow-y-auto">
              <table className="min-w-full bg-white">
                <thead className="bg-gray-50 sticky top-0 z-10">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Symbol
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Price
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Change
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Volume
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Avg. Volume
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Action
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {loading ? (
                    <tr>
                      <td colSpan={6} className="p-4 text-center">
                        <img src="/spinner.svg" alt="Loading spinner ..." className="mx-auto w-8 h-8"/>
                      </td>
                    </tr>
                  ) : (
                    filteredWatchlist.length > 0 ? (
                      filteredWatchlist.map((item) => (
                        <tr key={item.ticker} className="border-t border-gray-200">
                          <td className="py-4 px-6">{item.ticker}</td>
                          <td className="py-4 px-6">
                            {item.fundamentals?.current_price || "N/A"}
                          </td>
                          <td className="py-4 px-6 text-green-500">
                            {item.fundamentals?.change || "N/A"}
                          </td>
                          <td className="py-4 px-6">
                            {item.fundamentals?.volume || "N/A"}
                          </td>
                          <td className="py-4 px-6">
                            {item.fundamentals?.avg_volume || "N/A"}
                          </td>
                          <td className="py-4 px-9 relative text-left">
                            <button
                              onClick={(e) => {
                                const rect = e.currentTarget.getBoundingClientRect();
                                setDropdownPosition({ top: rect.bottom, left: rect.left });
                                toggleDropdown(item.ticker);
                              }}
                              className="text-gray-500 hover:text-gray-700 focus:outline-none bg-white font-light"
                            >
                              &#8942;
                            </button>
                            {openDropdown === item.ticker &&
                              createPortal(
                                <ul
                                  style={{
                                    position: "fixed",
                                    top: dropdownPosition.top,
                                    left: dropdownPosition.left,
                                  }}
                                  className="w-32 bg-white -translate-x-2 border-gray-200 shadow-lg z-50"
                                >
                                  <li>
                                    <a
                                      href="#"
                                      className="block px-4 py-2 text-black tracking-[-0.08em] hover:bg-gray-100"
                                      onClick={(e) => {
                                        e.preventDefault();
                                        handleDeleteStock(item.ticker);
                                      }}
                                    >
                                      Delete
                                    </a>
                                  </li>
                                  <li>
                                    <a
                                      href="#"
                                      className="block px-4 py-2 text-black tracking-[-0.08em] hover:bg-gray-100"
                                      onClick={(e) => {
                                        e.preventDefault();
                                        setSelectedStock(item);
                                        setOpenDropdown(null);
                                      }}
                                    >
                                      Explore
                                    </a>
                                  </li>
                                </ul>,
                                document.body
                              )}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={6} className={`px-6 py-4 tracking-[-0.08em] text-center`}>
                          No stocks in your watchlist.
                        </td>
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Modal Overlay for StockHistoricalChart */}
        {selectedStock && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="relative p-4">
              <StockHistoricalChart
                symbol={selectedStock.ticker}
                name={selectedStock.fundamentals?.company || selectedStock.ticker}
                description={selectedStock.description || "No description available."}
                fundamentals={selectedStock.fundamentals}
                onClose={() => setSelectedStock(null)}
              />
            </div>
          </div>
        )}

        {/* Modal Overlay for Adding a Stock */}
        {showAddStockModal && (
          <AddStock
            onClose={() => setShowAddStockModal(false)}
            onSubmit={handleAddStockTicker}
          />
        )}
      </div>
    </ProtectedRoute>
  );
}
