# MyChat Backend (FastAPI)

Ini adalah layanan backend untuk aplikasi ChatOI, dibangun menggunakan FastAPI. Layanan ini menyediakan API untuk fitur-fitur seperti otentikasi pengguna, manajemen percakapan, pengiriman pesan real-time, dan lainnya.

## Teknologi

* **FastAPI**: Kerangka kerja web Python modern, cepat (berkinerja tinggi), siap produksi.
* **Python 3.x**: Bahasa pemrograman utama.
* **SQLAlchemy**: Python SQL Toolkit dan Object Relational Mapper (ORM).
* **Alembic**: Alat migrasi database yang digunakan dengan SQLAlchemy.
* **PostgreSQL/MySQL (Opsional)**: Database pilihan Anda (sesuai konfigurasi SQLAlchemy Anda).
* **Pydantic**: Validasi data dan pengaturan.
* **Uvicorn**: Server ASGI untuk menjalankan aplikasi FastAPI.
* **Pusher**: Layanan API real-time untuk pesan instan dan notifikasi.
* **Docker**: Untuk orkestrasi kontainer dan deployment yang mudah.

## Memulai dengan Docker

Cara paling sederhana untuk menjalankan backend ini adalah menggunakan Docker dan Docker Compose.

### Prasyarat

Pastikan Anda telah menginstal yang berikut ini di mesin Anda:

