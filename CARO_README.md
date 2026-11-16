# Caro Club 🌸 — Caro 15 × 15

Trò chơi Caro 2 người online trên iPhone/Android. Người tạo phòng chia sẻ mã 6 ký tự, cả hai bấm Sẵn sàng rồi lần lượt đặt quân X/O. Nối **tối thiểu 5 quân** trên cùng hàng, cột hoặc đường chéo thì thắng (không áp dụng luật chặn hai đầu). Hòa khi 225 ô đã kín mà không ai thắng.

## Triển khai Render
- Source repo: nhánh `caro-online`
- Language: Python
- Build command: `pip install -r caro_requirements.txt`
- Start command: `uvicorn caro_server:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`
- Free plan, Singapore.
- Chỉ dùng 1 instance vì phòng và trận đấu lưu trong RAM.

## Chạy trên Mac
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r caro_requirements.txt
uvicorn caro_server:app --reload
```
Sau đó mở http://localhost:8000.

## Chức năng
- Chơi thật giữa hai trình duyệt qua WebSocket, máy chủ kiểm soát lượt và xác định kết quả.
- Người vào phòng được quân O, chủ phòng quân X.
- Nút gửi lời mời cho đối thủ qua URL và mã phòng.
- Hiển thị lượt, ván, tỉ số thắng, quân cuối và hàng 5 quân chiến thắng.
- Có nút chơi lại; lượt đi trước đổi sau mỗi ván.
- Có thể reconnect trong cùng tab; trò chơi tự dừng nếu 1 người ngắt mạng.

## Lưu ý bản thử nghiệm
Dữ liệu chỉ nằm trong bộ nhớ server và có thể mất khi Render Free ngủ hoặc khởi động lại. Không sử dụng multi-instance hay lưu tiến độ lâu dài. Đây là phiên bản Gomoku 5-liên-tiếp dễ chơi, không áp dụng luật Caro chặn hai đầu. 
