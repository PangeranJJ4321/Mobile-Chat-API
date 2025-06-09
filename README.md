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

### Langkah-langkah Menjalankan Aplikasi

1.  **Kloning Repositori:**
    ```bash
    git clone [https://github.com/your-username/mychat-backend.git](https://github.com/your-username/mychat-backend.git)
    cd mychat-backend
    ```

2.  **Konfigurasi Environment Variables:**
    Buat file `.env` di root proyek Anda berdasarkan `.env.example`. File ini akan berisi variabel lingkungan sensitif seperti kunci rahasia, kredensial database, dll.

    ```bash
    cp .env.example .env
    ```
    Buka file `.env` dan sesuaikan nilainya dengan pengaturan lingkungan Anda (misalnya, `DATABASE_URL`, `SECRET_KEY`, `PUSHER_APP_ID`, `PUSHER_APP_KEY`, `PUSHER_APP_SECRET`, `PUSHER_APP_CLUSTER`, dll.).

    **Contoh `.env`:**
    ```
    DATABASE_URL="postgresql://user:password@db:5432/mydatabase"
    SECRET_KEY="your_super_secret_key_for_jwt"
    ALGORITHM="HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES=30

    # Pusher Configuration
    PUSHER_APP_ID="your_pusher_app_id"
    PUSHER_APP_KEY="your_pusher_app_key"
    PUSHER_APP_SECRET="your_pusher_app_secret"
    PUSHER_APP_CLUSTER="ap1" # or your cluster, e.g., us2, eu
    ```
    *Pastikan untuk menggunakan kunci rahasia yang kuat dan unik untuk `SECRET_KEY`.*

3.  **Bangun dan Jalankan Kontainer Docker:**
    Dari direktori root proyek Anda, jalankan perintah berikut:

    ```bash
    docker-compose up --build
    ```
    * `docker-compose up`: Memulai layanan yang didefinisikan dalam `docker-compose.yml`.
    * `--build`: Membangun ulang *image* Docker jika ada perubahan pada `Dockerfile` atau dependensi. Ini disarankan untuk dijalankan setidaknya sekali atau setelah Anda mengubah kode sumber.

    Perintah ini akan:
    * Membangun *image* Docker untuk aplikasi FastAPI Anda.
    * Membuat dan memulai kontainer untuk layanan FastAPI dan layanan lain yang didefinisikan (misalnya, database PostgreSQL).
    * Menampilkan log dari semua kontainer di terminal Anda.

4.  **Akses Aplikasi:**
    Setelah kontainer berjalan, aplikasi FastAPI Anda akan dapat diakses di:
    `http://localhost:8000` , `http://127.0.0.1:8000/docs`

    Dokumentasi API interaktif (Swagger UI) akan tersedia di:
    `http://localhost:8000/docs`

    Redoc akan tersedia di:
    `http://localhost:8000/redoc`

5.  **Menghentikan Aplikasi:**
    Untuk menghentikan semua layanan dan menghapus kontainer (tetapi mempertahankan data volume jika Anda menggunakannya), tekan `Ctrl+C` di terminal tempat `docker-compose up` berjalan, lalu jalankan:
    ```bash
    docker-compose down
    ```
    Jika Anda juga ingin menghapus volume data (misalnya, untuk memulai database dari awal), gunakan:
    ```bash
    docker-compose down -v
    ```

## Pengembangan

Selama pengembangan, Anda mungkin ingin menjalankan aplikasi dalam mode *watch* yang akan memuat ulang kode secara otomatis saat ada perubahan. Anda bisa menambahkan opsi *reload* ke perintah `uvicorn` di `Dockerfile` atau `docker-compose.yml` atau menjalankannya secara lokal tanpa Docker Compose.

## Lisensi

[Pilih lisensi Anda, contoh: MIT License]

---

**Catatan Penting:**

* **Ganti `your-username/mychat-backend.git`** dengan URL repositori GitHub Anda yang sebenarnya.
* **Sesuaikan `.env.example`** dengan semua variabel lingkungan yang benar-benar digunakan oleh backend Anda.
* **`Dockerfile` dan `docker-compose.yml`** harus dikonfigurasi dengan benar sesuai dengan setup spesifik backend FastAPI Anda (misalnya, port yang diekspos, volume database, layanan database, dll.). Saya asumsikan Anda sudah memiliki kedua file ini.
* **Migrasi Database (Opsional):** Jika Anda menggunakan database dan memiliki migrasi (misalnya dengan Alembic), Anda mungkin perlu menambahkan langkah migrasi ke `docker-compose.yml` atau instruksikan pengguna untuk menjalankan migrasi secara manual di dalam kontainer. Contoh:
    ```bash
    docker-compose run app alembic upgrade head
    ```
    (Ganti `app` dengan nama layanan FastAPI Anda di `docker-compose.yml`).
* **Dependensi:** Pastikan `requirements.txt` Anda berisi semua dependensi Python yang diperlukan.

Semoga ini membantu Anda membuat README yang efektif untuk repositori backend Anda!