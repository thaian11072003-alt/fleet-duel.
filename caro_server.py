"""Caro Club: server-authoritative 15x15 online Gomoku for two players."""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pathlib import Path
from pydantic import BaseModel

SIZE = 15
CELLS = SIZE * SIZE
WIN_LENGTH = 5
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ROOMS: dict[str, "Room"] = {}
app = FastAPI()


class PlayerName(BaseModel):
    name: str = "Người chơi"


class JoinRequest(PlayerName):
    code: str


def safe_name(name: str) -> str:
    return (name.strip()[:24] or "Người chơi")


def find_room(code: str) -> "Room":
    room = ROOMS.get(code.strip().upper())
    if not room:
        raise HTTPException(404, "Phòng không tồn tại hoặc đã hết hạn")
    return room


def winning_line(board: list[int], index: int, marker: int) -> list[int]:
    """Return all cells in a connected 5+ line through index, else []."""
    row, col = divmod(index, SIZE)
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        line = [index]
        for sign in (-1, 1):
            r, c = row + sign * dy, col + sign * dx
            while 0 <= r < SIZE and 0 <= c < SIZE and board[r * SIZE + c] == marker:
                line.append(r * SIZE + c)
                r += sign * dy
                c += sign * dx
        if len(line) >= WIN_LENGTH:
            return sorted(line)
    return []


@dataclass
class Room:
    code: str
    names: list[Optional[str]]
    tokens: list[Optional[str]]
    connections: list[Optional[WebSocket]] = field(default_factory=lambda: [None, None])
    ready: list[bool] = field(default_factory=lambda: [False, False])
    rematch: list[bool] = field(default_factory=lambda: [False, False])
    board: list[int] = field(default_factory=lambda: [0] * CELLS)
    scores: list[int] = field(default_factory=lambda: [0, 0])
    phase: str = "lobby"
    turn: int = 0
    starter: int = 0
    winner: Optional[int] = None
    draw: bool = False
    win_line: list[int] = field(default_factory=list)
    last_move: Optional[int] = None
    round: int = 1
    updated: float = field(default_factory=time.monotonic)

    def seat_for(self, token: Optional[str]) -> Optional[int]:
        if not token:
            return None
        for i, candidate in enumerate(self.tokens):
            if candidate and secrets.compare_digest(candidate, token):
                return i
        return None

    def start_round(self) -> None:
        self.board = [0] * CELLS
        self.phase = "playing"
        self.turn = self.starter
        self.ready = [False, False]
        self.rematch = [False, False]
        self.winner = None
        self.draw = False
        self.win_line = []
        self.last_move = None
        self.updated = time.monotonic()

    def public(self, for_seat: int) -> dict:
        return {
            "type": "state",
            "code": self.code,
            "side": for_seat,
            "names": self.names,
            "connected": [ws is not None for ws in self.connections],
            "ready": self.ready,
            "rematch": self.rematch,
            "board": self.board,
            "phase": self.phase,
            "turn": self.turn,
            "starter": self.starter,
            "winner": self.winner,
            "draw": self.draw,
            "winLine": self.win_line,
            "lastMove": self.last_move,
            "scores": self.scores,
            "round": self.round,
            "moves": CELLS - self.board.count(0),
        }

    def place(self, seat: int, index: int) -> str | None:
        if self.phase != "playing":
            return "Trận đấu chưa bắt đầu"
        if not all(ws is not None for ws in self.connections):
            return "Đang chờ đối thủ kết nối lại"
        if seat != self.turn:
            return "Chưa đến lượt của bạn"
        if type(index) is not int or not (0 <= index < CELLS):
            return "Ô không hợp lệ"
        if self.board[index] != 0:
            return "Ô này đã có quân"
        self.board[index] = seat + 1
        self.last_move = index
        line = winning_line(self.board, index, seat + 1)
        if line:
            self.phase = "finished"
            self.winner = seat
            self.win_line = line
            self.scores[seat] += 1
        elif 0 not in self.board:
            self.phase = "finished"
            self.draw = True
        else:
            self.turn = 1 - seat
        self.updated = time.monotonic()
        return None


async def broadcast(room: Room) -> None:
    for seat, ws in enumerate(room.connections):
        if ws:
            try:
                await ws.send_json(room.public(seat))
            except Exception:
                if room.connections[seat] is ws:
                    room.connections[seat] = None


@app.get("/")
async def home() -> HTMLResponse:
    return HTMLResponse(Path(__file__).with_name("caro.html").read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "game": "caro-online", "board": "15x15", "winning_length": 5}


@app.post("/api/create")
async def create(data: PlayerName) -> dict:
    # Discard idle rooms without connected players.
    now = time.monotonic()
    for key, room in list(ROOMS.items()):
        if now - room.updated > 3600 and not any(room.connections):
            ROOMS.pop(key, None)
    if len(ROOMS) >= 300:
        raise HTTPException(503, "Máy chủ đang đầy. Vui lòng thử lại sau.")
    code = "".join(secrets.choice(ALPHABET) for _ in range(6))
    while code in ROOMS:
        code = "".join(secrets.choice(ALPHABET) for _ in range(6))
    token = secrets.token_urlsafe(32)
    ROOMS[code] = Room(code=code, names=[safe_name(data.name), None], tokens=[token, None])
    return {"code": code, "token": token, "side": 0}


@app.post("/api/join")
async def join(data: JoinRequest) -> dict:
    room = find_room(data.code)
    if room.names[1] is not None:
        raise HTTPException(400, "Phòng đã đủ 2 người")
    if room.phase != "lobby":
        raise HTTPException(400, "Trận đấu đã bắt đầu")
    token = secrets.token_urlsafe(32)
    room.names[1] = safe_name(data.name)
    room.tokens[1] = token
    room.updated = time.monotonic()
    await broadcast(room)
    return {"code": room.code, "token": token, "side": 1}


@app.websocket("/ws/{code}")
async def connect(ws: WebSocket, code: str) -> None:
    room = ROOMS.get(code.strip().upper())
    token = ws.query_params.get("token")
    seat = room.seat_for(token) if room else None
    if seat is None:
        await ws.close(code=1008)
        return
    await ws.accept()
    previous = room.connections[seat]
    room.connections[seat] = ws
    room.updated = time.monotonic()
    if previous:
        try:
            await previous.close(code=4000)
        except Exception:
            pass
    await broadcast(room)
    try:
        while True:
            msg = await ws.receive_json()
            if room.connections[seat] is not ws:
                break
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")
            room.updated = time.monotonic()
            if kind == "ready" and room.phase == "lobby":
                room.ready[seat] = True
                if all(room.ready) and all(room.names) and all(room.connections):
                    room.start_round()
                await broadcast(room)
            elif kind == "move":
                reason = room.place(seat, msg.get("index"))
                if reason:
                    await ws.send_json({"type": "error", "message": reason})
                else:
                    await broadcast(room)
            elif kind == "rematch" and room.phase == "finished":
                room.rematch[seat] = True
                if all(room.rematch) and all(room.connections):
                    room.round += 1
                    room.starter = 1 - room.starter
                    room.start_round()
                await broadcast(room)
            elif kind == "ping":
                await ws.send_json({"type": "pong"})
    except (WebSocketDisconnect, ValueError, RuntimeError):
        pass
    finally:
        if room.connections[seat] is ws:
            room.connections[seat] = None
            room.updated = time.monotonic()
            await broadcast(room)
