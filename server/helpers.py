# helpers.py
import pandas as pd
import json
import csv
import re
import openai
import time
import os
import requests
import yfinance as yf

from datetime import datetime, timedelta
from finvizfinance.quote import finvizfinance
from finvizfinance.screener.ticker import Ticker
from finvizfinance.calendar import Calendar
from models import db, User, Watchlist, Portfolio, Transaction, PortfolioHolding, UserThread
from datetime import datetime, timedelta


def convert_data(data):
    """Convert a pandas DataFrame to a dictionary if needed."""
    if isinstance(data, pd.DataFrame):
        return data.to_dict(orient="records")
    return data


def safe_convert(value):
    """Try to JSON-serialize a value; if it fails, return its string representation."""
    try:
        json.dumps(value)
        return value
    except (TypeError, OverflowError):
        return str(value)


def parse_csv_with_mapping(stream):
    """Parse CSV data using flexible header mapping"""
    header_mapping = {
        "ticker": ["ticker", "symbol", "security", "stock"],
        "shares": ["shares", "quantity", "units", "amount"],
        "price": ["price", "cost", "unit price", "price per share"],
        "transaction_type": ["transaction type", "type", "action", "activity", "transaction"],
        "date": ["date", "trade date", "transaction date"],
    }

    stream.seek(0)

    # Read the first line to get headers
    header_line = stream.readline().strip()
    stream.seek(0)
    csv_reader = csv.DictReader(stream)

    # Clean fieldnames to remove BOM and extra whitespace
    if csv_reader.fieldnames:
        cleaned_fieldnames = []
        for field in csv_reader.fieldnames:
            # Remove BOM (UTF-8 BOM shows as \ufeff)
            cleaned_field = field.replace("\ufeff", "").strip()
            cleaned_fieldnames.append(cleaned_field)
        csv_reader.fieldnames = cleaned_fieldnames

    print("csv_reader.fieldnames: ", csv_reader.fieldnames)

    # Create a mapping from actual CSV headers to our standardized field names
    field_map = {}
    print("csv_reader.fieldnames: ", csv_reader.fieldnames)
    for target_field, possible_names in header_mapping.items():
        for header in csv_reader.fieldnames:
            print("header: ", header)
            if any(possible_name.lower() == header.lower() for possible_name in possible_names):
                field_map[header] = target_field
                break

    print("field_map: ", field_map)

    # Clean header_line for BOM too
    clean_header_line = header_line.replace("\ufeff", "").strip()

    # Special case handling for brokerages with unique formats
    if "CurrencyCode_Group_Account" in clean_header_line and "Symbol" in field_map:
        # Questrade format detected
        field_map["Action"] = "transaction_type"
        field_map["Trade Date"] = "date"

    elif "Activity Type" in clean_header_line and any("Symbol" in h for h in csv_reader.fieldnames):
        # Wealthsimple format detected
        # May need special handling for symbol extraction
        pass

    # Process rows with the field mapping
    transactions = []
    for row in csv_reader:
        transaction_data = {}

        # Map fields using our field_map
        for csv_field, target_field in field_map.items():
            print("csv_field: ", csv_field, "target_field: ", target_field)
            if csv_field in row:
                transaction_data[target_field] = row[csv_field]
        print("transaction_data: ", transaction_data)

        # Special case: Extract ticker from "Symbol / Description" type fields
        if "ticker" not in transaction_data:
            for field in row.keys():
                if any(keyword in field.lower() for keyword in ["symbol", "description", "security"]):
                    # Try to extract ticker pattern (usually 1-5 uppercase letters)
                    symbol_desc = row[field]
                    ticker_match = re.search(r"\b[A-Z]{1,5}\b", symbol_desc)
                    if ticker_match:
                        transaction_data["ticker"] = ticker_match.group(0)
                        break

        # Process transaction type
        if "transaction_type" in transaction_data:
            tx_type = transaction_data["transaction_type"].lower()
            transaction_data["transaction_type"] = "buy" if any(word in tx_type for word in ["buy", "purchase"]) else "sell"
        else:
            # Default to buy if not specified
            transaction_data["transaction_type"] = "buy"

        # Process date
        if "date" in transaction_data:
            date_str = transaction_data["date"]
            # Try different date formats
            date_formats = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y", "%m-%d-%Y", "%d-%m-%y"]
            for fmt in date_formats:
                try:
                    transaction_data["date"] = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue

        # Process shares and price (ensure they're positive numbers)
        if "shares" in transaction_data:
            try:
                transaction_data["shares"] = abs(float(transaction_data["shares"]))
            except (ValueError, TypeError):
                transaction_data["shares"] = 0

        if "price" in transaction_data:
            try:
                transaction_data["price"] = abs(float(transaction_data["price"]))
            except (ValueError, TypeError):
                transaction_data["price"] = 0

        # Validate and add the transaction
        if transaction_data.get("ticker") and transaction_data.get("shares", 0) > 0 and transaction_data.get("price", 0) > 0:
            transactions.append(transaction_data)

        print("transaction_data: ", transaction_data)
        print("transactions from CSV: ", transactions)

    return transactions


