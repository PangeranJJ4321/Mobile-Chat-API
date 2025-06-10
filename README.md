<div align="center">
  <h1>🚀 ChatOI Backend</h1>
  <p><em>A modern, high-performance backend service for ChatOI chat application built with FastAPI</em></p>
  
  <!-- Tech Stack Badges -->
  <div>
    <img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
    <img src="https://img.shields.io/badge/Python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54" alt="Python">
    <img src="https://img.shields.io/badge/Docker-0db7ed?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
    <img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL">
    <img src="https://img.shields.io/badge/Real--time-Pusher-purple?style=for-the-badge&logo=pusher&logoColor=white" alt="Pusher">
    <img src="https://img.shields.io/badge/JWT-Auth-black?style=for-the-badge&logo=jsonwebtokens&logoColor=white" alt="JWT">
  </div>
  
  <br>
  
  <!-- Project Links -->
  <div>
    <h3>📱 Related Projects</h3>
    <a href="https://github.com/PangeranJJ4321/ChatOI-Mobile-App">
      <img src="https://img.shields.io/badge/📱_ChatOI_Mobile-Android-3DDC84?style=for-the-badge&logo=android&logoColor=white" alt="ChatOI Mobile App">
    </a>
    <br>
    <img src="https://img.shields.io/badge/Platform-Android-green?style=for-the-badge&logo=android&logoColor=white" alt="Android Platform">
    <img src="https://img.shields.io/badge/Language-Java-orange?style=for-the-badge&logo=openjdk&logoColor=white" alt="Java Language">
    <img src="https://img.shields.io/badge/Mobile-App-blue?style=for-the-badge&logo=smartphone&logoColor=white" alt="Mobile App">
  </div>
</div>

---

## ✨ Features

- 🔐 **User Authentication** - Secure JWT-based authentication
- 💬 **Real-time Messaging** - Instant messaging with Pusher integration
- 🔄 **Password Reset** - Email-based password recovery with React UI
- 📊 **Database Management** - SQLAlchemy ORM with Alembic migrations
- 🐳 **Docker Ready** - Containerized deployment with Docker Compose
- 📚 **API Documentation** - Interactive Swagger UI and ReDoc
- ⚡ **High Performance** - Built on FastAPI for optimal speed

---

## 🛠️ Tech Stack

| Technology | Description |
|------------|-------------|
| **[FastAPI](https://fastapi.tiangolo.com/)** | Modern, fast web framework for building APIs |
| **[Python 3.x](https://www.python.org/)** | Core programming language |
| **[SQLAlchemy](https://www.sqlalchemy.org/)** | Python SQL toolkit and ORM |
| **[Alembic](https://alembic.sqlalchemy.org/)** | Database migration tool |
| **[PostgreSQL](https://www.postgresql.org/)** | Primary database (configurable) |
| **[Pydantic](https://pydantic-docs.helpmanual.io/)** | Data validation and settings management |
| **[Uvicorn](https://www.uvicorn.org/)** | ASGI server for running FastAPI |
| **[Pusher](https://pusher.com/)** | Real-time messaging service |
| **[Docker](https://www.docker.com/)** | Containerization and deployment |

---

## 🚀 Quick Start with Docker

### Prerequisites

Ensure you have the following installed:

- 🐳 **[Docker Engine](https://docs.docker.com/engine/install/)**
- 🔧 **[Docker Compose](https://docs.docker.com/compose/install/)** (included with Docker Desktop)

### 🔧 Setup Instructions

#### 1. Clone the Repository

```bash
git clone https://github.com/PangeranJJ4321/Mobile-Chat-API
cd Mobile-Chat-API
```

#### 2. Configure Environment Variables

```bash
cp .env.example .env
```

Edit the `.env` file with your configurations:

```env
# 🗄️ Database Configuration
DATABASE_URL="postgresql://user:password@db:5432/mydatabase"

# 🔐 Security Configuration
SECRET_KEY="your_super_secret_key_for_jwt"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30

# 📡 Pusher Configuration
PUSHER_APP_ID="your_pusher_app_id"
PUSHER_APP_KEY="your_pusher_app_key"
PUSHER_APP_SECRET="your_pusher_app_secret"
PUSHER_APP_CLUSTER="ap1"

# 📧 Email Configuration
MAIL_USERNAME="your_email@example.com"
MAIL_PASSWORD="your_email_password"
MAIL_FROM="your_email@example.com"
MAIL_SERVER="smtp.example.com"
MAIL_PORT=587
MAIL_TLS=True
MAIL_SSL=False

# 🌐 Frontend Reset Password URL
FRONTEND_RESET_PASSWORD_URL="http://localhost:5173/reset-password"
```

#### 3. Build Docker Images

```bash
docker-compose build
```

#### 4. Run Database Migrations

```bash
docker-compose run --rm app alembic upgrade head
```

#### 5. Start the Application

```bash
docker-compose up
```

For development with auto-rebuild:
```bash
docker-compose up --build
```

---

## 🔧 Pusher Configuration

The backend uses Pusher for real-time messaging functionality.

### Steps:

1. **Sign up** at [Pusher.com](https://pusher.com/) 
2. **Create a new Channels app** in your dashboard
3. **Copy credentials** from the "App Keys" section:
   - `APP_ID`
   - `KEY` 
   - `SECRET`
   - `CLUSTER`
4. **Update** your `.env` file with these credentials

---

## 🔄 Password Reset Feature

The password reset functionality includes a separate React web interface.

### Setup Reset Password UI:

#### 1. Extract Frontend Files

```bash
unzip reset-password_frontend.zip -d frontend-reset-password/
```

#### 2. Install Dependencies & Run

```bash
cd frontend-reset-password/
npm install
npm run dev
```

The React app will run at `http://localhost:5173/`

#### 3. Production Deployment

For production:
```bash
npm run build
```

Serve the built files using Nginx, Apache, or a static hosting service, then update `FRONTEND_RESET_PASSWORD_URL` accordingly.

---

## 📡 API Access

Once running, access your API at:

| Service | URL | Description |
|---------|-----|-------------|
| **API Base** | `http://localhost:8000` | Main API endpoint |
| **Swagger UI** | `http://localhost:8000/docs` | Interactive API documentation |
| **ReDoc** | `http://localhost:8000/redoc` | Alternative API documentation |

---

## 🛑 Stopping the Application

### Graceful Shutdown
```bash
# Press Ctrl+C in the terminal, then:
docker-compose down
```

### Clean Shutdown (removes data volumes)
```bash
docker-compose down -v
```

---

## 🔧 Development Mode

For development with auto-reload, modify your `docker-compose.yml` or `Dockerfile` to include the `--reload` flag:

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

---

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🆘 Support

If you encounter any issues or have questions:

- 📧 Create an issue in this repository
- 📖 Check the [API documentation](http://localhost:8000/docs)
- 💬 Refer to the [FastAPI documentation](https://fastapi.tiangolo.com/)

---

<div align="center">

**Made with ❤️ by [PangeranJJ4321](https://github.com/PangeranJJ4321)**

⭐ **Star this repository if you found it helpful!**

</div>
