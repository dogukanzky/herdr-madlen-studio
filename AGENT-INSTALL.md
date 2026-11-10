Aşağıdaki metni agentına yapıştır:

---

Herdr Desktop'ıma Madlen Studio temasını kurmanı istiyorum.

Kaynak: https://github.com/muratangin187/herdr-madlen-studio
Sürüm: v1.0.3

1. macOS, Python 3.9+, açık Herdr Desktop, PATH üzerinde herdr-app ve hc olup olmadığını kontrol et. Eksikse açıkça bildir; mevcut uygulamamı veya çalışan agentlarımı kapatma.
2. Repository'yi v1.0.3 etiketinden ayrı bir klasöre klonla. README.md, AGENTS.md ve install.py dosyalarını oku. Kimlik bilgilerini, sohbet kayıtlarını veya mevcut Herdr ayarlarımı başka yere yükleme.
3. Önce python3 install.py çalıştır. Başarılıysa herdr-app status ile madlen-studio'nun seçildiğini kontrol et. Aynı adlı kişisel dosya veya yerel değişiklik çakışması varsa dur; --replace-modified seçeneğini kendiliğinden kullanma.
4. Çıktılar uygulamasını da istiyorum: swiftc varsa python3 install.py --with-outputs çalıştır. Yoksa tema kurulumunu tamamla ve Çıktılar için Xcode Command Line Tools gerektiğini bildir; sistem kurulumunu kendiliğinden başlatma.
5. quota-axi yoksa bunu opsiyonel eksik olarak belirt; hesabımda oturum açmaya veya kimlik bilgileri taşımaya çalışma.
6. Temayı ekran görüntüsüyle kontrol et. Mevcut agentlarıma test mesajı gönderme. Önceki temaya dönüş komutunu ve eksik kalan opsiyonel bileşenleri yaz.
