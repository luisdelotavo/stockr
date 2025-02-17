"use client";

import React, { useState, useEffect, useRef } from "react";
import { getAuth } from "firebase/auth";
import SellAssetModal from "@/components/SellAssetModal";
import PurchaseAssetModal from "@/components/PurchaseAssetModal";
import { EllipsisVerticalIcon } from "@heroicons/react/24/outline";

// Example font class (if using a similar font as before)
const kaisei = { className: "font-kaisei" };

const COLORS = ["#FF6384", "#36A2EB", "#FFCE56", "#4BC0C0", "#9966FF", "#FF9F40"];

interface PortfolioEntry {
  ticker: string;
  shares: number;
  average_cost: number;
  book_value: number;
  market_value?: number | null;
  portfolio_percentage: number;
  color?: string;
}

interface PortfolioTableProps {
  refresh: number;
  portfolioId: string | null;
  onAssetAdded: () => void;
}

async function getFirebaseIdToken(): Promise<string> {
  const auth = getAuth();
  return new Promise((resolve, reject) => {
    const unsubscribe = auth.onAuthStateChanged(async (user) => {
      unsubscribe();
      if (user) {
        const token = await user.getIdToken();
        resolve(token);
      } else {
        resolve("");
      }
    }, reject);
  });
}

const PortfolioTable: React.FC<PortfolioTableProps> = ({ refresh, portfolioId, onAssetAdded }) => {
  const [portfolio, setPortfolio] = useState<PortfolioEntry[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const [selectedAsset, setSelectedAsset] = useState<PortfolioEntry | null>(null);
  const [isSellModalOpen, setIsSellModalOpen] = useState<boolean>(false);
  const [dropdownOpen, setDropdownOpen] = useState<string | null>(null);
  const [isAssetModalOpen, setIsAssetModalOpen] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Fetch portfolio data
  const fetchPortfolio = async () => {
    setLoading(true);
    setError("");
    try {
      const token = await getFirebaseIdToken();
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/portfolio/${portfolioId}`,
        {
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );
      if (!res.ok) throw new Error("Failed to fetch portfolio");
      const data = await res.json();
      setPortfolio(calculatePortfolioPercentage(data.portfolio));
    } catch (err: any) {
      setError(err.message || "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  // Fetch market prices for portfolio assets
  const fetchMarketPrices = async () => {
    if (portfolio.length === 0) return;
    setLoading(true);
    const updatedPortfolio = await Promise.all(
      portfolio.map(async (entry) => {
        try {
          const token = await getFirebaseIdToken();
          const response = await fetch(
            `${process.env.NEXT_PUBLIC_API_URL}/api/stock/current/${entry.ticker}`,
            {
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
              },
            }
          );
          if (!response.ok) throw new Error("Failed to fetch market price");
          const data = await response.json();
          const price = data.market_price !== "N/A" ? data.market_price : null;
          return { ...entry, market_value: price };
        } catch {
          return { ...entry, market_value: null };
        }
      })
    );
    setPortfolio(updatedPortfolio);
    setLoading(false);
  };

  // Calculate portfolio percentage for each asset
  const calculatePortfolioPercentage = (portfolio: PortfolioEntry[]): PortfolioEntry[] => {
    const totalBookValue = portfolio.reduce((acc, entry) => acc + entry.book_value, 0);
    return portfolio.map((entry, index) => ({
      ...entry,
      portfolio_percentage: totalBookValue > 0 ? (entry.book_value / totalBookValue) * 100 : 0,
      color: COLORS[index % COLORS.length],
    }));
  };

  const openSellModal = (asset: PortfolioEntry) => {
    setSelectedAsset(asset);
    setIsSellModalOpen(true);
    setDropdownOpen(null);
  };

  const toggleDropdown = (ticker: string, event: React.MouseEvent) => {
    event.stopPropagation();
    setDropdownOpen((prev) => (prev === ticker ? null : ticker));
  };

  const handleAssetSold = async () => {
    await fetchPortfolio();
    setIsSellModalOpen(false);
  };

  // Called after an asset is added via the PurchaseAssetModal
  const handleAssetAdded = async () => {
    setIsAssetModalOpen(false);
    onAssetAdded(); // Let the parent know so it can refresh other parts (e.g. DoughnutGraph)
    await fetchPortfolio();
  };

  useEffect(() => {
    if (!portfolioId) return;
    fetchPortfolio();
  }, [refresh, portfolioId]);

  useEffect(() => {
    if (portfolio.length > 0) {
      fetchMarketPrices();
    }
  }, [portfolioId]);

  if (!portfolioId) return <p>Loading portfolio...</p>;
  if (loading) return <p className="p-4 text-center">Loading portfolio...</p>;
  if (error) return <p className="text-red-500 p-4">Error: {error}</p>;
  if (portfolio.length === 0)
    return <p className="p-4 text-center">No assets in portfolio.</p>;

  return (
    <div className={`${kaisei.className} w-full tracking-[-0.08em]`}>
      {/* Add Asset & Refresh Buttons */}
      <div className="mt-4 space-y-2">
        <button
          onClick={() => setIsAssetModalOpen(true)}
          className="w-full add-asset-button"
        >
          + Add Asset
        </button>
        <button
          onClick={fetchMarketPrices}
          className="w-full bg-gray-200 text-gray-700 py-2 hover:bg-gray-300 transition duration-300"
        >
          Refresh Market Values
        </button>
      </div>

      {/* Scrollable Table Section */}
      <div className="mt-6 h-[400px] overflow-y-auto">
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
                Avg. Cost
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Book Value
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Market Value
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Portfolio %
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {portfolio.map((entry, index) => (
              <tr key={index} className="border-t border-gray-200">
                <td className="py-4 px-6">{entry.ticker}</td>
                <td className="py-4 px-6">{entry.shares}</td>
                <td className="py-4 px-6">${entry.average_cost.toFixed(2)}</td>
                <td className="py-4 px-6">${entry.book_value.toFixed(2)}</td>
                <td className="py-4 px-6">
                  {entry.market_value != null && !isNaN(Number(entry.market_value))
                    ? `$${Number(entry.market_value).toFixed(2)}`
                    : "N/A"}
                </td>
                <td className="py-4 px-6">
                  <div>
                    <span>{entry.portfolio_percentage.toFixed(2)}%</span>
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className="h-2 rounded-full transition-all duration-300"
                        style={{ width: `${entry.portfolio_percentage}%`, backgroundColor: entry.color }}
                      ></div>
                    </div>
                  </div>
                </td>
                <td className="py-4 px-9 relative text-left">
                  <button
                    onClick={(event) => toggleDropdown(entry.ticker, event)}
                    className="text-gray-500 hover:text-gray-700 focus:outline-none bg-white font-light"
                  >
                    <EllipsisVerticalIcon className="w-5 h-5" />
                  </button>
                  {dropdownOpen === entry.ticker && (
                    <div className="absolute right-0 mt-2 w-32 bg-white border border-gray-200 shadow-lg z-50">
                      <ul>
                        <li>
                          <button
                            onClick={() => openSellModal(entry)}
                            className="block px-4 py-2 text-black tracking-[-0.08em] hover:bg-gray-100 w-full text-left"
                          >
                            Sell
                          </button>
                        </li>
                        <li>
                          <button
                            className="block px-4 py-2 text-black tracking-[-0.08em] hover:bg-gray-100 w-full text-left"
                          >
                            Explore
                          </button>
                        </li>
                      </ul>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {isSellModalOpen && selectedAsset && (
              <SellAssetModal
                onClose={() => setIsSellModalOpen(false)}
                onAssetSold={handleAssetSold}
                initialTicker={selectedAsset.ticker}
                maxShares={selectedAsset.shares}
                portfolioId={portfolioId ?? ""}
              />
            )}
          </tbody>
        </table>
      </div>

      {/* Purchase Asset Modal */}
      {isAssetModalOpen && portfolioId && (
        <PurchaseAssetModal
          onClose={() => setIsAssetModalOpen(false)}
          onAssetAdded={handleAssetAdded}
          portfolioId={portfolioId}
        />
      )}

      <style jsx>{`
        .add-asset-button {
          width: 100%;
          background-color: #f5f5f5; /* Light grey to match table header */
          color: #333; /* Darker text for contrast */
          padding: 12px 0;
          font-size: 1rem;
          font-weight: bold;
          border: none;
          border-radius: 5px;
          margin-top: 5px;
          margin-bottom: 5px;
          text-align: center;
          cursor: pointer;
          transition: background 0.2s ease-in-out;
        }

        .add-asset-button:hover {
          background-color: #e0e0e0; /* Slightly darker on hover */
        }

        .add-asset-button:active {
          background-color: #d6d6d6; /* Even darker when clicked */
        }
      `}</style>
    </div>
  );
};

export default PortfolioTable;
