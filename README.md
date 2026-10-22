# X00TD kernel 4.4 builder

Branch ini, lineage-20, membangun kernel X00TD untuk Android 13 / LineageOS 20.
Basis builder 4.19 tetap tersedia pada branch lineage-24.0.

Default build:

| Bagian | Default |
| --- | --- |
| Source | https://github.com/Kyura-Ground/android_kernel_asus_sdm660 |
| Branch kernel | lineage-20 |
| Defconfig | X00TD_defconfig |
| Clang | AOSP clang-r450784d, snapshot 292044a13f9d1d6f42c15d56f92fe8e11e363ca0 |
| GNU cross tools | LineageOS GCC 4.9 ARM64 dan ARM32, revision dipatok di build.sh |
| KernelSU | backslashxx/KernelSU, revision a7f37595dcf067791fc2c689047a651c19d6704c |
| AnyKernel3 | Kyura-Ground/AnyKernel3, branch 4.4 |
| Output | Image.gz-dtb dan ZIP AnyKernel3 bertanda tangan |

Compiler memakai target aarch64-linux-gnu, dengan GNU assembler/linker dari
prefix aarch64-linux-android- dan arm-linux-androideabi-. Target ARM32 diatur
untuk compat vDSO. Builder ini tidak menggunakan LLVM=1, integrated assembler,
LTO, atau NoMount dari konfigurasi 4.19.

## Build di CircleCI

1. Push branch lineage-20 dari repository cooking-kernel ke GitHub.
2. Pilih branch lineage-20 saat menjalankan pipeline CircleCI untuk repository ini.
3. Gunakan parameter default, atau ubah parameter berikut saat memicu pipeline.

| Parameter pipeline | Tipe | Default |
| --- | --- | --- |
| kernel-branch | string | lineage-20 |
| build-ksu | boolean | true |
| sign-zip | boolean | true |

Job lint memeriksa sintaks Bash, ShellCheck, YAML, dan tes alur builder offline.
Job build memasang dependensi Ubuntu 22.04, mengambil source/toolchain,
menggabungkan konfigurasi KSU, membangun kernel, lalu membuat ZIP.
Executor build menggunakan resource_class large.

Hasil tersedia di tab Artifacts pada job build:

- KERNEL-BUILDS: ZIP AnyKernel3, Image.gz-dtb, kernel.config, build-manifest.txt,
  SHA256SUMS, serta System.map/Module.symvers jika dihasilkan.
- BUILD-LOGS: log build, konfigurasi akhir, revision source/compiler/KSU dan AnyKernel3.

Log tetap disimpan oleh langkah store_artifacts jika kompilasi gagal. Ini
mengikuti [perilaku artifact CircleCI](https://circleci.com/docs/reference/configuration-reference/).
Toolchain dan ccache menggunakan namespace cache khusus kernel44.

## KernelSU

BUILD_KSU=1 adalah default. Builder mengambil revision KSU yang dipatok,
menambahkan wiring Kconfig/Makefile dan symlink pada checkout kernel milik
builder, kemudian menggabungkan configs/ksu.config setelah X00TD_defconfig.

Fragment mengikuti [referensi kernel 4.19 pengguna](https://github.com/Kyura-Ground/android_kernel_asus_sdm660-4.19/blob/lineage-24.0/arch/arm64/configs/vendor/extra/ksu.config):

    CONFIG_KSU=y
    # CONFIG_KSU_DEBUG is not set
    # CONFIG_KSU_TOOLKIT is not set
    # CONFIG_KSU_EXTRAS is not set
    CONFIG_KSU_TAMPER_SYSCALL_TABLE=y

Kconfig fork yang dipatok menyediakan backend syscall-table tersebut. Opsi
TOOLKIT/EXTRAS tidak didefinisikan pada revision ini, sehingga entri nonaktifnya
dihapus oleh olddefconfig. Builder memastikan CONFIG_KSU=y dan
CONFIG_KSU_TAMPER_SYSCALL_TABLE=y benar-benar bertahan setelah resolusi
dependensi; build dihentikan bila salah satu hilang.

Integrasi hanya dilakukan pada kernel-src hasil clone. Repository kernel utama
di folder sebelah tidak diubah. Untuk memperbarui KSU secara sengaja, isi
KSU_REF dengan revision/tag yang ingin digunakan. Gunakan Manager yang cocok
dengan fork [backslashxx/KernelSU](https://github.com/backslashxx/KernelSU).

## Build lokal dan override

Dependensi Ubuntu 22.04:

    sudo apt-get update
    sudo apt-get install git openssh-client bc bison build-essential flex \
      libssl-dev libelf-dev libncurses5 libtinfo5 python3 python-is-python3 curl cpio zip unzip \
      default-jre-headless ccache ca-certificates

Jalankan:

    bash build.sh

Untuk override tetap, salin config.example.sh menjadi config.sh lalu edit.
File config.sh diabaikan Git. File tersebut dimuat setelah default environment,
sehingga nilai yang ditulis di dalamnya menang atas environment/pipeline.

Contoh override tanpa config.sh:

    BUILD_KSU=0 SIGN_ZIP=0 USE_CCACHE=0 JOBS=4 bash build.sh

WORK_DIR dapat diarahkan ke direktori kerja baru dengan path absolut.
Gunakan direktori baru untuk build ulang setelah KSU/patch diterapkan; builder
menolak checkout dengan perubahan dan tidak melakukan reset/stash otomatis.
Hapus atau pindahkan direktori kerja lama hanya bila hasilnya sudah tidak dibutuhkan.

SIGN_ZIP=0 membuat ZIP tanpa ZipSigner. SIGN_ZIP=1 mengambil ZipSigner saat belum
ada di cache. TG_BOT_TOKEN/TG_CHAT_ID dan PIXELDRAIN_API_KEY tetap opsional untuk
upload seperti builder sebelumnya; tanpa kredensial tidak ada upload eksternal.
Kegagalan upload tidak membatalkan hasil build yang sudah tersedia di Artifacts.

Patch tambahan dapat diletakkan pada patches/*.patch; masing-masing diperiksa
dengan git apply --check sebelum diterapkan.

## Verifikasi yang sudah dilakukan

- Sintaks Bash dan parsing YAML diperiksa.
- Tes offline mencakup build KSU, vanilla, jalur ZIP signing dengan signer mock,
  kegagalan kompilasi, image kosong, opsi KSU yang hilang, dan penolakan LTO/NoMount.
  Git checkout dan ZIP asli dijalankan; kompilasi/toolchain serta signer dimock.
- Fragment KSU juga diuji dengan parser Kconfig kernel lokal 4.4 dan Kconfig fork
  yang dipatok: kedua opsi KSU yang wajib tetap aktif.
- Konfigurasi juga divalidasi oleh CLI CircleCI. Kompilasi penuh dan signing
  dijalankan oleh job build; periksa hasil pipeline untuk revision yang digunakan.
  Boot di perangkat belum diuji.

Tes offline dapat diulang dengan:

    python3 tests/smoke.py
