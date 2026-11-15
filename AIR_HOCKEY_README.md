# 💗 Air Hockey Club — 2 người online

Game Air Hockey 2 người trên điện thoại, giao diện pastel. Bàn chơi 360×600, hai thanh gạt cảm ứng, bóng di chuyển theo vật lý trên máy chủ. Ai ghi **7 bàn** trước thắng.

## Chạy tại MacBook

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r hockey_requirements.txt
uvicorn hockey_server:app --reload
```

Mở `http://127.0.0.1:8000`.

## Deploy trên Render

- Runtime: Python
- Build command: `pip install -r hockey_requirements.txt`
- Start command: `uvicorn hockey_server:app --host 0.0.0.0 --port $PORT`
- Health: `/health`
- Cài 1 instance cho phòng chơi trong RAM. WebSocket sử dụng cùng máy chủ, không cần cấu hình CORS.
- Không cần khóa API, dữ liệu riêng chỉ lưu trong RAM, mã phòng 6 ký tự và token bí mật ngẫu nhiên trong sessionStorage.
- Chỉ dùng gói Free, tránh gói trả phí nếu chưa có sự chấp thuận.

## Lưu ý prototype
- Phòng chơi và điểm sẽ mất khi dịch vụ khởi động lại; người chơi kết nối lại trong cùng browser tab có thể tiếp tục khi server chưa restart.
- Mỗi trận chỉ 2 người; không có danh sách công khai hay chat.
- Tốc độ phụ thuộc độ trễ mạng; gói miễn phí Render có thể sleep khi không có truy cập.
- Quản lý vật lý bóng, xác thực điểm và điều kiện thắng hoàn toàn trên máy chủ.

## Cách chơi
1. Người A tạo phòng và sao chép link mời.
2. Người B mở link trên điện thoại khác, nhập tên và bấm tham gia.
3. Hai người bấm Sẵn sàng.
4. Điều khiển thanh gạt hồng bằng thao tác chạm kéo. Người chơi luôn nhìn từ phần dưới sân.
5. Ai ghi 7 bàn trước sẽ thắng. Cả hai có thể chọn Chơi lại.