def fetch_stock_data(ticker):
    ticker = ticker.upper()
    stock = finvizfinance(ticker)
    stock_fundament = convert_data(stock.ticker_fundament())
    stock_description = convert_data(stock.ticker_description())
    fundamentals_data = convert_data(stock.ticker_fundament())
    if isinstance(fundamentals_data, list) and len(fundamentals_data) > 0:
        fundamentals_data = fundamentals_data[0]
    filtered_fundamentals = {
        "current_price": fundamentals_data.get("Price"),
        "pe_ratio": fundamentals_data.get("P/E"),
        "52_week_high": fundamentals_data.get("52W High"),
        "52_week_low": fundamentals_data.get("52W Low"),
        "lt_debt_equity": fundamentals_data.get("LT Debt/Eq"),
        "price_fcf": fundamentals_data.get("P/FCF"),
        "operating_margin": fundamentals_data.get("Oper. Margin"),
        "beta": fundamentals_data.get("Beta"),
        "company": fundamentals_data.get("Company"),
        "change": fundamentals_data.get("Change"),
        "sector": fundamentals_data.get("Sector"),
        "avg_volume": fundamentals_data.get("Avg Volume"),
        "volume": fundamentals_data.get("Volume"),
        "market_cap": fundamentals_data.get("Market Cap"),
        "forward_pe": fundamentals_data.get("Forward P/E"),
        "eps_this_year": fundamentals_data.get("EPS this Y"),
        "eps_ttm": fundamentals_data.get("EPS (ttm)"),
        "peg_ratio": fundamentals_data.get("PEG"),
        "roe": fundamentals_data.get("ROE"),
        "roa": fundamentals_data.get("ROA"),
        "profit_margin": fundamentals_data.get("Profit Margin"),
        "sales": fundamentals_data.get("Sales"),
        "debt_eq": fundamentals_data.get("Debt/Eq"),
        "current_ratio": fundamentals_data.get("Current Ratio"),
    }
    return {"ticker": ticker, "description": stock_description, "fundamentals": filtered_fundamentals}


def fetch_market_price(ticker):
    # Known problematic tickers that often cause timeouts or errors
    PROBLEMATIC_TICKERS = {"SLG", "DISCA", "DISCK", "VIAC", "VIACA", "FOX", "FOXA", "TWTR", "FB"}

    try:
        ticker = ticker.upper()

        # Skip known problematic tickers
        if ticker in PROBLEMATIC_TICKERS:
            print(f"Skipping problematic ticker: {ticker}")
            return {"ticker": ticker, "market_price": "N/A", "error": "Ticker in blacklist"}

        stock = finvizfinance(ticker)
        fundamentals_data = stock.ticker_fundament()

        if not fundamentals_data:
            return {"ticker": ticker, "market_price": "N/A", "error": "No data found"}

        market_price = fundamentals_data.get("Price", "N/A")
        return {"ticker": ticker, "market_price": market_price}

    except Exception as e:
        error_msg = str(e)
        print(f"Error fetching market price for {ticker}: {error_msg}")

        # Check for specific error patterns that indicate problematic tickers
        if any(keyword in error_msg.lower() for keyword in ["timeout", "delisted", "timezone", "symbol may be delisted"]):
            print(f"Adding {ticker} to problematic tickers due to: {error_msg}")

        return {"ticker": ticker, "market_price": "N/A", "error": error_msg}


