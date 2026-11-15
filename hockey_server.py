"""Air Hockey Duo — server-authoritative two-player game."""
import asyncio
import contextlib
import math
import random
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

WIDTH, HEIGHT = 360.0, 600.0
PUCK_RADIUS, PADDLE_RADIUS = 11.0, 27.0
LEFT, RIGHT = 13.0, WIDTH - 13.0
GOAL_LEFT, GOAL_RIGHT = 112.0, 248.0
WIN_SCORE = 7
PLAYER_SPEED = 1650.0
PUCK_START_SPEED = 295.0
PUCK_MAX_SPEED = 810.0
ROOMS = {}
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class NameInput(BaseModel):
    name: str = "Người chơi"


class JoinInput(BaseModel):
    code: str
    name: str = "Người chơi"


def pretty_name(name: str) -> str:
    return (name.strip()[:22] or "Người chơi")


def error(message: str, status: int = 400):
    raise HTTPException(status_code=status, detail=message)


class Room:
    def __init__(self, name):
        self.code = "".join(secrets.choice(ALPHABET) for _ in range(6))
        self.names = [pretty_name(name), None]
        self.tokens = [secrets.token_urlsafe(32), None]
        self.clients = [None, None]
        self.ready = [False, False]
        self.rematch = [False, False]
        self.phase = "lobby"
        self.score = [0, 0]
        self.winner = None
        self.paddles = [[180.0, 512.0], [180.0, 88.0]]
        self.targets = [[180.0, 512.0], [180.0, 88.0]]
        self.paddle_vel = [[0.0, 0.0], [0.0, 0.0]]
        self.puck = [180.0, 300.0]
        self.velocity = [0.0, 0.0]
        self.freeze_until = 0.0
        self.last_active = time.monotonic()
        self.last_emit = 0.0

    def seat(self, token):
        for i, t in enumerate(self.tokens):
            if token and t and secrets.compare_digest(token, t):
                return i
        return None

    def connected(self):
        return [c is not None for c in self.clients]

    def start(self):
        self.phase = "playing"
        self.score = [0, 0]
        self.winner = None
        self.ready = [False, False]
        self.rematch = [False, False]
        self.paddles = [[180.0, 512.0], [180.0, 88.0]]
        self.targets = [[180.0, 512.0], [180.0, 88.0]]
        self.reset_puck(random.choice((-1, 1)), 1.5)

    def reset_puck(self, direction, pause=1.0):
        self.puck = [WIDTH / 2, HEIGHT / 2]
        a = random.uniform(-0.57, 0.57)
        self.velocity = [PUCK_START_SPEED * math.sin(a), direction * PUCK_START_SPEED * math.cos(a)]
        self.freeze_until = time.monotonic() + pause


def get_room(code):
    room = ROOMS.get(code.strip().upper())
    if not room:
        error("Không tìm thấy phòng. Hãy kiểm tra mã mời.")
    return room


def clamp(value, low, high):
    return max(low, min(high, value))


def paddle_bounds(seat):
    if seat == 0:
        return PADDLE_RADIUS + 13, WIDTH - PADDLE_RADIUS - 13, HEIGHT / 2 + PADDLE_RADIUS + 9, HEIGHT - PADDLE_RADIUS - 20
    return PADDLE_RADIUS + 13, WIDTH - PADDLE_RADIUS - 13, PADDLE_RADIUS + 20, HEIGHT / 2 - PADDLE_RADIUS - 9


def set_target(room, seat, x, y):
    if not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
        return
    if not (math.isfinite(x) and math.isfinite(y)):
        return
    xmin, xmax, ymin, ymax = paddle_bounds(seat)
    room.targets[seat] = [clamp(x, xmin, xmax), clamp(y, ymin, ymax)]


def simulation_step(room, dt, now):
    if room.phase != "playing" or not all(room.connected()):
        return
    dt = min(dt, 0.05)
    for i in range(2):
        old_x, old_y = room.paddles[i]
        tx, ty = room.targets[i]
        dx, dy = tx - old_x, ty - old_y
        dist = math.hypot(dx, dy)
        travel = min(dist, PLAYER_SPEED * dt)
        if dist > 1e-6:
            old_x += dx / dist * travel
            old_y += dy / dist * travel
        room.paddles[i] = [old_x, old_y]
        room.paddle_vel[i] = [(old_x - (old_x - dx / dist * travel if dist > 1e-6 else old_x)) / dt if dt else 0,
                              (old_y - (old_y - dy / dist * travel if dist > 1e-6 else old_y)) / dt if dt else 0]

    if now < room.freeze_until:
        return

    px, py = room.puck
    vx, vy = room.velocity
    px += vx * dt
    py += vy * dt

    for seat in range(2):
        ax, ay = room.paddles[seat]
        dx, dy = px - ax, py - ay
        distance = math.hypot(dx, dy)
        reach = PUCK_RADIUS + PADDLE_RADIUS
        if distance < reach:
            if distance < 0.001:
                nx, ny = 0, -1 if seat == 0 else 1
            else:
                nx, ny = dx / distance, dy / distance
            px, py = ax + nx * (reach + 0.4), ay + ny * (reach + 0.4)
            # Only bounce if approaching the paddle (relative to its movement).
            avx, avy = room.paddle_vel[seat]
            rel_dot = (vx - avx) * nx + (vy - avy) * ny
            if rel_dot < 0:
                incoming_speed = math.hypot(vx, vy)
                speed = clamp(max(340, incoming_speed * 1.035), 340, PUCK_MAX_SPEED)
                vx = nx * speed + avx * 0.13
                vy = ny * speed + avy * 0.13
                vmag = math.hypot(vx, vy)
                if vmag > PUCK_MAX_SPEED:
                    vx *= PUCK_MAX_SPEED / vmag
                    vy *= PUCK_MAX_SPEED / vmag

    if px < LEFT + PUCK_RADIUS:
        px = LEFT + PUCK_RADIUS
        vx = abs(vx)
    if px > RIGHT - PUCK_RADIUS:
        px = RIGHT - PUCK_RADIUS
        vx = -abs(vx)

    for upper, crossed in ((True, py < 13 + PUCK_RADIUS), (False, py > HEIGHT - 13 - PUCK_RADIUS)):
        if not crossed:
            continue
        if GOAL_LEFT <= px <= GOAL_RIGHT:
            scorer = 0 if upper else 1
            room.score[scorer] += 1
            if room.score[scorer] >= WIN_SCORE:
                room.phase = "finished"
                room.winner = scorer
                room.velocity = [0.0, 0.0]
                room.puck = [px, py]
            else:
                room.reset_puck(1 if upper else -1, 1.15)
            return
        py = 13 + PUCK_RADIUS if upper else HEIGHT - 13 - PUCK_RADIUS
        vy = abs(vy) if upper else -abs(vy)

    room.puck = [px, py]
    room.velocity = [vx, vy]


