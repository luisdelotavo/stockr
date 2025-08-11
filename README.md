# Stockr

Personal finance dashboard created using React, Next.js, Flask, Firebase Authentication, Postgres, and OpenAI Assistant.
Track portfolio performance, distribution, create watchlists with stock summaries, and leverage OpenAI Assistant for personalized investment recommendations.

Accessible through https://www.stockr.info/

## Tech Stack

### **Frontend (Client)**
- **Framework**: Next.js 15.1.6 (React-based)
- **Language**: TypeScript 5
- **UI Framework**: React 19.0.0
- **Styling**: Tailwind CSS 3.4.1
- **Data Visualization**: Chart.js 4.4.7 with react-chartjs-2
- **Icons**: Heroicons & FontAwesome
- **Authentication**: Firebase 11.2.0 (client-side)

### **Backend (Server)**
- **Language**: Python
- **Framework**: Flask 2.2.5
- **ORM**: Flask-SQLAlchemy 3.0.3
- **CORS**: Flask-CORS 4.0.0
- **Production Server**: Gunicorn 21.2.0
- **Authentication**: Firebase Admin SDK 6.2.0
- **Financial Data**: 
  - yfinance 0.2.33 (Yahoo Finance API)
  - finvizfinance 1.1.0 (Finviz data)
- **AI/ML**: OpenAI API integration
- **Data Processing**: Pandas 1.5.3 & NumPy 1.26.3

### **Database**
- **Database**: PostgreSQL 15 (Alpine Linux)
- **Driver**: psycopg2-binary 2.9.7
- **Models**: User, Portfolio, Holdings, Transactions, Watchlist, UserThread

### **Infrastructure & DevOps**
- **Containerization**: Docker
- **Orchestration**: Docker Compose
- **Architecture**: Multi-container setup (frontend, backend, database)
- **Environment Management**: python-dotenv

## Key Features
- Portfolio tracking and management
- Stock watchlist functionality
- Real-time financial data integration
- AI-powered features for analysis and recommendations
- User authentication and personalized data
- Data visualization with interactive charts
- Transaction history tracking
- Modern responsive UI with Tailwind CSS

## Architecture
The application follows a modern full-stack approach with a React/Next.js frontend, Python/Flask backend, PostgreSQL database, and Firebase for authentication, all containerized with Docker for easy deployment and development.

## Depracated
The hosted demo at https://www.stockr.info/ is offline to avoid ongoing infrastructure costs.  
- The repo remains available for reference and local use. Screenshots below reflect the final production build.