def recalc_portfolio(portfolio_id, ticker):
    transactions = Transaction.query.filter_by(portfolio_id=portfolio_id, ticker=ticker).all()
    total_shares = 0
    total_cost = 0.0
    for txn in transactions:
        txn_shares = float(txn.shares)
        txn_price = float(txn.price)
        if txn.transaction_type.lower() == "buy":
            total_shares += txn_shares
            total_cost += txn_shares * txn_price
        elif txn.transaction_type.lower() == "sell" and total_shares >= txn_shares:
            avg_cost_per_share = total_cost / total_shares if total_shares > 0 else 0
            total_shares -= txn_shares
            total_cost -= txn_shares * avg_cost_per_share
    new_book_value = max(0, total_cost)
    new_avg_cost = (new_book_value / total_shares) if total_shares > 0 else 0
    portfolio_entry = PortfolioHolding.query.filter_by(portfolio_id=portfolio_id, ticker=ticker).first()
    if portfolio_entry:
        if total_shares > 0:
            portfolio_entry.shares = total_shares
            portfolio_entry.average_cost = new_avg_cost
            portfolio_entry.book_value = new_book_value
        else:
            db.session.delete(portfolio_entry)
    else:
        if total_shares > 0:
            new_portfolio_entry = PortfolioHolding(
                portfolio_id=portfolio_id, ticker=ticker, shares=total_shares, average_cost=new_avg_cost, book_value=new_book_value
            )
            db.session.add(new_portfolio_entry)
    db.session.commit()


def fetch_stock_sector(ticker):
    ticker = ticker.upper()
    try:
        stock = finvizfinance(ticker)
        fundamentals_data = stock.ticker_fundament()

        # Check if data exists and sector is present
        sector = fundamentals_data.get("Sector")
        if sector is None:
            sector = "Unknown"
    except Exception as e:
        print(f"Error fetching sector for {ticker}: {e}")
        sector = "Unknown"

    return sector


