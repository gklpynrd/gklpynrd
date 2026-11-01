---
name: dikis-reels-editor
description: Dikiş / terzilik / refashion / thrift flip / el işi videolarını Instagram Reels ve TikTok için dikey (9:16), kısa, yüksek izlenme süreli içeriklere dönüştürür. Ham çekimleri analiz eder, hook'u başa alır, uzun dikiş bölümlerini hızlandırır, ekran yazısı/altyazı basar, müzik ekler ve final "reveal" ile bitirir. Ayrıca başarılı dikiş içerik üreticilerinin referans videolarının kurgu ritmini (kesim sıklığı, çekim süreleri, yazı kullanımı) ölçer ve aynı ritmi kopyalar. Kullanıcı dikiş videosu, reels, tiktok, kurgu, edit, montaj, "before/after", "sew with me", "bunu ben diktim" gibi bir şey istediğinde kullan.
---

# Dikiş Reels/TikTok Editörü

Amaç: Kullanıcının ham dikiş çekimlerinden, en iyi dikiş içerik üreticilerinin kullandığı
kurgu kalıplarıyla 15–45 saniyelik dikey videolar üretmek. Tüm işlem `ffmpeg` + bu klasördeki
Python script'leriyle yapılır.

Önce `references/formatlar.md` dosyasını oku — format şablonları, hook kütüphanesi ve
ritim kuralları orada. Bu dosya sadece iş akışını anlatır.

## Dosyalar

| Dosya | Ne işe yarar |
|---|---|
| `references/formatlar.md` | 6 kanıtlanmış dikiş formatı, hook cümleleri, ritim/yazı/ses kuralları |
| `scripts/analiz.py` | Bir videonun kurgu DNA'sını çıkarır: kesim zamanları, ortalama çekim süresi, ilk 3 sn'deki kesim sayısı, ses seviyesi, kontak sayfası (kare ızgarası) |
| `scripts/sessizlik.py` | Ham çekimde sessiz/ölü bölümleri ve hareketsiz bölümleri bulur → kesim önerisi |
| `scripts/kurgu.py` | JSON kurgu planından final videoyu render eder (9:16 kırpma, hız, zoom, yazı, altyazı, müzik, ducking, loudnorm) |
| `scripts/ornek_plan.json` | Plan formatı örneği |

Script yolu: `SKILL_DIR=.claude/skills/dikis-reels-editor` (gerekirse `~/.claude/skills/...`).

## İş akışı

### 1. Girdiyi topla
Kullanıcıdan şunları al (eksikse sor, ama varsayılanla ilerleyebiliyorsan sorma):
- Ham video dosya(lar)ı. Varsa ayrıca **bitmiş ürünün giyildiği / gösterildiği** çekim (reveal).
- Ne dikildi? (ör. "eski kot ceketten korse", "ilk elbisem", "perde kumaşından etek")
- Platform: TikTok, Instagram veya ikisi (varsayılan: ikisi — tek 9:16 dosya, güvenli alanlara uygun).
- Ses tercihi: makine sesi (ASMR), seslendirme, trend müzik, ya da karışım.
- (İsteğe bağlı) Referans: beğendiği bir üreticinin videosu (indirilmiş dosya).

Müzik: Telifli trend şarkıları videoya gömme. Ya kullanıcının verdiği/telifsiz müziği kullan ya da
müziksiz (makine sesi + seslendirme) render et ve kullanıcıya "trend sesi uygulamada ekle" de —
TikTok/IG'de uygulama içinden eklenen trend ses keşfedilmeye de yardım eder.

### 2. Referans analizi (varsa)
```bash
python3 -I $SKILL_DIR/scripts/analiz.py referans.mp4 --out analiz_ref/
```
Çıktıdaki `ozet.json`'u ve `kontak.jpg`'yi incele (Read ile görsele bak). Şunları not et:
ortalama çekim süresi, ilk 3 sn kesim sayısı, toplam süre, reveal'in videonun neresinde olduğu,
ekranda yazı olup olmadığı (kontak sayfasından), yüz/eller/makine oranı.
Kurgu planını bu sayılara yaklaştır. Referans yoksa `formatlar.md`'deki varsayılan ritmi kullan.