def public_state(room, seat):
    now = time.monotonic()
    return {
        "type": "state",
        "code": room.code,
        "side": seat,
        "names": room.names,
        "connected": room.connected(),
        "ready": room.ready,
        "rematch": room.rematch,
        "phase": room.phase,
        "winner": room.winner,
        "score": room.score,
        "puck": [round(v, 2) for v in room.puck],
        "paddles": [[round(v, 2) for v in p] for p in room.paddles],
        "countdown": round(max(0, room.freeze_until - now), 2) if room.phase == "playing" else 0,
        "playing": room.phase == "playing" and all(room.connected()),
    }


async def broadcast(room):
    for seat, ws in enumerate(room.clients):
        if ws:
            try:
                await ws.send_json(public_state(room, seat))
            except Exception:
                if room.clients[seat] is ws:
                    room.clients[seat] = None


async def game_loop():
    last = time.monotonic()
    last_cleanup = last
    while True:
        await asyncio.sleep(1 / 60)
        now = time.monotonic()
        dt = now - last
        last = now
        for room in list(ROOMS.values()):
            simulation_step(room, dt, now)
            if now - room.last_emit >= 0.05:
                await broadcast(room)
                room.last_emit = now
        if now - last_cleanup > 60:
            for code, room in list(ROOMS.items()):
                if not any(room.connected()) and now - room.last_active > 3600:
                    ROOMS.pop(code, None)
            last_cleanup = now


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(game_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"ok": True, "game": "air-hockey-duo", "rooms": len(ROOMS), "winning_score": WIN_SCORE}


@app.get("/")
async def index():
    return HTMLResponse(Path(__file__).with_name("air_hockey.html").read_text(encoding="utf-8"))


@app.post("/api/create")
async def create(data: NameInput):
    if len(ROOMS) >= 500:
        error("Máy chủ đang có quá nhiều phòng. Vui lòng thử lại.")
    room = Room(data.name)
    while room.code in ROOMS:
        room.code = "".join(secrets.choice(ALPHABET) for _ in range(6))
    ROOMS[room.code] = room
    return {"code": room.code, "token": room.tokens[0], "side": 0}


@app.post("/api/join")
async def join(data: JoinInput):
    room = get_room(data.code)
    if room.names[1] is not None:
        error("Phòng đã đủ hai người.")
    if room.phase != "lobby":
        error("Trận đấu đã bắt đầu.")
    room.names[1] = pretty_name(data.name)
    room.tokens[1] = secrets.token_urlsafe(32)
    room.last_active = time.monotonic()
    await broadcast(room)
    return {"code": room.code, "token": room.tokens[1], "side": 1}


@app.websocket("/ws/{code}")
async def websocket_game(ws: WebSocket, code: str):
    room = ROOMS.get(code.strip().upper())
    token = ws.query_params.get("token")
    seat = room.seat(token) if room else None
    if seat is None:
        await ws.close(code=1008)
        return
    await ws.accept()
    former = room.clients[seat]
    room.clients[seat] = ws
    room.last_active = time.monotonic()
    if former:
        with contextlib.suppress(Exception):
            await former.close(code=4000)
    await broadcast(room)
    try:
        while True:
            msg = await ws.receive_json()
            if ws is not room.clients[seat]:
                break
            room.last_active = time.monotonic()
            cmd = msg.get("type")
            if cmd == "move" and room.phase == "playing":
                set_target(room, seat, msg.get("x"), msg.get("y"))
            elif cmd == "ready" and room.phase == "lobby":
                room.ready[seat] = True
                if all(room.ready) and all(room.connected()) and all(room.names):
                    room.start()
                await broadcast(room)
            elif cmd == "rematch" and room.phase == "finished":
                room.rematch[seat] = True
                if all(room.rematch) and all(room.connected()):
                    room.start()
                await broadcast(room)
            elif cmd == "ping":
                await ws.send_json({"type": "pong"})
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        if room.clients[seat] is ws:
            room.clients[seat] = None
            room.last_active = time.monotonic()
            await broadcast(room)
