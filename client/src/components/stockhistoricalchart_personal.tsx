"use client";

import { useState, useEffect } from "react";
import { getAuth } from "firebase/auth";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  TimeScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  ChartOptions,
} from "chart.js";
import "chartjs-adapter-date-fns";

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  TimeScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

interface Fundamentals {
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
}


interface StockCardProps {
  /** Stock symbol (for API lookup and chart label) */
  symbol: string;
  /** Optional display name (e.g. "Apple Inc.") */
  name?: string;
  /** Optional description text shown under the title */
  description?: string;
  /**
   * Optional callback for when the close (×) button is clicked.
   * You can use this to unmount or hide the card.
   */
  onClose?: () => void;
  /** Optional fundamentals data to display stock metrics */
  fundamentals?: Fundamentals;
}

/**
 * Retrieves the current Firebase ID token.
 */
async function getFirebaseIdToken(): Promise<string> {
  const auth = getAuth();
  const user = auth.currentUser;
  if (user) {
    console.log("User authenticated for chart fetch");
    return await user.getIdToken();
  }
  console.log("No authenticated user for chart fetch");
  return "";
}

/**
 * StockHistoricalChartPersonal Component
 *
 * Combines your card design with the chart functionality.
 * It fetches historical price data for the given stock symbol and displays it in a chart.
 * Additionally, it displays the passed fundamentals data.
 */
