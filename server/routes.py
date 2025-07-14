# routes.py
import uuid
from re import findall
import os
import time
import json
import requests
import pandas as pd
import csv
from openai import OpenAI

from flask import Flask, jsonify, request, g
from firebase_admin import auth
from finvizfinance.quote import finvizfinance
from finvizfinance.news import News
from io import StringIO
from datetime import datetime
from datetime import datetime, timedelta
from collections import defaultdict

from models import db, User, Watchlist, Portfolio, Transaction, PortfolioHolding, UserThread
from helpers import (
    convert_data,
    safe_convert,
    parse_csv_with_mapping,
    fetch_stock_data,
    fetch_market_price,
    recalc_portfolio,
    fetch_stock_sector,
    wait_for_run_completion,
    cleanup_old_threads,
    fetch_historical_price,
    fetch_batch_historical_prices,
    fetch_market_benchmarks,
)

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv("OPENAI_AGENT_API_KEY"))
ASSISTANT_ID = os.getenv("STOCKR_ASSISTANT_ID")
ALPHA_ID = os.getenv("STOCKR_ALPHA_ID")

# Debug: Check if environment variables are loaded
print("=== OpenAI Configuration Debug ===")
print(f"OPENAI_AGENT_API_KEY exists: {bool(os.getenv('OPENAI_AGENT_API_KEY'))}")
print(f"STOCKR_ASSISTANT_ID exists: {bool(os.getenv('STOCKR_ASSISTANT_ID'))}")
if os.getenv("OPENAI_AGENT_API_KEY"):
    api_key = os.getenv("OPENAI_AGENT_API_KEY")
    print(f"API Key starts with: {api_key[:10]}...")
else:
    print("ERROR: OPENAI_AGENT_API_KEY is None or empty!")
print("=== End Debug ===")


