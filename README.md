# AI Card Filler

**An Anki add-on that fills flashcards with AI: paste a word list, review the preview, add to Anki.**
**Add-on cho Anki giúp điền thẻ bằng AI: dán danh sách từ, xem trước, rồi thêm vào Anki.**

[English](#english) · [Tiếng Việt](#tiếng-việt) · [Changelog](CHANGELOG.md) · [License: MIT](LICENSE)

<!-- Add a screenshot here: docs/screenshot.png -->
<!-- ![AI Card Filler](docs/screenshot.png) -->

---

## English

AI Card Filler was built for language learners (originally Chinese vocabulary) who want to make many good cards quickly without typing every field by hand. You always see a preview first, so nothing reaches your collection until you approve it.

### Features
- **Create new cards**: paste one item per line (or a paragraph); the AI fills every field of your note type (meaning, pronunciation, example sentences...).
- **Fill existing cards**: select notes in the Browser, right-click, choose *AI Card Filler: fill empty fields…*. Only **empty** fields are written; existing content is never overwritten, and you can undo with Anki's Ctrl+Z.
- **Review before adding**: edit cells, remove rows, regenerate a single row with a short instruction; suspicious rows (empty, too long, duplicates) are highlighted.
- **Images**: search images for picture fields, or choose/paste your own.
- **Vocabulary from a photo**: take a photo of a book page and extract a word list (experimental).
- **Audio**: generate speech for Audio fields with Gemini TTS (experimental).
- **Several AI providers**: Gemini, any OpenAI-compatible service (OpenAI, OpenRouter, Ollama, LM Studio) and Claude. Optional automatic fallback when a provider hits its rate limit (HTTP 429).
- **Long lists**: processed in chunks (default 20) with progress; if one chunk fails, finished chunks are kept and you can resume.
- **Undo last add** button.
- **Presets**: ready-made configs for Chinese, Korean, English and Cloze note types; export/import your config.
- **No-API mode**: copy the prompt to ChatGPT/Gemini and paste the answer back.
- Vietnamese and English interface.

### Install
1. Download `ai_card_filler.ankiaddon` from the [Releases](../../releases) page.
2. Double-click it, or in Anki: *Tools → Add-ons → Install from file…*
3. Restart Anki. Open it from *Tools → AI Card Filler*.

Or install from source: run `./build.sh` and install the generated `.ankiaddon`.

### Set up an AI provider
Open the **Automatic (API)** tab, pick a provider and paste your API key. A free Gemini key from Google AI Studio is enough to start. Ollama / LM Studio running on your own computer need no key.

### Privacy
API keys are stored **only** in the add-on's config on your own computer and are sent **only** to the service you choose. Drafts saved by the add-on never contain keys, and exported configs do not include keys. The add-on has no telemetry.

### Compatibility
Tested with Anki 24.11, 25.2.7 and 25.9.2 (Python 3.13, Qt 6). Older versions are not tested.

### Known limitations
- Reading text from photos and Gemini text-to-speech are experimental; check the results.
- AI output can be wrong. Always review the preview.

### Development
```
src/            add-on source (package files at the root of the .ankiaddon)
build.sh        builds ai_card_filler.ankiaddon
```
Pull requests and issues are welcome.

### Contact
nguyenduchoi26112004@gmail.com

### License
[MIT](LICENSE)

---

## Tiếng Việt

AI Card Filler dành cho người học ngôn ngữ (ban đầu là từ vựng tiếng Trung) muốn tạo nhiều thẻ tốt nhanh chóng mà không phải gõ từng ô. Add-on luôn cho xem trước, nên không có gì vào bộ thẻ của bạn khi bạn chưa đồng ý.

### Tính năng
- **Tạo thẻ mới**: dán mỗi dòng một mục (hoặc một đoạn văn); AI điền tất cả các ô của loại ghi chú (nghĩa, phiên âm, câu ví dụ...).
- **Điền thẻ có sẵn**: chọn ghi chú trong Browser, chuột phải, chọn *AI Card Filler: điền ô trống…*. Chỉ ghi vào ô **trống**, không ghi đè nội dung đã có, và hoàn tác được bằng Ctrl+Z của Anki.
- **Xem trước rồi mới thêm**: sửa ô, bỏ dòng, tạo lại từng dòng kèm yêu cầu ngắn; dòng nghi sai (trống, quá dài, trùng) được tô màu.
- **Ảnh**: tìm ảnh cho ô hình, hoặc chọn/dán ảnh của bạn.
- **Lấy từ vựng từ ảnh**: chụp trang sách rồi lấy danh sách từ (thử nghiệm).
- **Âm thanh**: tạo giọng đọc cho ô Audio bằng Gemini TTS (thử nghiệm).
- **Nhiều dịch vụ AI**: Gemini, dịch vụ kiểu OpenAI (OpenAI, OpenRouter, Ollama, LM Studio) và Claude. Có thể tự đổi dịch vụ khi bị giới hạn (HTTP 429).
- **Danh sách dài**: chia lượt (mặc định 20 mục), có tiến trình; một lượt lỗi thì các lượt xong vẫn được giữ và chạy tiếp được.
- Nút **Hoàn tác lần thêm vừa rồi**.
- **Mẫu cấu hình** cho tiếng Trung, Hàn, Anh và Cloze; xuất/nhập cấu hình.
- **Chế độ không cần API**: sao chép prompt sang ChatGPT/Gemini rồi dán câu trả lời về.
- Giao diện tiếng Việt và tiếng Anh.

### Cài đặt
1. Tải `ai_card_filler.ankiaddon` ở trang [Releases](../../releases).
2. Bấm đúp vào file, hoặc trong Anki: *Tools → Add-ons → Install from file…*
3. Khởi động lại Anki. Mở từ *Tools → AI Card Filler*.

Hoặc cài từ mã nguồn: chạy `./build.sh` rồi cài file `.ankiaddon` vừa tạo.

### Cài dịch vụ AI
Vào tab **Tự động (API)**, chọn dịch vụ và dán khóa API. Khóa Gemini miễn phí từ Google AI Studio là đủ để bắt đầu. Ollama / LM Studio chạy trên máy bạn không cần khóa.

### Quyền riêng tư
Khóa API chỉ được lưu trong cấu hình add-on **trên máy của bạn** và chỉ được gửi tới đúng dịch vụ bạn chọn. Bản nháp add-on lưu không chứa khóa, file cấu hình xuất ra cũng không có khóa. Add-on không thu thập dữ liệu.

### Tương thích
Đã thử trên Anki 24.11, 25.2.7 và 25.9.2 (Python 3.13, Qt 6). Các bản cũ hơn chưa được kiểm tra.

### Hạn chế đã biết
- Đọc chữ từ ảnh và giọng đọc Gemini còn thử nghiệm; hãy kiểm tra kết quả.
- AI có thể sai. Luôn xem lại bản xem trước.

### Liên hệ
nguyenduchoi26112004@gmail.com

### Giấy phép
[MIT](LICENSE)
