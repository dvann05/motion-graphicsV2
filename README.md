# Motion Video Generator (GitHub Actions, 100% Gratis)

Generator video motion graphics otomatis dari judul + naskah narasi, jalan di
GitHub Actions — tanpa server sendiri, tanpa API berbayar.

## Cara pakai

1. Push repo ini ke GitHub (publik atau privat, sama-sama bisa — repo publik
   dapat menit Actions gratis tanpa batas, repo privat dapat jatah menit gratis
   bulanan).
2. Buka tab **Actions** di repo kamu → pilih workflow **Generate Motion
   Graphics Video** → klik **Run workflow**.
3. Isi form yang muncul:
   - **Judul** — judul video, ditampilkan di scene pembuka.
   - **Narasi** — naskah lengkap. Satu kalimat = satu scene. Pisahkan kalimat
     dengan baris baru atau tanda titik (`.`/`!`/`?`).
   - **Durasi** — pilih `otomatis` supaya durasi mengikuti panjang narasi
     (hasil TTS), atau pilih durasi tetap (15/30/60/90/120 detik). Kalau
     narasi lebih pendek dari durasi tetap, scene terakhir otomatis
     diperpanjang. Kalau narasi lebih panjang, video tidak dipotong di
     tengah kalimat — pertimbangkan mempersingkat naskah.
   - **Rasio** — `9:16` (Reels/TikTok/Shorts), `16:9` (YouTube), `1:1`, atau
     `4:5` (feed Instagram/Facebook).
   - **Suara TTS** — suara Bahasa Indonesia (pria/wanita) atau Inggris.
4. Klik **Run workflow** dan tunggu (biasanya 1–5 menit tergantung panjang
   narasi).
5. Setelah selesai:
   - Video bisa diunduh dari tab **Actions** → run yang baru selesai →
     bagian **Artifacts**.
   - Video juga otomatis dibuatkan **Release** baru di tab **Releases**
     dengan file video langsung bisa diunduh/dibagikan.

## Cara kerja di balik layar

1. **Naskah dipecah per kalimat** → tiap kalimat jadi satu scene.
2. **Tiap kalimat dibacakan** pakai [`edge-tts`](https://github.com/rany2/edge-tts)
   (suara TTS Microsoft Edge, gratis, tanpa API key).
3. **Durasi tiap scene mengikuti panjang audio** kalimat tersebut.
4. Tiap scene digambar sebagai gambar (gradient + teks besar, warna beda-beda
   tiap scene) pakai Pillow, lalu di-render jadi klip video dengan efek
   **zoom pelan (Ken Burns) + fade in/out** pakai `ffmpeg`.
5. Semua klip scene digabung jadi satu video final (`ffmpeg concat`).

Semua proses jalan di runner GitHub Actions (`ubuntu-latest`) yang sudah ada
`ffmpeg`, jadi tidak perlu install apa-apa di komputer/HP kamu.

## Menjalankan di lokal (opsional, buat uji coba)

Butuh Python 3.10+ dan `ffmpeg` terpasang.

```bash
pip install -r scripts/requirements.txt

python scripts/generate_video.py \
  --judul "5 Fakta Unik Otak Manusia" \
  --narasi "Otak manusia punya sekitar 86 miliar neuron. Berat otak hanya sekitar 2 persen dari berat badan, tapi menghabiskan 20 persen energi tubuh. Otak terus berkembang sampai usia 25 tahun." \
  --durasi otomatis \
  --rasio 9:16 \
  --tts-voice id-ID-ArdiNeural \
  --output output/video.mp4
```

## Mengubah tampilan

- **Warna background per scene**: edit daftar `PALETTES` di
  `scripts/scene_builder.py`.
- **Font**: taruh file `.ttf` di `assets/fonts/` (lihat README di folder
  tersebut).
- **Kecepatan zoom / transisi**: ubah `zoom_expr` dan `TRANSITION` di
  `scripts/generate_video.py`.
- **Tambah musik latar**: setelah kamu punya musik bebas royalti, tambahkan
  mixing audio di `render_zoompan_clip` (`-filter_complex amix`) — beri tahu
  Claude kalau mau dibantu bagian ini.

## Batasan & catatan

- Ini motion graphics sederhana (teks + gradient + zoom), bukan animasi
  karakter/ilustrasi kompleks. Cocok untuk konten edukasi singkat gaya
  caption besar.
- `edge-tts` adalah proyek open-source yang memanfaatkan layanan TTS gratis
  Microsoft Edge secara tidak resmi — gratis dan stabil untuk pemakaian
  wajar, tapi bukan API resmi berbayar, jadi sewaktu-waktu bisa berubah.
- Jangan pakai teks hak cipta orang lain (kutipan panjang, lirik lagu, dll)
  di input narasi.
- GitHub Actions di repo publik: menit build gratis tanpa batas wajar. Di
  repo privat: ada kuota menit gratis bulanan (lihat Settings → Billing).
