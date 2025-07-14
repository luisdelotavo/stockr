"use client";

import { useState, useEffect } from "react";
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "@/firebase/config";
import { getAuth } from "firebase/auth";
import ProtectedRoute from "@/components/protectedroute";
import PortfolioTable from "@/components/PortfolioTable";
import DoughnutGraph from "@/components/DoughnutGraph";
import PortfolioGrowthChart from "@/components/PortfolioGrowthChart";

// Define interfaces for data structures
interface PortfolioEntry {
  ticker: string;
  shares: number;
  book_value: number;
  average_cost: number;
  market_price?: number | null;
  market_value?: number | null;
  portfolio_percentage?: number;
  color?: string;
  total_value?: number;
}

interface HistoryDataPoint {
  date: string;
  value: number;
  market_value?: number;
}

// Helper function to get Firebase token
async function getFirebaseIdToken(): Promise<string | null> {
  const auth = getAuth();
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

// Helper function to process requests in batches with concurrency limit
async function processBatchRequests<T, R>(
  items: T[],
  processor: (item: T, index: number) => Promise<R>,
  concurrency: number = 3,
  fallbackValue?: (item: T, index: number, error: any) => R
): Promise<R[]> {
  const results: R[] = [];
  
  for (let i = 0; i < items.length; i += concurrency) {
    const batch = items.slice(i, i + concurrency);
    const batchPromises = batch.map(async (item, batchIndex) => {
      try {
        return await processor(item, i + batchIndex);
      } catch (err) {
        console.error(`Error processing item at index ${i + batchIndex}:`, err);
        if (fallbackValue) {
          return fallbackValue(item, i + batchIndex, err);
        }
        throw err;
      }
    });
    
    const batchResults = await Promise.allSettled(batchPromises);
    for (const result of batchResults) {
      if (result.status === 'fulfilled') {
        results.push(result.value);
      }
    }
  }
  
  return results;
}

export default function HomePage() {
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const [portfolioId, setPortfolioId] = useState<string | null>(null);
  const [portfolioData, setPortfolioData] = useState<PortfolioEntry[]>([]);
  const [historyData, setHistoryData] = useState<HistoryDataPoint[]>([]);
  const [totalValue, setTotalValue] = useState<number>(0);
  const [refreshCounter, setRefreshCounter] = useState(0);

  // Gray shades for consistent coloring
  const grayShades = [
    "#F0F0F0", "#E3E3E3", "#D7D7D7", "#CACACA",
    "#BDBDBD", "#B1B1B1", "#A4A4A4", "#989898",
    "#8B8B8B", "#7E7E7E", "#727272", "#656565",
    "#585858", "#4C4C4C", "#3F3F3F", "#333333",
    "#262626", "#191919", "#0D0D0D", "#000000",
  ];

  // Fetch portfolio ID when user logs in
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      setUser(firebaseUser);
      if (firebaseUser && !portfolioId) {
        await fetchPortfolioId();
      }
    });

    return () => unsubscribe();
  }, []); // Runs only once when component mounts

  // Fetch all data when portfolioId changes or refresh is triggered
  useEffect(() => {
    if (portfolioId) {
      fetchAllData();
    }
  }, [portfolioId, refreshCounter]);

  // Fetch portfolio ID
  const fetchPortfolioId = async () => {
    try {
      setLoading(true);
      const token = await getFirebaseIdToken();
      if (!token) {
        console.error("User not authenticated.");
        setLoading(false);
        return;
      }

      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/portfolio/id`,
        {
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!res.ok) {
        throw new Error("Failed to fetch portfolio ID");
      }

      const data = await res.json();
      setPortfolioId(data.portfolio_id);
    } catch (error: any) {
      console.error("Error fetching portfolio ID:", error);
      setError("Error fetching portfolio ID: " + error.message);
      setLoading(false);
    }
  };

  // Fetch all data in parallel
  const fetchAllData = async () => {
    if (!portfolioId) return;

    try {
      setLoading(true);
      setError("");

      // Fetch both portfolio data and history data in parallel
      const [portfolioWithMarketValues, historyResponse] = await Promise.all([
        fetchPortfolioWithMarketData(),
        fetchPortfolioHistory()
      ]);

      // Set the state with fetched data
      setPortfolioData(portfolioWithMarketValues);

      // Set loading to false after all data is fetched
      setLoading(false);
    } catch (err: any) {
      console.error("Error fetching data:", err);
      setError(err.message || "An error occurred while loading your portfolio");
      setLoading(false);
    }
  };

  // Fetch portfolio with market data
  const fetchPortfolioWithMarketData = async () => {
    const token = await getFirebaseIdToken();
    if (!token) throw new Error("Authentication required");

    // Fetch portfolio data
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/api/portfolio/${portfolioId}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      }
    );

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || "Failed to fetch portfolio data");
    }

    const data = await response.json();

    // Fetch market data for each asset with batch processing (limit concurrency)
    const portfolioWithMarketValues = await processBatchRequests(
      data.portfolio,
      async (entry: PortfolioEntry, index: number) => {
        const marketData = await fetchMarketPrice(entry.ticker);
        const marketPrice = marketData.market_price !== "N/A" ? Number(marketData.market_price) : null;
        const shares = Number(entry.shares) || 0;
        const marketValue = marketPrice !== null ? marketPrice * shares : null;

        return {
          ...entry,
          market_price: marketPrice,
          market_value: marketValue,
          color: grayShades[index % grayShades.length] // Assign a color from the gray shades
        };
      },
      3, // Limit to 3 concurrent requests
      (entry: PortfolioEntry, index: number, error: any) => {
        // Fallback value when market price fetch fails
        console.warn(`Using fallback for ${entry.ticker} due to error:`, error);
        return {
          ...entry,
          market_price: null,
          market_value: null,
          color: grayShades[index % grayShades.length]
        };
      }
    );

    // Calculate portfolio percentages
    return calculatePortfolioPercentage(portfolioWithMarketValues);
  };

  // Fetch market price for a ticker with timeout and retry logic
  const fetchMarketPrice = async (ticker: string, retries: number = 1) => {
    const token = await getFirebaseIdToken();
    if (!token) throw new Error("Authentication required");

    for (let attempt = 0; attempt < retries; attempt++) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/api/stock/current/${ticker}`,
          {
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            signal: controller.signal,
          }
        );

        clearTimeout(timeoutId);

        if (!response.ok) {
          throw new Error(`Failed to fetch market price for ${ticker}`);
        }

        const data = await response.json();
        
        // If the API returned an error, handle it gracefully
        if (data.error) {
          console.warn(`API returned error for ${ticker}: ${data.error}`);
          return { ticker, market_price: "N/A", error: data.error };
        }

        return data;
      } catch (error: any) {
        if (error.name === 'AbortError') {
          console.warn(`Request timeout for ${ticker}`);
          if (attempt < retries - 1) continue; // Retry on timeout
          return { ticker, market_price: "N/A", error: "Request timeout" };
        }
        
        if (attempt < retries - 1) {
          console.warn(`Attempt ${attempt + 1} failed for ${ticker}, retrying...`);
          continue;
        }
        
        console.error(`Error fetching market price for ${ticker}:`, error);
        return { ticker, market_price: "N/A", error: error.message };
      }
    }
  };

  // Fetch portfolio history
  const fetchPortfolioHistory = async () => {
    const token = await getFirebaseIdToken();
    if (!token) throw new Error("Authentication required");

    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/api/portfolio/${portfolioId}/history`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      }
    );

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || "Failed to fetch portfolio history");
    }

    const data = await response.json();

    // Process history data
    if (data.history && Array.isArray(data.history)) {
      const processedData = data.history.map((item: { date: any; market_value: any; value: any; }) => ({
        date: item.date,
        value: item.market_value !== undefined ? item.market_value : item.value
      }));

      setHistoryData(processedData);

      // Update the total value if it's available
      if (data.total_value) {
        setTotalValue(data.total_value);

        // Update the last data point if needed
        if (processedData.length > 0) {
          const lastValue = processedData[processedData.length - 1].value;
          if (Math.abs(lastValue - data.total_value) > 1) {
            processedData[processedData.length - 1].value = data.total_value;
            setHistoryData([...processedData]);
          }
        }
      }
    }

    return data;
  };

  // Calculate portfolio percentage for each asset
  const calculatePortfolioPercentage = (portfolio: PortfolioEntry[]): PortfolioEntry[] => {
    // Calculate total market value of all assets with valid market values
    const totalMarketValue = portfolio.reduce((acc, entry) => {
      if (entry.market_value != null && !isNaN(Number(entry.market_value))) {
        return acc + entry.market_value;
      }
      return acc;
    }, 0);

    // If there's no valid market value, fall back to book value
    const totalValue = totalMarketValue > 0
      ? totalMarketValue
      : portfolio.reduce((acc, entry) => acc + entry.book_value, 0);

    // Update the total value state
    setTotalValue(totalValue);

    return portfolio.map((entry) => {
      // Use market value for percentage calculation if available, otherwise use book value
      const valueForPercentage = (entry.market_value != null && !isNaN(Number(entry.market_value)))
        ? entry.market_value
        : entry.book_value;

      return {
        ...entry,
        portfolio_percentage: totalValue > 0 ? (valueForPercentage / totalValue) * 100 : 0
      };
    });
  };

  // Handle page refresh
  const handlePageRefresh = () => {
    setRefreshCounter(prev => prev + 1);
  };

  // Handle refresh of market prices
  const handleRefreshMarketPrices = async () => {
    if (portfolioData.length === 0) return;

    try {
      setLoading(true);
      const updatedPortfolio = await processBatchRequests(
        portfolioData,
        async (entry: PortfolioEntry) => {
          const marketData = await fetchMarketPrice(entry.ticker);
          const marketPrice = marketData.market_price !== "N/A" ? Number(marketData.market_price) : null;
          const marketValue = marketPrice !== null ? marketPrice * entry.shares : null;

          return {
            ...entry,
            market_price: marketPrice,
            market_value: marketValue
          };
        },
        3, // Limit to 3 concurrent requests
        (entry: PortfolioEntry, index: number, error: any) => {
          // Fallback: keep the old data if fetching fails
          console.warn(`Refresh failed for ${entry.ticker}, keeping old data:`, error);
          return entry;
        }
      );

      // Recalculate portfolio percentages and update state
      setPortfolioData(calculatePortfolioPercentage(updatedPortfolio));
    } catch (err) {
      console.error("Error refreshing market prices:", err);
    } finally {
      setLoading(false);
    }
  };

  // Render loading spinner for the entire page
  if (loading) {
    return (
      <ProtectedRoute>
        <div className="flex flex-col items-center pt-64 min-h-screen">
          <img src="/spinner.svg" alt="Loading spinner..." className="w-36 h-36" />
          <p className={`mt-4 text-gray-600 tracking-[-0.08em]`}>Loading your portfolio...</p>
        </div>
      </ProtectedRoute>
    );
  }

  // Render error state
  if (error) {
    return (
      <ProtectedRoute>
        <div className="flex flex-col items-center justify-center h-full">
          <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 rounded">
            <p className={`font-medium`}>Error</p>
            <p className={``}>{error}</p>
            <button
              className="mt-4 bg-red-500 text-white px-4 py-2 rounded hover:bg-red-600 transition"
              onClick={handlePageRefresh}
            >
              Retry
            </button>
          </div>
        </div>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <div className="flex flex-col items-start pl-20 h-full pt-24">
        <div className="w-full grid grid-cols-5 mb-4">
          {/* Left chart - Growth Chart (60%) */}
          <div className="col-span-3 bg-white overflow-hidden h-[300px]">
            <PortfolioGrowthChart
              historyData={historyData}
              totalValue={totalValue}
            />
          </div>

          {/* Right chart - Doughnut Graph (40%) */}
          <div className="col-span-2 bg-white overflow-hidden h-[300px]">
            <DoughnutGraph
              portfolioData={portfolioData}
              totalValue={totalValue}
            />
          </div>
        </div>

        {/* Portfolio Table Section */}
        <div className={`w-11/12 tracking-[-0.08em] bg-white flex-1 overflow-hidden`}>
          <PortfolioTable
            portfolioData={portfolioData}
            portfolioId={portfolioId}
            onAssetAdded={handlePageRefresh}
            onRefreshMarketPrices={handleRefreshMarketPrices}
          />
        </div>
      </div>
    </ProtectedRoute>
  );
}