# Helper function to wait for OpenAI run completion
def wait_for_run_completion(thread_id, run_id, openai_client, timeout=60):
    """Wait for a run to complete, with timeout."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        run = openai_client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
        if run.status == "completed":
            return run
        elif run.status in ["failed", "cancelled", "expired"]:
            raise Exception(f"Run failed with status: {run.status}")

        # Sleep to avoid excessive API calls
        time.sleep(1)

    raise Exception("Run timed out")


# Scheduled task to clean up old threads
def cleanup_old_threads(openai_client):
    """
    Cleanup threads older than 24 hours.
    This should be run as a scheduled task.
    """
    try:
        # Find threads older than 24 hours
        one_day_ago = datetime.now() - timedelta(days=1)
        old_threads = UserThread.query.filter(UserThread.last_used < one_day_ago).all()

        for thread in old_threads:
            # Delete the thread from OpenAI
            try:
                openai_client.beta.threads.delete(thread_id=thread.thread_id)
            except Exception as e:
                print(f"Error deleting OpenAI thread {thread.thread_id}: {str(e)}")

            # Delete the thread from our database
            db.session.delete(thread)

        db.session.commit()
        print(f"Cleaned up {len(old_threads)} old chat threads")

    except Exception as e:
        print(f"Error in cleanup_old_threads: {str(e)}")
        db.session.rollback()


def fetch_historical_price(ticker, date_str):
    """
    Fetch historical price data for a ticker on a specific date using Yahoo Finance.

    Args:
        ticker (str): The stock ticker symbol
        date_str (str): Date in ISO format (YYYY-MM-DD)

    Returns:
        float: The closing price for that date, or None if not available
    """
    try:
        # Convert the string date to a datetime object
        date = datetime.strptime(date_str, "%Y-%m-%d").date()

        # To handle weekend/holiday, we might need to look a few days back
        # Get data for a window of 5 days before the requested date
        start_date = (date - timedelta(days=5)).strftime("%Y-%m-%d")
        end_date = (date + timedelta(days=1)).strftime("%Y-%m-%d")  # Add one day to include the target date

        # Fetch data from Yahoo Finance
        data = yf.download(ticker, start=start_date, end=end_date, progress=False)

        if data.empty:
            print(f"No data returned from yfinance for {ticker} around {date_str}")
            return None

        # Get the last available date on or before the requested date
        data = data[data.index <= pd.Timestamp(date)]
        if data.empty:
            print(f"No data on or before {date_str} for {ticker}")
            return None

        # Get the closing price from the most recent date
        latest_date = data.index[-1]
        price = float(data.loc[latest_date, "Close"])

        print(f"Found price for {ticker} on {latest_date.strftime('%Y-%m-%d')}: ${price:.2f}")
        return price

    except Exception as e:
        print(f"Error fetching historical price for {ticker} on {date_str}: {e}")
        return None


def fetch_batch_historical_prices(ticker, start_date, end_date=None):
    """
    Fetch historical prices for a ticker within a date range using Yahoo Finance.

    Args:
        ticker (str): The stock ticker symbol
        start_date (str): Start date in ISO format (YYYY-MM-DD)
        end_date (str, optional): End date in ISO format. Defaults to current date.

    Returns:
        dict: Map of dates to closing prices
    """
    if end_date is None:
        end_date = datetime.now().date().isoformat()

    try:
        # Add a buffer day at the beginning and end to ensure we get the exact dates
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()

        adjusted_start = (start_date_obj - timedelta(days=5)).strftime("%Y-%m-%d")
        adjusted_end = (end_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")

        # Fetch data from Yahoo Finance
        data = yf.download(ticker, start=adjusted_start, end=adjusted_end, progress=False)

        if data.empty:
            print(f"No data returned from yfinance for {ticker} between {start_date} and {end_date}")
            return {}

        # Convert DataFrame to dictionary mapping dates to closing prices
        prices = {}
        for date, row in data.iterrows():
            date_str = date.strftime("%Y-%m-%d")
            # Only include dates in our requested range
            if start_date <= date_str <= end_date:
                prices[date_str] = float(row["Close"])

        if prices:
            print(f"Fetched {len(prices)} historical prices for {ticker} from {start_date} to {end_date}")
            # Print a few sample prices for debugging
            sample_keys = list(prices.keys())
            if len(sample_keys) > 3:
                sample_keys = [sample_keys[0], sample_keys[len(sample_keys) // 2], sample_keys[-1]]
            for key in sample_keys:
                print(f"{key}: ${prices[key]:.2f}")
        else:
            print(f"No prices found in the specified range for {ticker}")

        return prices

    except Exception as e:
        print(f"Error fetching batch historical prices for {ticker}: {e}")
        return {}


def fetch_market_benchmarks():
    """Fetch performance data for major market indices"""
    try:
        # Get S&P 500, Nasdaq, and Dow Jones data
        benchmarks = {"S&P500": "^GSPC", "NASDAQ": "^IXIC", "DOW": "^DJI"}

        result = {}
        for name, ticker in benchmarks.items():
            data = yf.Ticker(ticker)
            hist = data.history(period="1mo")  # Get 1 month of data

            if not hist.empty:
                # Calculate performance metrics
                current = hist["Close"].iloc[-1]
                week_ago = hist["Close"].iloc[-5] if len(hist) >= 5 else hist["Close"].iloc[0]
                month_ago = hist["Close"].iloc[0]

                # Calculate percentage changes
                weekly_change = ((current - week_ago) / week_ago) * 100
                monthly_change = ((current - month_ago) / month_ago) * 100

                result[name] = {"current": current, "weekly_change_pct": weekly_change, "monthly_change_pct": monthly_change}

        return result
    except Exception as e:
        return {"error": str(e)}
