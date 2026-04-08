# X00TD / SDM660 Kernel Builder

[![CircleCI](https://circleci.com/gh/Kyura-Ground/cooking-kernel.svg?style=shield)](https://app.circleci.com/pipelines/github/Kyura-Ground/cooking-kernel)

Repository ini berisi script dan konfigurasi CircleCI terotomatisasi yang diperuntukkan untuk melakukan kompilasi Kernel Android dari awal (khususnya untuk device ASUS Max Pro M1 / X00TD dengan SoC Snapdragon 660). 

## Repositori Utama
Skrip ini akan mengambil dependensi berikut pada saat proses build berjalan:

- **Kernel Source:** [android_kernel_asus_sdm660-4.19](https://github.com/Kyura-Ground/android_kernel_asus_sdm660-4.19) (Branch: `lineage-23.2`)
- **AnyKernel3:** [AnyKernel3](https://github.com/Kyura-Ground/AnyKernel3) (Branch: `4.19`)
- **Compiler:** [AOSP Clang r596125](https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/9b144befdfd93b90e02c663504fb9f4b95f9faf8/clang-r596125.tar.gz)

## Cara Kerja

1. **CircleCI Trigger:** Setiap ada *push* atau perubahan pada repository ini, CircleCI akan langsung menjalankan perintah kompilasi menggunakan docker `ubuntu:22.04`.
2. **Kompilasi (build.sh):** Skrip akan mengunduh source code kernel, AOSP Clang, dan memulai proses compile menggunakan argumen `make` yang sesuai standar Android ARM64.
3. **Packaging AnyKernel3:** Setelah *Image* berhasil jadi (yakni `Image.gz-dtb`), skrip akan mem-package kernel ke dalam sebuah *flashable* zip format TWRP/OrangeFox yang dirangkai secara otomatis oleh AnyKernel3.
4. **Artifacts:** *Flashable Zip* yang sudah matang dapat diunduh langsung di tab **Artifacts** yang ada di dashboard *Steps* CircleCI.

## Struktur Direktori

- `.circleci/config.yml` : Konfigurasi docker, environments, dan job step dari mesin CircleCI.
- `build.sh` : Skrip bash yang mengeksekusi proses fetching (*download*), kompilasi (*make*), dan *packaging* (AnyKernel).

## Cara Menggunakan (Fork & Run)

Jika Anda ingin menjalankan build Anda sendiri dan mengaktifkan notifikasi Telegram:
1. *Fork* repository ini ke akun Github Anda.
2. Sign in di [CircleCI](https://circleci.com) menggunakan Github Anda.
3. Klik **Projects** lalu *Set Up Project* untuk repository ini. Ikuti opsi default menggunakan config `.circleci/config.yml` yang sudah ada (*Fastest Options*).
4. **(Opsional) Setup Telegram Bot:** Di project CircleCI Anda, buka **Project Settings** > **Environment Variables** lalu tambahkan dua *secret variable* berikut:
   - `TG_BOT_TOKEN` : Berisi Token Bot Telegram Anda (dari @BotFather).
   - `TG_CHAT_ID` : Berisi Chat ID tujuan pengiriman (bisa grup, channel, atau akun pribadi Anda).
5. Build akan langsung berjalan dan file zip bisa di-download setelah sukses (serta otomatis dikirimkan ke Telegram apabila Variabel Environment diaktifkan).
6. Anda juga bebas mengubah environment / target repository di dalam file `build.sh`.

---

*Automated Compiler setup built with CircleCI.*
