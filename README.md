# 🥷 NH-Tools (Ninja Heroes Auto Daily Reward)

NH-Tools adalah skrip otomatisasi berbasis Python yang dirancang untuk melakukan klaim hadiah harian (Daily Reward) pada event web game **Ninja Heroes: New Era** (`kageherostudio.com`). 

Skrip ini memungkinkan pemain untuk mengelola banyak akun sekaligus dan melakukan klaim secara otomatis di latar belakang tanpa harus membuka browser setiap hari.

---

## ✨ Fitur Utama

*   🚀 **Multi-Akun:** Mendukung penambahan dan eksekusi banyak akun dalam sekali jalan.
*   ⚡ **Cepat & Asynchronous:** Memproses antrean klaim secara paralel (*concurrent*) sehingga proses eksekusi sangat cepat, bahkan untuk puluhan akun.
*   🔒 **Local Storage & Base64:** Menyimpan data akun di penyimpanan lokal (`data.json`) dengan kata sandi yang disandikan (*encode*) menggunakan format Base64.
*   ⏭️ **Skip Claim Days:** Terdapat fitur khusus untuk "merapel" atau melompati hari klaim jika PC sempat mati atau terlewat melakukan klaim di hari sebelumnya.
*   👻 **Mode Latar Belakang (Ghost Mode):** Terintegrasi penuh dengan Windows Task Scheduler via `otomatis.py` agar bot berjalan senyap tanpa memunculkan layar terminal (CMD).

---

## 🛠️ Persyaratan (Prerequisites)

Sebelum menjalankan skrip ini, pastikan sistem kamu sudah memenuhi persyaratan berikut:
*   **Python 3.7+** (Kompatibel penuh untuk versi di bawah 3.11 tanpa error `TaskGroup`).
*   Manajer paket Python (`pip`).

Library eksternal yang dibutuhkan:
*   `httpx` (Untuk manajemen sesi dan HTTP Request)
*   `beautifulsoup4` (Untuk membaca elemen HTML *Daily Reward*)

---

## 📥 Instalasi

1. Clone repositori ini ke penyimpanan lokal kamu:
   ```bash
   git clone [https://github.com/difnsy/NH-Tools.git](https://github.com/difnsy/NH-Tools.git)