### 3. Ham çekimi tanı
```bash
python3 -I $SKILL_DIR/scripts/analiz.py ham.mp4 --out analiz_ham/ --kare-sayisi 24
python3 -I $SKILL_DIR/scripts/sessizlik.py ham.mp4
```
Kontak sayfasına bakarak "altın anları" bul ve zaman damgalarını çıkar:
- **Reveal**: bitmiş ürün, giyilmiş hali, dönme/twirl, aynada bakış
- **Before**: eski giysi / kumaş topu / kalıp
- **Tatmin edici anlar**: makas kumaşı kesiyor, iğne yakın plan, overlok, ütü buharı, düğme takma, kalıp üstüne çizim
- **Sorun/drama anı**: hata, sökme, "olmadı" anı (izleyiciyi tutar)
Ölü süreleri (sessizlik + hareketsizlik) at.

### 4. Format seç ve plan yaz
`formatlar.md`'den en uygun formatı seç (ör. Before→After Refashion, Sew With Me ASMR,
"X saatte diktim", Hata→Çözüm, Kalıp/Teknik ipucu, Giy-Göster). Ardından plan JSON'u yaz
(`ornek_plan.json` örneğine bak). Kurallar:
- **0–1.5 sn**: Hook. Neredeyse her zaman sonucu (reveal) veya en çarpıcı anı başa koy + büyük ekran yazısı.
- **Gövde**: 0.4–1.5 sn'lik çekimler, ritme göre kes. Uzun dikiş bölümleri `speed: 4–16`.
  Her 2–3 sn'de bir görsel değişim (açı, zoom, yazı).
- **Son 2–4 sn**: Reveal / giyme / dönme, normal hızda veya hafif slow-mo (`speed: 0.7`).
- **Loop**: Son kare, ilk kareye bağlanacak şekilde bitir (aynı poz/kumaş), tekrar izlemeyi artırır.
- Toplam: 15–35 sn (ASMR/tutorial 45–60 sn'ye kadar çıkabilir).
- Yazılar ekranın orta-üst bölgesinde (alt %20 ve sağ kenar platform arayüzüyle kaplanır).

### 5. Render
```bash
python3 -I $SKILL_DIR/scripts/kurgu.py plan.json
```
Script her klibi 1080x1920 / 30 fps'e normalize eder, hız + zoom uygular, birleştirir, ASS
altyazıları basar, müziği ekler (konuşma/makine sesi varken müziği kısar), -14 LUFS'a normalize eder.

### 6. Kontrol et (zorunlu)
```bash
python3 -I $SKILL_DIR/scripts/analiz.py cikti.mp4 --out analiz_cikti/
```
Kontak sayfasına bak: yazılar okunuyor mu, güvenli alanda mı, ilk kare çarpıcı mı, siyah kare var mı?
Ortalama çekim süresi hedefe (referansa) yakın mı? Sorun varsa planı düzelt, yeniden render et.

### 7. Teslim
Kullanıcıya ver:
1. Video dosyası (SendUserFile ile).
2. **Açıklama metni** (caption): ilk satır merak uyandıran hook, 1–3 cümle hikâye, soru ile bitiş
   ("Siz olsanız hangi rengi seçerdiniz?").
3. **Hashtag'ler**: 3–6 adet, niş + geniş karışık (ör. #dikiş #refashion #thriftflip #sewing #elyapımı #diybykendim).
4. **Kapak önerisi**: hangi saniyedeki kare kapak olmalı + kapak yazısı.
5. Platform notu: TikTok'ta trend ses ekleme önerisi; IG'de "Paylaşırken Reels kapağını ayarla".
6. Varyasyon önerisi: aynı çekimden 2. bir video (farklı hook veya farklı format) — dikiş içeriğinde
   bir proje genelde 2–4 video çıkarır (süreç, sonuç, hata, ipucu).

## Notlar
- Yatay çekim gelirse: `kurgu.py` otomatik merkezden kırpar; klip başına `"crop_x": 0.0–1.0` ile kırpma
  konumunu ayarla (ör. makine solda ise 0.3).
- Ses yoksa script sessiz ses kanalı ekler — birleştirme bozulmaz.
- Otomatik altyazı (konuşma→yazı) gerekiyorsa ve `faster-whisper` kurulabiliyorsa onu kullan; değilse
  seslendirme metnini kullanıcıdan al ve `captions` olarak zamanla.
- Türkçe karakterler için varsayılan font: Inter / DejaVu Sans (ikisi de ş,ğ,ı,İ destekler).
