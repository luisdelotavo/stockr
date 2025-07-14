"use client";

export default function Home() {
  return (
    <div className="flex flex-col items-start justify-center pl-20 h-full">
      {/* Header Section */}
      <header className="w-full">
        <h1 className="text-[10rem] tracking-[-0.1em] -ml-4">Stockr.</h1>
        <div className="flex justify-between items-center">
          <p className="text-2xl tracking-[-0.08em] flex-1 max-w-2xl font-medium">
            Personal Finances and Current Market Trends
          </p>
        </div>
      </header>

      {/* Content Section - Adding this structure to match transactions and agent */}
      <div className={`w-full tracking-[-0.08em]`}>
        <div className="mt-6 h-[400px] overflow-y-auto">
          {/* Your home page content will go here */}
          <div className="p-4">
            {/* You can add featured content, quick stats, or welcome messaging here */}
          </div>
        </div>
      </div>
    </div>
  );
}