export default function StockHistoricalChartPersonal ({
  symbol,
  name,
  description,
  fundamentals,
  onClose,
}: StockCardProps) {
  const [historicalData, setHistoricalData] = useState<{ dates: string[]; prices: number[] }>({
    dates: [],
    prices: [],
  });
  const [loading, setLoading] = useState(true);

  // (Commented out fetch for historical data for brevity.)
  // useEffect(() => { ... }, [symbol]);



  useEffect(() => {
    async function fetchHistoricalData() {
      try {
        const token = await getFirebaseIdToken();
        const res = await fetch(
            `${process.env.NEXT_PUBLIC_API_URL}/api/stock/historical/${symbol}`,
            {
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
              },
            }
        );
        if (!res.ok) {
          throw new Error("Failed to fetch stock historical data");
        }
        const data = await res.json();
        // Expecting data to have the following structure: { dates: string[], prices: number[] }
        setHistoricalData(data);
      } catch (error) {
        console.error("Error fetching stock historical data:", error);
      } finally {
        setLoading(false);
      }
    }

    fetchHistoricalData();
  }, [symbol]);

  const chartData = {
    labels: historicalData.dates,
    datasets: [
      {
        label: "Daily Price at Close",
        data: historicalData.prices,
        borderColor: "rgba(75, 192, 192, 1)",
        backgroundColor: "rgba(75, 192, 192, 1)",
        fill: false,
        pointRadius: 0,
        tension: 0.1,
      },
    ],
  };

  const options: ChartOptions<"line"> = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: {
        type: "time",
        time: {
          parser: "yyyy-MM-dd",
          tooltipFormat: "PP",
          unit: "month" as const,
        },
        title: {
          display: true,
          text: "Date",
        },
      },
      y: {
        title: {
          display: true,
          text: "Price",
        },
      },
    },
  };

  return (
      <div className="bg-white shadow-lg p-4 max-w-xl w-[600px] max-h-[80vh] overflow-y-auto">
        {/* Header with title and close button */}

        <div className="flex justify-between items-start">
          <h1 className="text-2xl tracking-[-0.02em] font-semibold">{name || symbol}</h1>

          <button
          className="w-10 h-10 flex items-center justify-center transition-all hover:bg-gray-200 -mt-2"
          onClick={onClose}>
          <span className="relative w-5 h-5 flex items-center justify-center">
          {/* Thin "X" crossbars */}
          <span className="absolute w-[1.5px] h-5 bg-gray-500 rotate-45"></span>
          <span className="absolute w-[1.5px] h-5 bg-gray-500 -rotate-45"></span>
          </span>
          </button>
        </div>

        {/* Description */}
        <p className={`tracking-[-0.02em] flex-1 max-w-2xl`}>
          {description}
        </p>

        {/* Display Fundamentals Data if available */}

{fundamentals && (
  <div className="font-medium mt-4 grid grid-cols-2 tracking-[-0.02em] flex-1 max-w-2xl">
    <div>
      <p className="grid grid-cols-[65%_35%] gap-x-2">
        <span className="text-right">  Current Price:  </span>
        <span>{fundamentals.current_price || "-"}</span>
      </p>
      <p className="grid grid-cols-[65%_35%] gap-x-2">
        <span className="text-right"> 52 Week High: </span>
        <span> {fundamentals["52_week_high"] || "-"} </span>
      </p>
      <p className="grid grid-cols-[65%_35%] gap-x-2">
        <span className="text-right"> 52 Week Low: </span>
        <span> {fundamentals["52_week_low"] || "-"} </span>
      </p>
      <p className="grid grid-cols-[65%_35%] gap-x-2">
        <span className="text-right">Price/Earnings Ratio:</span>
        <span>{fundamentals.pe_ratio || "-"}</span>
      </p>
      <p className="grid grid-cols-[65%_35%] gap-x-2">
        <span className="text-right">Fwd. Price/Earnings: </span>
        <span>{fundamentals.forward_pe || "-"}</span>
      </p>
      <p className="grid grid-cols-[65%_35%] gap-x-2">
        <span className="text-right">Earnings/Share (12M): </span>
        <span>{fundamentals.eps_ttm || "-"}</span>
      </p>
      <p className="grid grid-cols-[65%_35%] gap-x-2">
        <span className="text-right">Return On Equity: </span>
        <span>{fundamentals.roe || "-"}</span>
      </p>
    </div>
    <div>
      <p className="grid grid-cols-2 gap-x-2">
        <span className="text-right">Return On Asset: </span>
        <span>{fundamentals.roa || "-"}</span>
      </p>
      <p className="grid grid-cols-2 gap-x-2">
        <span className="text-right">Sector:</span>
        <span>{fundamentals.sector || "-"} </span>
      </p>
      <p className="grid grid-cols-2 gap-x-2">
        <span className="text-right">Market Cap: </span>
        <span>{fundamentals.market_cap || "-"}</span>
      </p>
      <p className="grid grid-cols-2 gap-x-2">
        <span className="text-right">Beta: </span>
        <span>{fundamentals.beta || "-"}</span>
      </p>
      <p className="grid grid-cols-2 gap-x-2">
        <span className="text-right">Change: </span>
        <span>{fundamentals.change || "-"}</span>
      </p>
      <p className="grid grid-cols-2 gap-x-2">
        <span className="text-right">Volume: </span>
        <span>{fundamentals.volume || "-"}</span>
      </p>
      <p className="grid grid-cols-2 gap-x-2">
        <span className="text-right">Average Volume: </span>
        <span>{fundamentals.avg_volume || "-"}</span>
      </p>
    </div>
  </div>
)}

        {/* Price History Section */}
        <div className="mt-6">
          <h2 className="text-center text-lg font-semibold tracking-[-0.08em]">Price History</h2>
          <p className="text-center text-sm text-gray-500 tracking-[-0.08em]">source data: Alpha Vantage</p>

          {/* Navigation Links (non-functional placeholders)
          <div className="flex justify-center space-x-4 mt-2 text-blue-600 tracking-[-0.08em]">
            <a className="hover:underline" href="#">1W</a>
            <a className="hover:underline" href="#">1M</a>
            <a className="hover:underline" href="#">3M</a>
            <a className="hover:underline" href="#">6M</a>
            <a className="hover:underline" href="#">1Y</a>
            <a className="hover:underline" href="#">2Y</a>
            <a className="hover:underline" href="#">5Y</a>
            <a className="hover:underline" href="#">10Y</a>
            <a className="hover:underline" href="#">All</a>
          </div>
          */}

          {/* Chart Legend */}
          {/*
          <h3 className="text-center text-sm text-gray-600 tracking-[-0.08em]">Historical Prices</h3>
          <div className="flex justify-center items-center mt-2">
            <span className="bg-teal-500 h-2 w-8 inline-block mr-2"></span>
            <span className="text-gray-600 text-sm tracking-[-0.08em]">Daily Price at Close</span>
          </div>

          {/* Chart */}
          <div className="mt-4 w-full h-60">
            {loading ? (
                <div className="flex items-center justify-center h-full tracking-[-0.08em]">Loading stock data...</div>
            ) : (
                <Line data={chartData} options={options}/>
            )}
          </div>

        </div>
      </div>
  );
}