* [**Docker Engine**](https://docs.docker.com/engine/install/)
* [**Docker Compose**](https://docs.docker.com/compose/install/) (biasanya sudah termasuk dalam instalasi Docker Desktop)

### Konfigurasi Pusher

Backend ini menggunakan Pusher untuk fungsionalitas pesan real-time. Anda perlu mendaftar akun Pusher dan membuat aplikasi baru untuk mendapatkan kredensial yang diperlukan.

1.  **Daftar di Pusher**: Kunjungi [Pusher.com](https://pusher.com/) dan buat akun gratis.
2.  **Buat Aplikasi Baru**: Setelah login, navigasikan ke Dashboard Anda dan buat aplikasi Channels baru.
3.  **Dapatkan Kredensial**: Catat `APP_ID`, `KEY`, `SECRET`, dan `CLUSTER` yang akan Anda temukan di halaman "App Keys" aplikasi Anda.

### Konfigurasi Fitur Reset Password (React Vite Web UI)

Fitur reset password diimplementasikan dengan antarmuka web terpisah yang dibangun menggunakan **React dan Vite**. Backend Anda akan mengirim email yang berisi tautan ke halaman reset password ini.

1.  **Ekstrak File Reset Password**:
    File `reset-password.zip` berisi **kode sumber (source code) dan dependensi** dari aplikasi React Vite. Ekstrak file ini ke direktori terpisah (misalnya, `frontend-reset-password/`) di lokasi mana pun di sistem Anda.

    ```bash
    unzip reset-password_frontend.zip -d frontend-reset-password/
    ```

2.  **Jalankan Aplikasi Web Reset Password**:
    Setelah diekstrak, navigasikan ke direktori `frontend-reset-password/` dan jalankan aplikasi React Vite. Anda akan memerlukan Node.js dan npm/yarn terinstal.

    ```bash
    cd frontend-reset-password/
    npm install   # atau yarn install, untuk menginstal dependensi
    npm run dev   # atau yarn dev, untuk menjalankan development server
    ```
    Secara default, ini akan menjalankan aplikasi di `http://localhost:5173/`. Pastikan URL ini sesuai dengan konfigurasi `FRONTEND_RESET_PASSWORD_URL` di file `.env` backend. Contoh URL lengkap yang akan digunakan backend untuk mengirim tautan: `http://localhost:5173/reset-password?token=...`.

    **Catatan:** Untuk deployment produksi, Anda akan menjalankan `npm run build` dan menyajikan file-file statis yang dihasilkan melalui server web (misalnya Nginx, Apache, atau layanan hosting statis). Dalam kasus tersebut, `FRONTEND_RESET_PASSWORD_URL` akan menjadi URL server web Anda.

3.  **Konfigurasi Environment Variables Backend**:
    Pastikan file `.env` backend Anda berisi variabel `FRONTEND_RESET_PASSWORD_URL` yang menunjuk ke URL dasar di mana UI reset password Anda di-host (misalnya, `http://localhost:5173`).

### Langkah-langkah Menjalankan Aplikasi

1.  **Kloning Repositori:**
    ```bash
    git clone [https://github.com/PangeranJJ4321/Mobile-Chat-API](https://github.com/PangeranJJ4321/Mobile-Chat-API)
    cd Mobile-Chat-API
    ```

2.  **Konfigurasi Environment Variables Backend:**
    Buat file `.env` di root proyek Anda berdasarkan `.env.example`. File ini akan berisi variabel lingkungan sensitif seperti kunci rahasia, kredensial database, kredensial Pusher, dan **konfigurasi email untuk reset password**.

    ```bash
    cp .env.example .env
    ```
    Buka file `.env` dan sesuaikan nilainya dengan pengaturan lingkungan Anda.

    **Contoh `.env`:**
    ```
    # Database Configuration (Example for PostgreSQL)
    DATABASE_URL="postgresql://user:password@db:5432/mydatabase" # Pastikan 'db' cocok dengan nama layanan database di docker-compose.yml

    # Application Security Configuration
    SECRET_KEY="your_super_secret_key_for_jwt" # Ubah ini! Gunakan kunci yang kuat dan unik.
    ALGORITHM="HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES=30

    # Pusher Configuration - PENTING! Ganti dengan detail aplikasi Pusher Anda yang sebenarnya.
    PUSHER_APP_ID="your_pusher_app_id"
    PUSHER_APP_KEY="your_pusher_app_key"
    PUSHER_APP_SECRET="your_pusher_app_secret"
    PUSHER_APP_CLUSTER="ap1" # Contoh: us2, eu, ap1 (sesuai yang Anda pilih di Pusher)

    # Email Configuration for Password Reset (Example for SMTP)
    MAIL_USERNAME="your_email@example.com"
    MAIL_PASSWORD="your_email_password"
    MAIL_FROM="your_email@example.com"
    MAIL_SERVER="smtp.example.com"
    MAIL_PORT=587
    MAIL_TLS=True
    MAIL_SSL=False

    # Frontend URL for Password Reset.
    # This is the base URL where your React Vite reset password UI is hosted.
    # When running in development mode (npm run dev), this is typically http://localhost:5173/
    # If your Vite app has a base path like /reset-password, then it would be http://localhost:5173/reset-password
    FRONTEND_RESET_PASSWORD_URL="http://localhost:5173/reset-password" # SESUAIKAN DENGAN BASE URL VITE ANDA
    ```
    *Pastikan untuk menggunakan kunci rahasia yang kuat dan unik untuk `SECRET_KEY` dan ganti semua placeholder dengan kredensial Anda yang sebenarnya.*

4.  **Bangun Kontainer Docker (tanpa menjalankan):**
    Ini akan membangun *image* Docker untuk aplikasi Anda, tetapi tidak akan langsung menjalankannya. Ini diperlukan sebelum menjalankan migrasi.

    ```bash
    docker-compose build
    ```

5.  **Jalankan Migrasi Database dengan Alembic:**
    Setelah *image* dibangun, Anda dapat menjalankan migrasi database menggunakan Alembic di dalam kontainer layanan aplikasi Anda. Asumsikan nama layanan aplikasi Anda di `docker-compose.yml` adalah `app`.

    ```bash
    docker-compose run --rm app alembic upgrade head
    ```
    **Catatan:** Pastikan layanan database Anda (misalnya, `db` jika Anda menggunakan PostgreSQL di Docker Compose) sudah berjalan sebelum menjalankan migrasi ini. Anda bisa memulai layanan database saja dengan `docker-compose up -d db` jika perlu, lalu jalankan migrasi.

6.  **Jalankan Kontainer Docker (secara penuh):**
    Setelah migrasi selesai, Anda dapat memulai semua layanan aplikasi, termasuk FastAPI dan database.

    ```bash
    docker-compose up
    ```
    Jika Anda ingin membangun ulang *image* secara otomatis setiap kali ada perubahan pada `Dockerfile` atau `requirements.txt`, gunakan `--build`:
    ```bash
    docker-compose up --build
    ```

    Perintah ini akan:
    * Membuat dan memulai kontainer untuk layanan FastAPI dan layanan database Anda (jika belum berjalan).
    * Menampilkan log dari semua kontainer di terminal Anda.

7.  **Akses Aplikasi:**
    Setelah kontainer backend berjalan, aplikasi FastAPI Anda akan dapat diakses di:
    `http://localhost:8000`

    Dokumentasi API interaktif (Swagger UI) akan tersedia di:
    `http://localhost:8000/docs`

    Redoc akan tersedia di:
    `http://localhost:8000/redoc`

8.  **Menghentikan Aplikasi:**
    Untuk menghentikan semua layanan dan menghapus kontainer (tetapi mempertahankan volume data agar database tetap ada), tekan `Ctrl+C` di terminal tempat `docker-compose up` berjalan, lalu jalankan:
    ```bash
    docker-compose down
    ```
    Jika Anda juga ingin menghapus volume data (misalnya, untuk memulai database dari awal, sangat berguna untuk pengembangan lokal), gunakan:
    ```bash
    docker-compose down -v
    ```

## Pengembangan

Selama pengembangan, Anda mungkin ingin menjalankan aplikasi dalam mode *watch* yang akan memuat ulang kode secara otomatis saat ada perubahan. Anda bisa menambahkan opsi `--reload` ke perintah `uvicorn` di `Dockerfile` atau `docker-compose.yml` Anda (misalnya, `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]`).

## Lisensi

[Pilih lisensi Anda, contoh: MIT License]
