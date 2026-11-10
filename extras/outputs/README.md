# Herdr Çıktılar · 4.0

Codex veya Claude Code’un paylaştığı resim, Markdown, JSON, HTML, ZIP ve klasörleri tek pencerede bulup açmak için hazırlanmış kişisel Herdr eklentisi.

## Kurulum

**Gerekenler:** macOS 13 veya üzeri, açık ve çalışan Herdr Desktop (`herdr-app` ve `hc`), Python 3.9+ ve Xcode Command Line Tools (`swiftc`). Bu sürüm Linux ve Windows’ta çalışmaz.

1. ZIP’i bir klasöre çıkarın.
2. Terminal’de bu klasöre girip çalıştırın:

```sh
python3 install.py
```

Kurulum yardımcı uygulamayı kendi Mac’inizde kaynak kodundan derler. İndirme, Node.js veya API anahtarı gerektirmez. Mevcut Herdr düzeninizin kişisel bir kopyasına **Çıktılar** düğmesi ekler. Ajanlarınızı kapatmaz; var olan düzeninizi ve dağıtılan Herdr modlarını değiştirmez.

`swiftc` bulunamazsa önce `xcode-select --install` ile Xcode Command Line Tools’u kurun. `herdr-app` veya `hc` bulunamazsa Herdr Desktop kurulumunuzu tamamlayıp uygulamayı bir kez açın.

## Kullanım

Herdr’da istediğiniz yerel Codex veya Claude Code oturumunu seçip **Çıktılar** düğmesine basın. Son 50 kullanıcı/asistan mesajındaki mevcut dosyalar en yeni paylaşım üstte olacak şekilde listelenir. Tekrarlanan yollar bir kez gösterilir. Yeni yanıtlar için yenile düğmesi veya **Cmd+R** kullanılır.

- **Tek tık:** seçer. **Çift tık:** açar.
- **Görsel:** pencere içinde büyür; Cmd+tıklama Preview’da açar.
- **Markdown:** başlık, tablo, liste ve renkli kod bloklarıyla okunur. Kod blokları kopyalanabilir.
- **JSON:** renkli ağaçta alanlar açılıp kapatılır. Tümünü aç/kapat düğmeleri vardır. Büyük sayılar yuvarlanmadan gösterilir.
- **Markdown/JSON içinde Cmd+F:** belgeyi arar. Enter/Cmd+G sonraki, Shift+Enter/Cmd+Shift+G önceki eşleşmeye gider. JSON’da kapalı dallardaki sonuçlar da açılır.
- **HTML:** pencere içinde çalışır; Cmd+tıklama Chrome’da açar.
- **ZIP:** Finder’da seçilir. **Klasör:** Finder’da açılır.
- **Markdown/JSON’da Cmd+tıklama:** varsayılan dış uygulamada açar.
- **Çoklu seçim:** seçim daireleri, Shift+tıklama veya Cmd+A.
- **Cmd+C:** görselleri görsel olarak, diğer dosyaları yol metni olarak kopyalar.
- **Sürükleme:** seçilen gerçek dosyaları başka uygulamalara taşır. Birden fazla görseli yapıştırma ve dosya bırakma desteği hedef uygulamaya bağlıdır.
- **Grid/liste ve tür filtreleri:** üst çubuk ve sol taraftan değiştirilir.
- **Dosya araması:** dosya adı, yol ve konuşmada dosyanın geçtiği satırlarla komşu satırlarda arar. Bağlam metni görünmez.
- **Artı düğmesi / Cmd+V:** yerel dosya veya klasör ekler.

Belgeden dosyalara dönmek için geri okunu kullanın. Dosyaların asılları değiştirilmez.

İlk deneme için artı düğmesiyle paketteki `ornekler/Kullanim.md` ve `ornekler/Ornek.json` dosyalarını seçin. Markdown’da `kurulum`, JSON’da `gizli-deger` arayın; JSON’un kapalı dalları da açılmalıdır.

## Kapsam ve gizlilik

Bu kişisel bir araçtır; Herdr’ın resmi parçası değildir. Tam HTML ve dış uygulamalara sürükleme için Herdr’dan açılan ayrı bir macOS penceresi kullanır. Ajanın yerel konuşma kaydı salt okunur okunur; başka oturumların görselleri listeye katılmaz. Eşleşme kesin değilse başka bir konuşma seçilmez. Uzak makine oturumları desteklenmez.

Paket sohbet kaydı, hesap, anahtar veya kişisel çıktı içermez. Markdown ve JSON kütüphaneleri paket içindedir; belge içeriği bir sunucuya gönderilmez. Markdown’daki açıkça belirtilmiş HTTPS resimleri internetten yüklenebilir. Markdown içindeki çalıştırılabilir HTML temizlenir. Normal HTML dosyaları ise kullanıcı açtığında WebKit içinde JavaScript çalıştırabilir.

## Geri dönüş

Kurulum sonunda önceki düzene dönme komutu yazdırılır. Herdr düzen seçicisinden eski düzeni seçmek de yeterlidir. Kurulum bilgisi `~/.config/herdr-app/mods/outputs-browser/installation.json` içindedir. Güncelleme öncesi modun kopyası `~/.config/herdr-app/backups/outputs-browser/` altında saklanır.

## Doğrulananlar

macOS Apple Silicon üzerinde: konuşma ayrımı ve 50 mesaj sınırı, sıra ve bağlam araması, tek/çift/Cmd+tıklama, Markdown tablo/kod/temizleme, JSON aç/kapat ve sayı doğruluğu, belge içi arama ve kapalı JSON dalını bulma, görsel/yol panosu ve dosya URL aktarım verisi. Intel üzerinde kaynak derleme yolu sağlanır; Intel cihazda çalışma testi yapılmadı. Chrome/WhatsApp’a gerçek bırakma ve bu uygulamalarda yapıştırma uçtan uca test edilmedi.

## Kaynaklar ve lisanslar

Yerel yardımcı AppKit/WebKit kullanır. Markdown görünümü Marked ve DOMPurify; kod renklendirmesi highlight.js kullanır. Sürümler ve üçüncü taraf lisansları `mod/web/vendor/` içindedir. Kütüphaneler kurulurken internetten çekilmez.

Kaynak kod ve testler pakettedir. Kurulumdan sonra:

```sh
python3 -m unittest discover -s ~/.config/herdr-app/mods/outputs-browser -p 'test_*.py'
herdr-app check ~/.config/herdr-app/mods/outputs-browser
```