def register_routes(app):

    # Before each request, check Firebase token for protected endpoints.
    @app.before_request
    def authenticate():
        if request.method == "OPTIONS":
            return  # Skip auth for preflight
        protected_endpoints = [
            "add_to_watchlist",
            "get_watchlist_stocks",
            "delete_from_watchlist",
            "get_stock_historical",
            "get_crypto_historical",
            "get_cash_balance",
            "add_portfolio_entry",
            "get_portfolio_for_graph",
            "get_portfolio",
            "deposit_cash",
            "withdraw_cash",
            "delete_transaction",
            "get_transactions",
            "buy_asset",
            "sell_asset",
            "get_portfolio_id",
            "sell_portfolio_asset",
            "add_portfolio_asset",
            "get_stock_market_price",
            "search_stocks",
            "upload_transactions",
            "get_portfolio_assistant_context",
            "start_chat_thread",
            "continue_chat_thread",
            "get_portfolio_history",
        ]
        if request.endpoint in protected_endpoints:
            auth_header = request.headers.get("Authorization")
            if not auth_header or "Bearer " not in auth_header:
                return jsonify({"error": "Unauthorized"}), 401
            id_token = auth_header.split("Bearer ")[1]
            print(id_token)
            try:
                decoded_token = auth.verify_id_token(id_token)
                g.user = User.query.filter_by(firebase_uid=decoded_token["uid"]).first()
                if not g.user:
                    return jsonify({"error": "User not found"}), 401
            except Exception as e:
                return jsonify({"error": str(e)}), 401

    # --- Route Definitions ---

    @app.route("/")
    def home():
        return jsonify({"message": "FinViz Stock Watchlist API is running!"})

    @app.route("/api/calendar", methods=["GET"])
    def get_economic_calendar():
        return jsonify({"message": "FinViz Stock Watchlist API is running!"})

    @app.route("/api/stocks/<string:query>", methods=["GET"])
    def search_stocks(query):
        try:
            yahoo_api_url = f"https://query1.finance.yahoo.com/v6/finance/autocomplete?lang=en&query={query}"
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(yahoo_api_url, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()
            results = data.get("ResultSet", {}).get("Result", [])
            stocks = [{"symbol": stock.get("symbol"), "name": stock.get("name")} for stock in results[:5]]
            if not stocks:
                return jsonify({"error": "No matching stocks found"}), 404
            return jsonify({"stocks": stocks}), 200
        except requests.exceptions.RequestException as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/stock/<string:ticker>", methods=["GET"])
    def get_stock_data(ticker):
        try:
            ticker = ticker.upper()
            stock = finvizfinance(ticker)
            stock_fundament = convert_data(stock.ticker_fundament())
            stock_description = convert_data(stock.ticker_description())
            outer_ratings = convert_data(stock.ticker_outer_ratings())
            news = convert_data(stock.ticker_news())
            inside_trader = convert_data(stock.ticker_inside_trader())
            combined_data = {
                "fundamentals": stock_fundament,
                "description": stock_description,
                "outer_ratings": outer_ratings,
                "news": news,
                "inside_trader": inside_trader,
            }
            return jsonify(combined_data), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/stock/current/<string:ticker>", methods=["GET"])
    def get_stock_price(ticker):
        market_data = fetch_market_price(ticker)
        return jsonify(market_data), 200

    @app.route("/api/watchlist/stocks", methods=["GET"])
    def get_watchlist_stocks():
        try:
            watchlist_items = Watchlist.query.filter_by(user_id=g.user.id).all()
            tickers = [item.ticker for item in watchlist_items]
            stocks_data = []
            for ticker in tickers:
                try:
                    stock_data = fetch_stock_data(ticker)
                    stocks_data.append(stock_data)
                except Exception as inner_error:
                    stocks_data.append({"ticker": ticker, "error": str(inner_error)})
            return jsonify(stocks_data), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/watchlist", methods=["POST"])
    def add_to_watchlist():
        data = request.get_json()
        if not data or "ticker" not in data:
            return jsonify({"error": "Ticker is required"}), 400
        ticker = data["ticker"].upper()
        try:
            new_watchlist_item = Watchlist(user_id=g.user.id, ticker=ticker)
            db.session.add(new_watchlist_item)
            db.session.commit()
            return jsonify({"message": "Ticker added to watchlist", "ticker": ticker, "user_id": g.user.id}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/watchlist/<string:ticker>", methods=["DELETE"])
    def delete_from_watchlist(ticker):
        ticker = ticker.upper()
        item = Watchlist.query.filter_by(user_id=g.user.id, ticker=ticker).first()
        if not item:
            return jsonify({"error": "Ticker not found in watchlist"}), 404
        try:
            db.session.delete(item)
            db.session.commit()
            return jsonify({"message": "Ticker removed from watchlist", "ticker": ticker, "user_id": g.user.id}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/stock/historical/<string:symbol>", methods=["GET"])
    def get_stock_historical(symbol):
        symbol = symbol.upper()
        url = f"https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY_ADJUSTED&symbol={symbol}&outputsize=full&apikey={ALPHA_ID}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if "Error Message" in data:
                return jsonify({"error": data["Error Message"]}), 400
            if "Weekly Adjusted Time Series" not in data:
                return jsonify({"error": "Invalid response from Alpha Vantage"}), 400
            time_series = data["Weekly Adjusted Time Series"]
            dates = sorted(time_series.keys())
            prices = [time_series[date]["5. adjusted close"] for date in dates]
            graph_data = {"dates": dates, "prices": prices}
            return jsonify(graph_data), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/crypto/historical/<string:symbol>", methods=["GET"])
    def get_crypto_historical(symbol):
        symbol = symbol.upper()
        url = f"https://www.alphavantage.co/query?function=DIGITAL_CURRENCY_DAILY&symbol={symbol}&market=USD&apikey={ALPHA_ID}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if "Error Message" in data:
                return jsonify({"error": data["Error Message"]}), 400
            if "Time Series (Digital Currency Daily)" not in data:
                return jsonify({"error": "Invalid response from Alpha Vantage"}), 400
            time_series = data["Time Series (Digital Currency Daily)"]
            dates = sorted(time_series.keys())
            prices = [time_series[date]["4a. close (USD)"] for date in dates]
            graph_data = {"dates": dates, "prices": prices}
            return jsonify(graph_data), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/market-news", methods=["GET"])
    def get_market_news():
        try:
            news = News()
            news_data = news.get_news()
            news_data_converted = {}
            for key, value in news_data.items():
                if hasattr(value, "to_dict"):
                    news_data_converted[key] = value.to_dict(orient="records")
                else:
                    news_data_converted[key] = value
            response = {"relevant_news": news_data_converted}
            return jsonify(response), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/ticker-search", methods=["GET"])
    def get_ticker():
        keyword = request.args.get("keywords", "Microsoft")
        url = f"https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={keyword}&apikey={ALPHA_ID}"
        r = requests.get(url)
        if r.status_code != 200:
            return jsonify({"error": "Failed to fetch data from Alpha Vantage"}), 500
        data = r.json()
        return jsonify(data), 200

    @app.route("/api/news-sentiment", methods=["GET"])
    def get_news_sentiment():
        tickers = request.args.get("tickers")
        if not tickers:
            return jsonify({"error": "The 'tickers' query parameter is required."}), 400
        topics = request.args.get("topics")
        url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={tickers}"
        if topics:
            url += f"&topics={topics}"
        url += f"&apikey={ALPHA_ID}"
        print(url)
        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.RequestException as req_err:
            return jsonify({"error": f"Failed to fetch data from Alpha Vantage: {req_err}"}), 500
        data = response.json()
        return jsonify(data), 200

    @app.route("/api/income-statement", methods=["GET"])
    def get_income_statement():
        symbol = request.args.get("symbol")
        if not symbol:
            return jsonify({"error": "The 'symbol' query parameter is required."}), 400
        url = f"https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol={symbol}&apikey={ALPHA_ID}"
        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.RequestException as req_err:
            return jsonify({"error": f"Failed to fetch data from Alpha Vantage: {req_err}"}), 500
        data = response.json()
        return jsonify(data), 200

    @app.route("/api/balance-sheet", methods=["GET"])
    def get_balance_sheet():
        symbol = request.args.get("symbol")
        if not symbol:
            return jsonify({"error": "The 'symbol' query parameter is required."}), 400
        url = f"https://www.alphavantage.co/query?function=BALANCE_SHEET&symbol={symbol}&apikey={ALPHA_ID}"
        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.RequestException as req_err:
            return jsonify({"error": f"Failed to fetch data from Alpha Vantage: {req_err}"}), 500
        data = response.json()
        return jsonify(data), 200

    @app.route("/api/cash-flow", methods=["GET"])
    def get_cash_flow():
        symbol = request.args.get("symbol")
        if not symbol:
            return jsonify({"error": "The 'symbol' query parameter is required."}), 400
        url = f"https://www.alphavantage.co/query?function=CASH_FLOW&symbol={symbol}&apikey={ALPHA_ID}"
        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.RequestException as req_err:
            return jsonify({"error": f"Failed to fetch data from Alpha Vantage: {req_err}"}), 500
        data = response.json()
        return jsonify(data), 200

    @app.route("/api/portfolio/<string:portfolio_id>", methods=["GET"])
    def get_portfolio(portfolio_id):
        try:
            if not hasattr(g, "user") or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401
            portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found or unauthorized"}), 404
            portfolio_entries = PortfolioHolding.query.filter_by(portfolio_id=portfolio_id).all()
            portfolio_list = [
                {
                    "ticker": entry.ticker,
                    "shares": float(entry.shares),
                    "average_cost": float(entry.average_cost) if entry.average_cost is not None else 0,
                    "book_value": float(entry.book_value) if entry.book_value is not None else 0,
                    "market_value": 0,
                }
                for entry in portfolio_entries
            ]
            return jsonify({"portfolio": portfolio_list}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/portfolio/buy", methods=["POST"])
    def buy_asset():
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided."}), 400
        ticker = data.get("ticker")
        shares = data.get("shares")
        price = data.get("price")
        if not ticker or shares is None or price is None:
            return jsonify({"error": "Ticker, shares, and price are required."}), 400
        ticker = ticker.upper()
        try:
            user = g.user
            portfolio = Portfolio.query.filter_by(user_id=user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found"}), 404
            new_txn = Transaction(portfolio_id=portfolio.id, ticker=ticker, shares=shares, price=price, transaction_type="buy")
            db.session.add(new_txn)
            db.session.commit()
            recalc_portfolio(portfolio.id, ticker)
            return jsonify({"message": "Asset purchased successfully.", "ticker": ticker}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/portfolio/sell", methods=["POST"])
    def sell_asset():
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided."}), 400
        ticker = data.get("ticker")
        shares = data.get("shares")
        price = data.get("price")
        if not ticker or shares is None or price is None:
            return jsonify({"error": "Ticker, shares, and price are required."}), 400
        ticker = ticker.upper()
        try:
            user = g.user
            portfolio = Portfolio.query.filter_by(user_id=user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found"}), 404
            holding = PortfolioHolding.query.filter_by(portfolio_id=portfolio.id, ticker=ticker).first()
            if not holding or holding.shares < shares:
                return jsonify({"error": "Not enough shares to sell."}), 400
            new_txn = Transaction(portfolio_id=portfolio.id, ticker=ticker, shares=shares, price=price, transaction_type="sell")
            db.session.add(new_txn)
            db.session.commit()
            recalc_portfolio(portfolio.id, ticker)
            return jsonify({"message": "Asset sold successfully.", "ticker": ticker}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/portfolio/<string:portfolio_id>/add-asset", methods=["POST"])
    def add_portfolio_asset(portfolio_id):
        try:
            if not hasattr(g, "user") or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401
            data = request.get_json()
            if not data:
                return jsonify({"error": "No data provided."}), 400
            ticker = data.get("ticker")
            shares = data.get("shares")
            price = data.get("price")
            transaction_type = data.get("transaction_type", "buy").lower()
            if not ticker or shares is None or price is None:
                return jsonify({"error": "Ticker, shares, and price are required."}), 400
            ticker = ticker.upper()
            portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found or unauthorized"}), 404
            new_txn = Transaction(portfolio_id=portfolio.id, ticker=ticker, shares=shares, price=price, transaction_type=transaction_type)
            db.session.add(new_txn)
            recalc_portfolio(portfolio.id, ticker)
            db.session.commit()
            return jsonify({"message": "Transaction recorded and portfolio updated successfully."}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/portfolio/<string:portfolio_id>/sell-asset", methods=["POST"])
    def sell_portfolio_asset(portfolio_id):
        try:
            if not hasattr(g, "user") or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401
            data = request.get_json()
            if not data:
                return jsonify({"error": "No data provided."}), 400
            ticker = data.get("ticker")
            shares = data.get("shares")
            price = data.get("price")
            transaction_type = "sell"
            if not ticker or shares is None or price is None:
                return jsonify({"error": "Ticker, shares, and price are required."}), 400
            ticker = ticker.upper()
            portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found or unauthorized"}), 404
            portfolio_entry = PortfolioHolding.query.filter_by(portfolio_id=portfolio.id, ticker=ticker).first()
            if not portfolio_entry or portfolio_entry.shares < shares:
                return jsonify({"error": "Insufficient shares to sell"}), 400
            new_txn = Transaction(portfolio_id=portfolio.id, ticker=ticker, shares=shares, price=price, transaction_type=transaction_type)
            db.session.add(new_txn)
            recalc_portfolio(portfolio.id, ticker)
            db.session.commit()
            return jsonify({"message": "Transaction recorded and portfolio updated successfully."}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/portfolio/graph/<string:portfolio_id>", methods=["GET"])
    def get_portfolio_for_graph(portfolio_id):
        try:
            if not hasattr(g, "user") or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401
            portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found or unauthorized"}), 404
            portfolio_entries = PortfolioHolding.query.filter_by(portfolio_id=portfolio_id).all()
            portfolio_list = [
                {"ticker": entry.ticker, "book_value": float(entry.book_value) if entry.book_value is not None else 0} for entry in portfolio_entries
            ]
            return jsonify({"portfolio": portfolio_list}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/transactions", methods=["GET"])
    def get_transactions():
        try:
            if not hasattr(g, "user") or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401
            portfolio = Portfolio.query.filter_by(user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found"}), 404
            transactions = Transaction.query.filter_by(portfolio_id=portfolio.id).order_by(Transaction.created_at.desc()).limit(15).all()
            transactions_list = [
                {
                    "id": txn.id,
                    "ticker": txn.ticker,
                    "shares": float(txn.shares),
                    "price": float(txn.price),
                    "transaction_type": txn.transaction_type,
                    "created_at": txn.created_at.isoformat(),
                }
                for txn in transactions
            ]
            return jsonify({"transactions": transactions_list}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/transactions/<string:transaction_id>", methods=["DELETE"])
    def delete_transaction(transaction_id):
        try:
            if not hasattr(g, "user") or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401
            portfolio = Portfolio.query.filter_by(user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found"}), 404
            transaction = Transaction.query.filter_by(id=transaction_id, portfolio_id=portfolio.id).first()
            if not transaction:
                return jsonify({"error": "Transaction not found"}), 404
            ticker = transaction.ticker
            shares = float(transaction.shares)
            price = float(transaction.price)
            total_value = shares * price
            holding = PortfolioHolding.query.filter_by(portfolio_id=portfolio.id, ticker=ticker).first()
            if transaction.transaction_type.lower() == "buy":
                if holding:
                    holding.shares -= shares
                    holding.book_value -= total_value
                    if holding.shares <= 0:
                        db.session.delete(holding)
            elif transaction.transaction_type.lower() == "sell":
                if holding:
                    holding.shares += shares
                    holding.book_value += total_value
                else:
                    new_holding = PortfolioHolding(
                        id=str(uuid.uuid4()), portfolio_id=portfolio.id, ticker=ticker, shares=shares, average_cost=price, book_value=total_value
                    )
                    db.session.add(new_holding)
            db.session.delete(transaction)
            db.session.commit()
            return (
                jsonify(
                    {
                        "message": "Transaction deleted successfully.",
                        "updated_portfolio": {
                            "ticker": ticker,
                            "shares": float(holding.shares) if holding else 0,
                            "book_value": float(holding.book_value) if holding else 0,
                        },
                    }
                ),
                200,
            )
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/users", methods=["POST"])
    def create_user():
        try:
            data = request.get_json()
            print("Received data:", data)
            if not data or "firebase_uid" not in data:
                return jsonify({"error": "Firebase UID is required"}), 400
            existing_user = User.query.filter_by(firebase_uid=data["firebase_uid"]).first()
            if existing_user:
                portfolio = Portfolio.query.filter_by(user_id=existing_user.id).first()
                return (
                    jsonify({"message": "User already exists", "user_id": existing_user.id, "portfolio_id": portfolio.id if portfolio else None}),
                    200,
                )
            new_user = User(id=str(uuid.uuid4()), firebase_uid=data["firebase_uid"])
            db.session.add(new_user)
            db.session.commit()
            new_portfolio = Portfolio(id=str(uuid.uuid4()), user_id=new_user.id)
            db.session.add(new_portfolio)
            db.session.commit()
            print("User and portfolio created successfully:", new_user.id, new_portfolio.id)
            return jsonify({"message": "User created", "user_id": new_user.id, "portfolio_id": new_portfolio.id}), 201
        except Exception as e:
            print("Error creating user:", str(e))
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/portfolio/id", methods=["GET"])
    def get_portfolio_id():
        try:
            if not hasattr(g, "user") or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401
            portfolio = Portfolio.query.filter_by(user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found"}), 404
            return jsonify({"portfolio_id": portfolio.id}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/portfolio/<string:portfolio_id>/upload-transactions", methods=["POST"])
    def upload_transactions(portfolio_id):
        # Ensure the user is authenticated.
        if not hasattr(g, "user") or g.user is None:
            return jsonify({"error": "User not authenticated"}), 401

        # Ensure a file was uploaded.
        if "file" not in request.files:
            return jsonify({"error": "No file part in the request"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        try:
            # Read file content and create a StringIO stream.
            content = file.read().decode("UTF8")
            stream = StringIO(content, newline=None)

            # Parse the CSV using the flexible mapping helper.
            transactions = parse_csv_with_mapping(stream)
            print(transactions)
            if not transactions:
                return jsonify({"error": "No valid transactions found in the file"}), 400

            # Get the portfolio for the authenticated user using the provided portfolio_id.
            portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found or unauthorized"}), 404

            transactions_added = 0
            errors = []
            tickers_set = set()

            for transaction in transactions:
                # Normalize ticker.
                ticker = transaction.get("ticker", "").strip().upper()

                try:
                    shares = float(transaction.get("shares", 0))
                    price = float(transaction.get("price", 0))
                except ValueError as e:
                    errors.append(f"Invalid numeric values in transaction: {transaction}. Error: {str(e)}")
                    continue

                transaction_type = transaction.get("transaction_type", "buy").strip().lower()

                # Process the date if provided. We'll use it to override created_at.
                transaction_date = transaction.get("date")
                created_at_val = None
                if transaction_date:
                    # If the date is already a date/datetime object, combine with midnight if needed.
                    if isinstance(transaction_date, datetime):
                        created_at_val = transaction_date
                    elif hasattr(transaction_date, "year"):
                        created_at_val = datetime.combine(transaction_date, datetime.min.time())
                    else:
                        # Otherwise, try parsing from string (assumes formats like YYYY-MM-DD).
                        try:
                            created_at_val = datetime.strptime(transaction_date, "%Y-%m-%d")
                        except Exception:
                            # If parsing fails, leave created_at_val as None (default will be used).
                            pass

                if not ticker or shares <= 0 or price <= 0:
                    errors.append(f"Invalid data in transaction: {transaction}")
                    continue

                tickers_set.add(ticker)

                # Create the transaction record.
                # If a CSV date is provided, override created_at.
                if created_at_val is not None:
                    new_txn = Transaction(
                        portfolio_id=portfolio.id,
                        ticker=ticker,
                        shares=shares,
                        price=price,
                        transaction_type=transaction_type,
                        created_at=created_at_val,
                    )
                else:
                    new_txn = Transaction(portfolio_id=portfolio.id, ticker=ticker, shares=shares, price=price, transaction_type=transaction_type)

                db.session.add(new_txn)
                transactions_added += 1

            if transactions_added > 0:
                db.session.commit()
                # Recalculate portfolio holdings for each unique ticker.
                for ticker in tickers_set:
                    recalc_portfolio(portfolio.id, ticker)

            if errors:
                return (
                    jsonify(
                        {
                            "message": f"{transactions_added} transactions added with some errors.",
                            "errors": errors,
                        }
                    ),
                    207,
                )

            return jsonify({"message": f"{transactions_added} transactions added successfully."}), 201

        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error processing CSV file: {str(e)}")
            return jsonify({"error": f"Error processing file: {str(e)}"}), 500

    @app.route("/api/portfolio/<string:portfolio_id>/history", methods=["GET"])
    def get_portfolio_history(portfolio_id):
        """
        Calculates the portfolio's market value over time based on transaction history
        and historical market prices using helper functions.
        Returns data points for plotting a line chart of portfolio growth.
        """
        try:
            if not hasattr(g, "user") or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401

            # Verify the portfolio belongs to the user
            portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found or unauthorized"}), 404

            # Get all transactions sorted by date
            transactions = Transaction.query.filter_by(portfolio_id=portfolio_id).order_by(Transaction.created_at).all()

            if not transactions:
                return jsonify({"history": [], "message": "No transactions found"}), 200

            # Find the date of the first transaction to establish our timeline start
            start_date = transactions[0].created_at.date()
            end_date = datetime.now().date()  # Use current date as end date

            app.logger.info(f"Calculating portfolio history from {start_date} to {end_date}")

            # Get all unique tickers in the portfolio
            unique_tickers = set(txn.ticker for txn in transactions)

            app.logger.info(f"Found {len(unique_tickers)} unique tickers: {', '.join(unique_tickers)}")

            # Get current holdings to use for the final data point
            current_holdings = {}
            portfolio_entries = PortfolioHolding.query.filter_by(portfolio_id=portfolio_id).all()

            for entry in portfolio_entries:
                current_holdings[entry.ticker] = float(entry.shares)

            # Fetch real-time current market prices for current holdings
            current_market_prices = {}
            for ticker, shares in current_holdings.items():
                if shares <= 0:  # Skip positions with 0 shares
                    continue

                try:
                    market_data = fetch_market_price(ticker)
                    if market_data and "market_price" in market_data and market_data["market_price"] != "N/A":
                        try:
                            current_market_prices[ticker] = float(market_data["market_price"])
                            app.logger.info(f"Current market price for {ticker}: ${current_market_prices[ticker]}")
                        except (ValueError, TypeError):
                            app.logger.warning(f"Invalid market price for {ticker}: {market_data['market_price']}")
                    else:
                        app.logger.warning(f"Market price for {ticker} not available")
                except Exception as e:
                    app.logger.error(f"Error fetching current market price for {ticker}: {e}")

            # Fetch historical price data for each ticker
            ticker_historical_prices = {}

            for ticker in unique_tickers:
                # Use the fetch_batch_historical_prices helper function
                prices = fetch_batch_historical_prices(ticker, start_date.isoformat(), end_date.isoformat())
                ticker_historical_prices[ticker] = prices

                # Ensure we don't hit API rate limits
                time.sleep(0.5)  # Add a small delay between API calls

            # Create a day-by-day portfolio value calculation
            portfolio_history = []

            # Sample dates - weekly intervals for past data points
            sampling_rate = 7  # One data point per week

            date_range = []
            current_date = start_date
            while current_date < end_date:  # Note: we'll handle end_date separately for current prices
                date_range.append(current_date)
                current_date += timedelta(days=sampling_rate)

            # Process each sampled date
            for current_date in date_range:
                date_str = current_date.isoformat()

                # Calculate holdings as of this date
                holdings = defaultdict(float)  # ticker -> shares

                # Apply all transactions up to and including this date
                for txn in transactions:
                    if txn.created_at.date() <= current_date:
                        ticker = txn.ticker
                        shares = float(txn.shares)

                        if txn.transaction_type.lower() == "buy":
                            holdings[ticker] += shares
                        elif txn.transaction_type.lower() == "sell":
                            holdings[ticker] -= shares

                # Calculate portfolio value for this day using historical market prices
                day_value = 0

                for ticker, shares in holdings.items():
                    if shares <= 0:
                        continue

                    # Try to get the market price for this ticker on this date
                    price = None

                    if date_str in ticker_historical_prices.get(ticker, {}):
                        # Use price from our already fetched batch
                        price = ticker_historical_prices[ticker][date_str]
                    else:
                        # Fetch individual price if not in batch (as a fallback)
                        price = fetch_historical_price(ticker, date_str)

                        if price is None:
                            # If still no price, use the last transaction price for this ticker
                            for t in reversed(transactions):
                                if t.ticker == ticker and t.created_at.date() <= current_date:
                                    price = float(t.price)
                                    break

                    # If a price was found, add to the day's value
                    if price:
                        day_value += shares * price
                    else:
                        app.logger.warning(f"No price found for {ticker} on {date_str}")

                # Add data point for this day
                portfolio_history.append({"date": date_str, "value": round(day_value, 2), "market_value": round(day_value, 2)})

            # Add current day using real-time market prices
            current_day_value = 0

            for ticker, shares in current_holdings.items():
                if shares <= 0:
                    continue

                if ticker in current_market_prices:
                    # Use real-time market price
                    price = current_market_prices[ticker]
                    current_day_value += shares * price
                else:
                    # Fallback if real-time price not available
                    app.logger.warning(f"No current market price available for {ticker}, using fallback")

                    # Try historical prices first
                    latest_prices = ticker_historical_prices.get(ticker, {})
                    if latest_prices:
                        latest_date = max(latest_prices.keys())
                        price = latest_prices[latest_date]
                        current_day_value += shares * price
                    else:
                        # Last resort: use transaction price
                        for t in reversed(transactions):
                            if t.ticker == ticker:
                                price = float(t.price)
                                current_day_value += shares * price
                                break

            # Add current day data point
            portfolio_history.append(
                {"date": end_date.isoformat(), "value": round(current_day_value, 2), "market_value": round(current_day_value, 2)}
            )

            app.logger.info(f"Calculated {len(portfolio_history)} portfolio history data points")
            app.logger.info(f"Final portfolio value: ${round(current_day_value, 2)}")

            return (
                jsonify(
                    {
                        "history": portfolio_history,
                        "message": "Portfolio history with current market values",
                        "total_value": round(current_day_value, 2),
                    }
                ),
                200,
            )

        except Exception as e:
            app.logger.error(f"Error calculating portfolio history: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    # --- Assistant ---

    @app.route("/api/portfolio/chat", methods=["POST"])
    def start_chat_thread():
        try:
            # Ensure user is authenticated
            if not hasattr(g, "user") or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401

            data = request.get_json()
            user_question = data.get("question")
            if not user_question:
                return jsonify({"error": "Question is required"}), 400

            # Get the user's portfolio (removed is_default filter since Portfolio doesn't have it)
            portfolio = Portfolio.query.filter_by(user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "No portfolio found for this user"}), 404

            # Retrieve portfolio holdings and benchmarks
            portfolio_entries = PortfolioHolding.query.filter_by(portfolio_id=portfolio.id).all()
            benchmarks = fetch_market_benchmarks()

            if not portfolio_entries:
                # Provide a default message if no holdings exist.
                portfolio_context = "You currently do not have any portfolio holdings."
            else:
                portfolio_context = "Market Benchmarks:\n"

                if "error" not in benchmarks:
                    for name, data in benchmarks.items():
                        portfolio_context += (
                            f"{name}: Current: ${data['current']:.2f}, "
                            f"1-Week: {data['weekly_change_pct']:.2f}%, "
                            f"1-Month: {data['monthly_change_pct']:.2f}%\n"
                        )
                else:
                    portfolio_context += "Market benchmark data unavailable.\n"
                portfolio_context = "Portfolio Holdings:\n"
                for entry in portfolio_entries:
                    # Get detailed stock data
                    try:
                        stock_data = fetch_stock_data(entry.ticker)
                        fundamentals = stock_data.get("fundamentals", {})
                        sector = fundamentals.get("sector") or fetch_stock_sector(entry.ticker) or "Unknown"
                        total_value = float(entry.shares) * float(entry.average_cost)
                        current_price = fundamentals.get("current_price", "N/A")

                        # Calculate performance metrics
                        market_value = (
                            float(entry.shares) * float(current_price.replace("$", "").replace(",", ""))
                            if isinstance(current_price, str) and current_price != "N/A"
                            else total_value
                        )
                        gain_loss = market_value - total_value
                        gain_loss_percentage = (gain_loss / total_value) * 100 if total_value > 0 else 0

                        # Format the portfolio entry with detailed metrics
                        portfolio_context += (
                            f"- {entry.ticker.upper()} ({sector}): "
                            f"{float(entry.shares):.2f} shares at avg ${float(entry.average_cost):.2f}, "
                            f"total value ${total_value:.2f}. "
                            f"Current price: {current_price}, Market value: ${market_value:.2f}, "
                            f"Gain/Loss: ${gain_loss:.2f} ({gain_loss_percentage:.2f}%). "
                            f"P/E: {fundamentals.get('pe_ratio', 'N/A')}, "
                            f"Forward P/E: {fundamentals.get('forward_pe', 'N/A')}, "
                            f"PEG: {fundamentals.get('peg_ratio', 'N/A')}, "
                            f"52W High: {fundamentals.get('52_week_high', 'N/A')}, "
                            f"52W Low: {fundamentals.get('52_week_low', 'N/A')}, "
                            f"Profit Margin: {fundamentals.get('profit_margin', 'N/A')}, "
                            f"ROE: {fundamentals.get('roe', 'N/A')}, "
                            f"Debt/Equity: {fundamentals.get('debt_eq', 'N/A')}, "
                            f"Beta: {fundamentals.get('beta', 'N/A')}, "
                            f"Market Cap: {fundamentals.get('market_cap', 'N/A')}.\n"
                        )
                    except Exception as e:
                        # Fallback to basic information if fetching detailed data fails
                        sector = fetch_stock_sector(entry.ticker) or "Unknown"
                        total_value = float(entry.shares) * float(entry.average_cost)
                        portfolio_context += (
                            f"- {entry.ticker.upper()} ({sector}): "
                            f"{float(entry.shares):.2f} shares at avg ${float(entry.average_cost):.2f}, "
                            f"total value ${total_value:.2f}. (Error fetching detailed metrics: {str(e)})\n"
                        )

            # Create a new thread
            try:
                thread = openai_client.beta.threads.create()
            except Exception as e:
                app.logger.error(f"Error creating OpenAI thread: {e}")
                return jsonify({"error": "Failed to create chat thread", "details": str(e)}), 500

            # Send system message with portfolio context
            try:
                openai_client.beta.threads.messages.create(thread_id=thread.id, role="user", content=portfolio_context)
            except Exception as e:
                app.logger.error(f"Error sending system message: {e}")
                return jsonify({"error": "Failed to send system message", "details": str(e)}), 500

            # Send the user's question
            try:
                openai_client.beta.threads.messages.create(thread_id=thread.id, role="user", content=user_question)
            except Exception as e:
                app.logger.error(f"Error sending user message: {e}")
                return jsonify({"error": "Failed to send user message", "details": str(e)}), 500

            # Start the assistant run
            try:
                run = openai_client.beta.threads.runs.create(thread_id=thread.id, assistant_id=ASSISTANT_ID)
            except Exception as e:
                app.logger.error(f"Error starting OpenAI run: {e}")
                return jsonify({"error": "Failed to start chat run", "details": str(e)}), 500

            # Wait for the run to complete
            try:
                run = wait_for_run_completion(thread.id, run.id, openai_client)
            except Exception as e:
                app.logger.error(f"Error waiting for run completion: {e}")
                return jsonify({"error": "Chat run did not complete", "details": str(e)}), 500

            # Retrieve assistant's response
            try:
                messages_response = openai_client.beta.threads.messages.list(thread_id=thread.id)
                assistant_message = next((msg for msg in messages_response.data if msg.role == "assistant"), None)
            except Exception as e:
                app.logger.error(f"Error retrieving assistant message: {e}")
                return jsonify({"error": "Failed to retrieve assistant message", "details": str(e)}), 500

            if not assistant_message:
                app.logger.error("No assistant response received from OpenAI")
                return jsonify({"error": "No response received from assistant"}), 500

            assistant_response = assistant_message.content[0].text.value

            # Store the thread for future messages
            # Store the thread for future messages
            user_thread = UserThread(user_id=str(g.user.id), thread_id=thread.id, created_at=datetime.now())
            db.session.add(user_thread)
            db.session.commit()

            return jsonify({"threadId": thread.id, "answer": assistant_response}), 200

        except Exception as e:
            app.logger.error(f"Error in start_chat_thread: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/portfolio/chat/<string:thread_id>", methods=["POST"])
    def continue_chat_thread(thread_id):
        """
        Continue an existing chat thread with a new message.
        This endpoint is called for all subsequent messages in a conversation.
        """
        try:
            # Ensure user is authenticated
            if not hasattr(g, "user") or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401

            # Get the user question from the request body
            data = request.get_json()
            user_question = data.get("question")
            if not user_question:
                return jsonify({"error": "Question is required"}), 400

            # Verify the thread exists and belongs to this user
            user_thread = UserThread.query.filter_by(user_id=str(g.user.id), thread_id=thread_id).first()
            if not user_thread:
                return jsonify({"error": "Thread not found or unauthorized"}), 404

            # Check if any portfolio holdings have been updated since thread creation
            portfolio = Portfolio.query.filter_by(user_id=g.user.id).first()
            if portfolio:
                # Find the most recently updated holding
                latest_holding_update = (
                    db.session.query(db.func.max(PortfolioHolding.updated_at)).filter(PortfolioHolding.portfolio_id == portfolio.id).scalar()
                )

                # Check for new transactions since thread creation
                latest_transaction = db.session.query(db.func.max(Transaction.created_at)).filter(Transaction.portfolio_id == portfolio.id).scalar()

                # If holdings were updated or new transactions added after thread creation
                if (latest_holding_update and latest_holding_update > user_thread.created_at) or (
                    latest_transaction and latest_transaction > user_thread.created_at
                ):

                    # Delete old thread from OpenAI
                    try:
                        openai_client.beta.threads.delete(thread_id=thread_id)
                    except Exception as e:
                        app.logger.error(f"Error deleting outdated thread: {e}")

                    # Delete from database
                    db.session.delete(user_thread)
                    db.session.commit()

                    # Create a new thread with updated portfolio context
                    return start_chat_thread()

            # Add the user's question to the thread
            openai_client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_question)

            # Run the Assistant
            run = openai_client.beta.threads.runs.create(thread_id=thread_id, assistant_id=ASSISTANT_ID)

            # Wait for the run to complete
            run = wait_for_run_completion(thread_id, run.id, openai_client)

            # Retrieve the assistant's response
            messages = openai_client.beta.threads.messages.list(thread_id=thread_id)
            # Get the most recent assistant message
            assistant_message = next((msg for msg in messages.data if msg.role == "assistant"), None)

            if not assistant_message:
                return jsonify({"error": "No response received from assistant"}), 500

            # Extract the content from the message
            assistant_response = assistant_message.content[0].text.value

            # Update the thread's last_used timestamp
            user_thread.last_used = datetime.now()
            db.session.commit()

            return jsonify({"answer": assistant_response}), 200

        except Exception as e:
            print(f"Error in continue_chat_thread: {str(e)}")
            return jsonify({"error": str(e)}), 500
