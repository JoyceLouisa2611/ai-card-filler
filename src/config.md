**AI Card Filler** lưu cấu hình ở đây.

- `gemini_key`: khóa Gemini API của bạn (chỉ cần cho chế độ Tự động). Khóa lưu trên máy bạn, add-on không gửi đi đâu ngoài Google.
- `gemini_model`: model Gemini dùng khi gọi tự động.
- `image_max_side`: cạnh dài nhất của ảnh sau khi thu nhỏ (pixel).
- `tag`: nhãn mặc định gắn cho thẻ mới.
- `extra`: yêu cầu thêm chèn vào prompt (ví dụ trình độ, ngành).
- `types`: cấu hình theo từng loại ghi chú (vai trò ô, mô tả ô, lời mở đầu prompt). Chỉnh trong cửa sổ "Cấu hình ô và prompt" thay vì sửa tay.
- `open_on_add`: true thì bấm nút Add của Anki sẽ mở AI Card Filler (có nút "Add thường" để quay lại cửa sổ gốc).
- `ui`: kích thước cửa sổ, phương thức tạo và loại ghi chú dùng gần nhất; được lưu tự động khi đóng cửa sổ.
- `animations`: bật mascot và GIF trong khung xem trước; cũng tuân theo Reduce Motion của Anki.
- `auto_save_draft`: tự lưu bản nháp vào `user_files/drafts`, tách riêng theo hồ sơ Anki. Không lưu khóa API vào bản nháp.

Ngôn ngữ theo Anki: hỗ trợ tiếng Việt và English; ngôn ngữ khác dùng English.
Màu nền lấy từ palette và theme hiện tại của Anki, cập nhật khi đổi theme.
- `appearance`: chỉnh bằng nút **Màu sắc / Colors**. `mode` là `anki` hoặc `custom`;
  `source` là `auto`, `background` hoặc `accent`; `accent`, `light_bg`, `dark_bg`
  là mã `#RRGGBB`; `decorations` bật/tắt hoa, dấu chân và thẻ minh họa.
GIF chọn từ máy được giữ nguyên chuyển động và định dạng khi thêm vào thẻ; ảnh tĩnh vẫn được thu nhỏ.
Chọn hoặc tải danh sách model tại tab Gemini API. Add-on dùng đúng model được chọn.

## Từ phiên bản 1.8.10
- `provider`: dịch vụ AI đang dùng: `gemini`, `openai` (OpenAI, OpenRouter, Ollama/LM Studio trên máy bạn, hoặc dịch vụ nào có API kiểu OpenAI) hoặc `anthropic` (Claude). Chọn trong tab **Tự động (API)**.
- `openai`: `base_url`, `key`, `model` cho dịch vụ kiểu OpenAI. Ollama/LM Studio chạy trên máy bạn không cần `key`.
- `anthropic`: `key` và `model` của Claude.
- `auto_fallback`: khi dịch vụ đang chọn báo hết hạn mức (429), tự thử dịch vụ khác đã điền đủ thông tin.
- `chunk_size`: số mục mỗi lượt khi tạo bằng API (mặc định 20). Danh sách dài được chia lượt; nếu một lượt lỗi, các lượt xong vẫn được giữ và bấm lại sẽ chạy tiếp phần còn thiếu.
- `tts_model`, `tts_voice`: model và giọng đọc Gemini dùng cho ô âm thanh (tính năng thử nghiệm, cần khóa Gemini).
- `fill_tag`: nhãn gắn thêm khi điền ô trống cho thẻ có sẵn từ Browser.

### Quyền riêng tư
Mọi khóa API chỉ lưu trong cấu hình trên máy của bạn và chỉ được gửi tới đúng dịch vụ bạn chọn. Bản nháp tự lưu (`user_files/drafts`) không chứa khóa API. File xuất cấu hình loại thẻ không chứa khóa.

### Lịch sử thay đổi
- **1.8.10**: khung ảnh to hơn và kéo được; bỏ nhiều dòng (Delete, Ctrl/Shift), sửa cả dòng, tạo lại từng dòng bằng AI, tô màu dòng nghi sai; điền ô trống cho thẻ có sẵn từ Browser; chia lượt cho danh sách dài; hoàn tác lần thêm vừa rồi; lấy danh sách từ từ ảnh; nhiều dịch vụ AI (OpenAI/OpenRouter/Ollama, Claude) và tự đổi khi hết hạn mức; ô âm thanh bằng giọng Gemini (thử nghiệm); mẫu cấu hình cho tiếng Trung/Hàn/Anh/Cloze, xuất và nhập cấu hình.
