# routes.py
import uuid
from re import findall
import os
import time
import json
import requests
import pandas as pd
import csv
import openai

from flask import Flask, jsonify, request, g
from firebase_admin import auth
from finvizfinance.quote import finvizfinance
from finvizfinance.news import News
from io import StringIO
from datetime import datetime
from datetime import datetime, timedelta
from collections import defaultdict

from models import db, User, Watchlist, Portfolio, Transaction, PortfolioHolding, UserThread
from helpers import convert_data, safe_convert, parse_csv_with_mapping, fetch_stock_data, fetch_market_price, recalc_portfolio, fetch_stock_sector, wait_for_run_completion, cleanup_old_threads

openai.api_key = os.getenv("OPENAI_AGENT_API_KEY")
ASSISTANT_ID = os.getenv("STOCKR_ASSISTANT_ID")

def register_routes(app):

    # Before each request, check Firebase token for protected endpoints.
    @app.before_request
    def authenticate():
        if request.method == "OPTIONS":
            return  # Skip auth for preflight
        protected_endpoints = [
            'add_to_watchlist', 'get_watchlist_stocks', 'delete_from_watchlist',
            'get_stock_historical', 'get_crypto_historical', 'get_cash_balance',
            'add_portfolio_entry', 'get_portfolio_for_graph', 'get_portfolio', 'deposit_cash',
            'withdraw_cash', 'delete_transaction', 'get_transactions', 'buy_asset', 'sell_asset',
            'get_portfolio_id', 'sell_portfolio_asset', 'add_portfolio_asset', 'get_stock_market_price',
            'search_stocks', 'upload_transactions', 'get_portfolio_assistant_context', 'start_chat_thread',
            'continue_chat_thread', 'get_portfolio_history'
        ]
        if request.endpoint in protected_endpoints:
            auth_header = request.headers.get('Authorization')
            if not auth_header or 'Bearer ' not in auth_header:
                return jsonify({"error": "Unauthorized"}), 401
            id_token = auth_header.split('Bearer ')[1]
            try:
                decoded_token = auth.verify_id_token(id_token)
                g.user = User.query.filter_by(firebase_uid=decoded_token['uid']).first()
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
                "inside_trader": inside_trader
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
        if not data or 'ticker' not in data:
            return jsonify({"error": "Ticker is required"}), 400
        ticker = data['ticker'].upper()
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
        api_key = os.getenv('ALPHAVANTAGE_API_KEY', 'IH7UCOABIKN6Y6KH')
        symbol = symbol.upper()
        url = f'https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY_ADJUSTED&symbol={symbol}&outputsize=full&apikey={api_key}'
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
        api_key = os.getenv('ALPHAVANTAGE_API_KEY', 'IH7UCOABIKN6Y6KH')
        symbol = symbol.upper()
        url = f'https://www.alphavantage.co/query?function=DIGITAL_CURRENCY_DAILY&symbol={symbol}&market=USD&apikey={api_key}'
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
                    news_data_converted[key] = value.to_dict(orient='records')
                else:
                    news_data_converted[key] = value
            response = {"relevant_news": news_data_converted}
            return jsonify(response), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/ticker-search", methods=["GET"])
    def get_ticker():
        keyword = request.args.get('keywords', 'Microsoft')
        api_key = os.getenv('ALPHAVANTAGE_API_KEY', 'IH7UCOABIKN6Y6KH')
        url = f'https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={keyword}&apikey={api_key}'
        r = requests.get(url)
        if r.status_code != 200:
            return jsonify({"error": "Failed to fetch data from Alpha Vantage"}), 500
        data = r.json()
        return jsonify(data), 200

    @app.route("/api/news-sentiment", methods=["GET"])
    def get_news_sentiment():
        tickers = request.args.get('tickers')
        if not tickers:
            return jsonify({"error": "The 'tickers' query parameter is required."}), 400
        topics = request.args.get('topics')
        api_key = os.getenv('ALPHAVANTAGE_API_KEY', 'IH7UCOABIKN6Y6KH')
        url = f'https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={tickers}'
        if topics:
            url += f'&topics={topics}'
        url += f'&apikey={api_key}'
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
        symbol = request.args.get('symbol')
        if not symbol:
            return jsonify({"error": "The 'symbol' query parameter is required."}), 400
        api_key = os.getenv('ALPHAVANTAGE_API_KEY', 'IH7UCOABIKN6Y6KH')
        url = f'https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol={symbol}&apikey={api_key}'
        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.RequestException as req_err:
            return jsonify({"error": f"Failed to fetch data from Alpha Vantage: {req_err}"}), 500
        data = response.json()
        return jsonify(data), 200

    @app.route("/api/balance-sheet", methods=["GET"])
    def get_balance_sheet():
        symbol = request.args.get('symbol')
        if not symbol:
            return jsonify({"error": "The 'symbol' query parameter is required."}), 400
        api_key = os.getenv('ALPHAVANTAGE_API_KEY', 'IH7UCOABIKN6Y6KH')
        url = f'https://www.alphavantage.co/query?function=BALANCE_SHEET&symbol={symbol}&apikey={api_key}'
        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.RequestException as req_err:
            return jsonify({"error": f"Failed to fetch data from Alpha Vantage: {req_err}"}), 500
        data = response.json()
        return jsonify(data), 200

    @app.route("/api/cash-flow", methods=["GET"])
    def get_cash_flow():
        symbol = request.args.get('symbol')
        if not symbol:
            return jsonify({"error": "The 'symbol' query parameter is required."}), 400
        api_key = os.getenv('ALPHAVANTAGE_API_KEY', 'IH7UCOABIKN6Y6KH')
        url = f'https://www.alphavantage.co/query?function=CASH_FLOW&symbol={symbol}&apikey={api_key}'
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
            if not hasattr(g, 'user') or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401
            portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found or unauthorized"}), 404
            portfolio_entries = PortfolioHolding.query.filter_by(portfolio_id=portfolio_id).all()
            portfolio_list = [{
                "ticker": entry.ticker,
                "shares": float(entry.shares),
                "average_cost": float(entry.average_cost) if entry.average_cost is not None else 0,
                "book_value": float(entry.book_value) if entry.book_value is not None else 0,
                "market_value": 0
            } for entry in portfolio_entries]
            return jsonify({"portfolio": portfolio_list}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/portfolio/buy", methods=["POST"])
    def buy_asset():
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided."}), 400
        ticker = data.get('ticker')
        shares = data.get('shares')
        price = data.get('price')
        if not ticker or shares is None or price is None:
            return jsonify({"error": "Ticker, shares, and price are required."}), 400
        ticker = ticker.upper()
        try:
            user = g.user
            portfolio = Portfolio.query.filter_by(user_id=user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found"}), 404
            new_txn = Transaction(
                portfolio_id=portfolio.id,
                ticker=ticker,
                shares=shares,
                price=price,
                transaction_type="buy"
            )
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
        ticker = data.get('ticker')
        shares = data.get('shares')
        price = data.get('price')
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
            new_txn = Transaction(
                portfolio_id=portfolio.id,
                ticker=ticker,
                shares=shares,
                price=price,
                transaction_type="sell"
            )
            db.session.add(new_txn)
            db.session.commit()
            recalc_portfolio(portfolio.id, ticker)
            return jsonify({"message": "Asset sold successfully.", "ticker": ticker}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/portfolio/<string:portfolio_id>/add-asset", methods=["POST"])
    def add_portfolio_asset(portfolio_id):
        try:
            if not hasattr(g, 'user') or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401
            data = request.get_json()
            if not data:
                return jsonify({"error": "No data provided."}), 400
            ticker = data.get('ticker')
            shares = data.get('shares')
            price = data.get('price')
            transaction_type = data.get('transaction_type', 'buy').lower()
            if not ticker or shares is None or price is None:
                return jsonify({"error": "Ticker, shares, and price are required."}), 400
            ticker = ticker.upper()
            portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found or unauthorized"}), 404
            new_txn = Transaction(
                portfolio_id=portfolio.id,
                ticker=ticker,
                shares=shares,
                price=price,
                transaction_type=transaction_type
            )
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
            if not hasattr(g, 'user') or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401
            data = request.get_json()
            if not data:
                return jsonify({"error": "No data provided."}), 400
            ticker = data.get('ticker')
            shares = data.get('shares')
            price = data.get('price')
            transaction_type = 'sell'
            if not ticker or shares is None or price is None:
                return jsonify({"error": "Ticker, shares, and price are required."}), 400
            ticker = ticker.upper()
            portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found or unauthorized"}), 404
            portfolio_entry = PortfolioHolding.query.filter_by(portfolio_id=portfolio.id, ticker=ticker).first()
            if not portfolio_entry or portfolio_entry.shares < shares:
                return jsonify({"error": "Insufficient shares to sell"}), 400
            new_txn = Transaction(
                portfolio_id=portfolio.id,
                ticker=ticker,
                shares=shares,
                price=price,
                transaction_type=transaction_type
            )
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
            if not hasattr(g, 'user') or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401
            portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found or unauthorized"}), 404
            portfolio_entries = PortfolioHolding.query.filter_by(portfolio_id=portfolio_id).all()
            portfolio_list = [{
                "ticker": entry.ticker,
                "book_value": float(entry.book_value) if entry.book_value is not None else 0
            } for entry in portfolio_entries]
            return jsonify({"portfolio": portfolio_list}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/transactions", methods=["GET"])
    def get_transactions():
        try:
            if not hasattr(g, 'user') or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401
            portfolio = Portfolio.query.filter_by(user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found"}), 404
            transactions = Transaction.query.filter_by(portfolio_id=portfolio.id).order_by(Transaction.created_at.desc()).limit(15).all()
            transactions_list = [{
                "id": txn.id,
                "ticker": txn.ticker,
                "shares": float(txn.shares),
                "price": float(txn.price),
                "transaction_type": txn.transaction_type,
                "created_at": txn.created_at.isoformat()
            } for txn in transactions]
            return jsonify({"transactions": transactions_list}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/transactions/<string:transaction_id>", methods=["DELETE"])
    def delete_transaction(transaction_id):
        try:
            if not hasattr(g, 'user') or g.user is None:
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
            if transaction.transaction_type.lower() == 'buy':
                if holding:
                    holding.shares -= shares
                    holding.book_value -= total_value
                    if holding.shares <= 0:
                        db.session.delete(holding)
            elif transaction.transaction_type.lower() == 'sell':
                if holding:
                    holding.shares += shares
                    holding.book_value += total_value
                else:
                    new_holding = PortfolioHolding(
                        id=str(uuid.uuid4()),
                        portfolio_id=portfolio.id,
                        ticker=ticker,
                        shares=shares,
                        average_cost=price,
                        book_value=total_value
                    )
                    db.session.add(new_holding)
            db.session.delete(transaction)
            db.session.commit()
            return jsonify({
                "message": "Transaction deleted successfully.",
                "updated_portfolio": {
                    "ticker": ticker,
                    "shares": float(holding.shares) if holding else 0,
                    "book_value": float(holding.book_value) if holding else 0
                }
            }), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/users", methods=["POST"])
    def create_user():
        try:
            data = request.get_json()
            print("Received data:", data)
            if not data or 'firebase_uid' not in data:
                return jsonify({"error": "Firebase UID is required"}), 400
            existing_user = User.query.filter_by(firebase_uid=data['firebase_uid']).first()
            if existing_user:
                portfolio = Portfolio.query.filter_by(user_id=existing_user.id).first()
                return jsonify({
                    "message": "User already exists",
                    "user_id": existing_user.id,
                    "portfolio_id": portfolio.id if portfolio else None
                }), 200
            new_user = User(id=str(uuid.uuid4()), firebase_uid=data['firebase_uid'])
            db.session.add(new_user)
            db.session.commit()
            new_portfolio = Portfolio(id=str(uuid.uuid4()), user_id=new_user.id)
            db.session.add(new_portfolio)
            db.session.commit()
            print("User and portfolio created successfully:", new_user.id, new_portfolio.id)
            return jsonify({
                "message": "User created",
                "user_id": new_user.id,
                "portfolio_id": new_portfolio.id
            }), 201
        except Exception as e:
            print("Error creating user:", str(e))
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    @app.route("/api/portfolio/id", methods=["GET"])
    def get_portfolio_id():
        try:
            if not hasattr(g, 'user') or g.user is None:
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
        if not hasattr(g, 'user') or g.user is None:
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
                        created_at=created_at_val
                    )
                else:
                    new_txn = Transaction(
                        portfolio_id=portfolio.id,
                        ticker=ticker,
                        shares=shares,
                        price=price,
                        transaction_type=transaction_type
                    )

                db.session.add(new_txn)
                transactions_added += 1

            if transactions_added > 0:
                db.session.commit()
                # Recalculate portfolio holdings for each unique ticker.
                for ticker in tickers_set:
                    recalc_portfolio(portfolio.id, ticker)

            if errors:
                return (
                    jsonify({
                        "message": f"{transactions_added} transactions added with some errors.",
                        "errors": errors,
                    }),
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
        Calculates the portfolio's value over time based on transaction history.
        Returns data points for plotting a line chart of portfolio growth.
        """
        try:
            if not hasattr(g, 'user') or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401

            # Verify the portfolio belongs to the user
            portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "Portfolio not found or unauthorized"}), 404

            # Get all transactions sorted by date
            transactions = Transaction.query.filter_by(portfolio_id=portfolio_id).order_by(Transaction.created_at).all()

            if not transactions:
                return jsonify({"history": [], "message": "No transactions found"}), 200

            # Compute portfolio value after each transaction
            portfolio_history = []
            holdings = {}  # ticker -> {shares, value}
            total_value = 0

            # Group transactions by date (day)
            from collections import defaultdict
            daily_snapshots = defaultdict(list)

            for txn in transactions:
                txn_date = txn.created_at.date()
                daily_snapshots[txn_date].append(txn)

            # Process each day's transactions
            for day, day_txns in sorted(daily_snapshots.items()):
                day_value = 0

                # Apply all transactions for this day
                for txn in day_txns:
                    ticker = txn.ticker
                    shares = float(txn.shares)
                    price = float(txn.price)
                    txn_value = shares * price

                    # Initialize ticker if not present
                    if ticker not in holdings:
                        holdings[ticker] = {"shares": 0, "value": 0}

                    # Update holdings based on transaction type
                    if txn.transaction_type.lower() == 'buy':
                        holdings[ticker]["shares"] += shares
                        holdings[ticker]["value"] += txn_value
                        total_value += txn_value
                    elif txn.transaction_type.lower() == 'sell':
                        # Calculate the portion of value to remove
                        if holdings[ticker]["shares"] > 0:
                            value_per_share = holdings[ticker]["value"] / holdings[ticker]["shares"]
                            value_to_remove = shares * value_per_share
                            holdings[ticker]["shares"] -= shares
                            holdings[ticker]["value"] -= value_to_remove
                            total_value -= value_to_remove

                            # Add the profit/loss to the total value
                            profit_loss = txn_value - value_to_remove
                            total_value += profit_loss

                # Get market prices for each holding on this day
                # Note: For historical data, we'd normally use a service with historical prices
                # For now, we'll use the transaction prices as an approximation
                for ticker, holding in holdings.items():
                    if holding["shares"] > 0:
                        # For each ticker, find the latest transaction price on or before this day
                        latest_price = None
                        for t in transactions:
                            if t.ticker == ticker and t.created_at.date() <= day:
                                latest_price = float(t.price)

                        if latest_price:
                            day_value += holding["shares"] * latest_price

                # Add data point for this day
                portfolio_history.append({
                    "date": day.isoformat(),
                    "value": day_value
                })

            # Fill in any missing days with the previous day's value to create a continuous line
            if portfolio_history:
                filled_history = []
                current_date = datetime.strptime(portfolio_history[0]["date"], "%Y-%m-%d").date()
                end_date = datetime.strptime(portfolio_history[-1]["date"], "%Y-%m-%d").date()
                idx = 0

                while current_date <= end_date:
                    date_str = current_date.isoformat()

                    if idx < len(portfolio_history) and portfolio_history[idx]["date"] == date_str:
                        filled_history.append(portfolio_history[idx])
                        idx += 1
                    else:
                        # Use the previous day's value
                        prev_value = filled_history[-1]["value"] if filled_history else 0
                        filled_history.append({
                            "date": date_str,
                            "value": prev_value
                        })

                    current_date += timedelta(days=1)

                return jsonify({"history": filled_history}), 200
            else:
                return jsonify({"history": [], "message": "No portfolio history available"}), 200

        except Exception as e:
            app.logger.error(f"Error calculating portfolio history: {e}")
            return jsonify({"error": str(e)}), 500

    # --- Assistant ---

    @app.route('/api/portfolio/chat', methods=['POST'])
    def start_chat_thread():
        try:
            # Ensure user is authenticated
            if not hasattr(g, 'user') or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401

            data = request.get_json()
            user_question = data.get("question")
            if not user_question:
                return jsonify({"error": "Question is required"}), 400

            # Get the user's portfolio (removed is_default filter since Portfolio doesn't have it)
            portfolio = Portfolio.query.filter_by(user_id=g.user.id).first()
            if not portfolio:
                return jsonify({"error": "No portfolio found for this user"}), 404

            # Retrieve portfolio holdings
            portfolio_entries = PortfolioHolding.query.filter_by(portfolio_id=portfolio.id).all()
            if not portfolio_entries:
                # Provide a default message if no holdings exist.
                portfolio_context = "You currently do not have any portfolio holdings."
            else:
                portfolio_context = "Portfolio Holdings:\n"
                for entry in portfolio_entries:
                    sector = fetch_stock_sector(entry.ticker) or "Unknown"
                    total_value = float(entry.shares) * float(entry.average_cost)
                    portfolio_context += (
                        f"- {entry.ticker.upper()} ({sector}): "
                        f"{float(entry.shares):.2f} shares at avg ${float(entry.average_cost):.2f}, "
                        f"total value ${total_value:.2f}. More info: https://ca.finance.yahoo.com/quote/{entry.ticker.upper()}\n"
                    )

            # Create a new thread
            try:
                thread = openai.beta.threads.create()
            except Exception as e:
                app.logger.error(f"Error creating OpenAI thread: {e}")
                return jsonify({"error": "Failed to create chat thread", "details": str(e)}), 500

            # Send system message with portfolio context
            try:
                openai.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=portfolio_context
                )
            except Exception as e:
                app.logger.error(f"Error sending system message: {e}")
                return jsonify({"error": "Failed to send system message", "details": str(e)}), 500

            # Send the user's question
            try:
                openai.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=user_question
                )
            except Exception as e:
                app.logger.error(f"Error sending user message: {e}")
                return jsonify({"error": "Failed to send user message", "details": str(e)}), 500

            # Start the assistant run
            try:
                run = openai.beta.threads.runs.create(
                    thread_id=thread.id,
                    assistant_id=ASSISTANT_ID,
                    instructions="Please use the provided portfolio context to generate an insightful and actionable answer."
                )
            except Exception as e:
                app.logger.error(f"Error starting OpenAI run: {e}")
                return jsonify({"error": "Failed to start chat run", "details": str(e)}), 500

            # Wait for the run to complete
            try:
                run = wait_for_run_completion(thread.id, run.id)
            except Exception as e:
                app.logger.error(f"Error waiting for run completion: {e}")
                return jsonify({"error": "Chat run did not complete", "details": str(e)}), 500

            # Retrieve assistant's response
            try:
                messages_response = openai.beta.threads.messages.list(thread_id=thread.id)
                assistant_message = next((msg for msg in messages_response.data if msg.role == "assistant"), None)
            except Exception as e:
                app.logger.error(f"Error retrieving assistant message: {e}")
                return jsonify({"error": "Failed to retrieve assistant message", "details": str(e)}), 500

            if not assistant_message:
                app.logger.error("No assistant response received from OpenAI")
                return jsonify({"error": "No response received from assistant"}), 500

            assistant_response = assistant_message.content[0].text.value

            # Store the thread for future messages
            user_thread = UserThread(
                user_id=g.user.id,
                thread_id=thread.id,
                created_at=datetime.now()
            )
            db.session.add(user_thread)
            db.session.commit()

            return jsonify({
                "threadId": thread.id,
                "answer": assistant_response
            }), 200

        except Exception as e:
            app.logger.error(f"Error in start_chat_thread: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route('/api/portfolio/chat/<string:thread_id>', methods=['POST'])
    def continue_chat_thread(thread_id):
        """
        Continue an existing chat thread with a new message.
        This endpoint is called for all subsequent messages in a conversation.
        """
        try:
            # Ensure user is authenticated
            if not hasattr(g, 'user') or g.user is None:
                return jsonify({"error": "User not authenticated"}), 401

            # Get the user question from the request body
            data = request.get_json()
            user_question = data.get("question")
            if not user_question:
                return jsonify({"error": "Question is required"}), 400

            # Verify the thread exists and belongs to this user
            user_thread = UserThread.query.filter_by(user_id=g.user.id, thread_id=thread_id).first()
            if not user_thread:
                return jsonify({"error": "Thread not found or unauthorized"}), 404

            # Add the user's question to the thread
            openai.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=user_question
            )

            # Run the Assistant
            run = openai.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=ASSISTANT_ID
            )

            # Wait for the run to complete
            run = wait_for_run_completion(thread_id, run.id)

            # Retrieve the assistant's response
            messages = openai.beta.threads.messages.list(thread_id=thread_id)
            # Get the most recent assistant message
            assistant_message = next((msg for msg in messages.data if msg.role == "assistant"), None)

            if not assistant_message:
                return jsonify({"error": "No response received from assistant"}), 500

            # Extract the content from the message
            assistant_response = assistant_message.content[0].text.value

            # Update the thread's last_used timestamp
            user_thread.last_used = datetime.now()
            db.session.commit()

            return jsonify({
                "answer": assistant_response
            }), 200

        except Exception as e:
            print(f"Error in continue_chat_thread: {str(e)}")
            return jsonify({"error": str(e)}), 500