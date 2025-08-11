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

<img width="1796" height="1033" alt="home" src="https://github.com/user-attachments/assets/98921921-3d28-4247-a47c-5a1725440a44" />
<img width="1795" height="1035" alt="register" src="https://github.com/user-attachments/assets/33585637-8322-407d-ae67-5057eff101f2" />
<img width="1798" height="1036" alt="login" src="https://github.com/user-attachments/assets/d63939b4-4fa3-4ad2-b6d7-7248f2dfdfa2" />

<img width="1800" height="1034" alt="portfolio" src="https://github.com/user-attachments/assets/e3ea6cc3-06c3-40ef-a151-f7a0bd4afacd" />
<img width="1797" height="1035" alt="input" src="https://github.com/user-attachments/assets/3d2657cd-c647-4d23-8c6c-bd03f3b8abea" />
<img width="1799" height="1036" alt="watchlist" src="https://github.com/user-attachments/assets/89c3fb63-39d9-4db7-9d27-ace2ca7cd7b6" />
<img width="1800" height="1039" alt="explore_watchlist" src="https://github.com/user-attachments/assets/274f2dd3-4e4a-405d-bda0-6ff4286402dd" />
<img width="1799" height="1037" alt="agent" src="https://github.com/user-attachments/assets/e0dbbd0c-a2da-4927-8123-2ca058410a1a" />

