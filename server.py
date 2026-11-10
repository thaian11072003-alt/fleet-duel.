import os, secrets, time
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path

app=FastAPI()
rooms={}
SIZES=[1,1,3,4]
def fail(msg): raise HTTPException(400,msg)
def room(code):
    r=rooms.get(code)
    if not r: fail("Không tìm thấy phòng")
    return r
def player(r,token):
    for i,p in enumerate(r["players"]):
        if p and p["token"]==token: return i
    fail("Bạn không thuộc phòng này")
def occupied(ships):
    o={}
    for n,s in enumerate(ships):
        a=s["start"]; d=s["axis"]; size=SIZES[n]
        if type(a)!=int or not(0<=a<100) or d not in ("h","v"): fail("Vị trí tàu không hợp lệ")
        if d=="h" and a%10+size>10: fail("Tàu vượt ngoài bảng")
        if d=="v" and a//10+size>10: fail("Tàu vượt ngoài bảng")
        for k in range(size):
            c=a+(k if d=="h" else 10*k)
            if c in o: fail("Tàu bị chồng lên nhau")
            o[c]=n
    return o
class Name(BaseModel): name:str
class Join(BaseModel):code:str;name:str
class Secret(BaseModel):code:str;token:str
class Place(Secret): ships:list[dict]
class Fire(Secret):cell:int
@app.get("/health")
def health():return {"ok":True}
@app.get("/")
def home():return HTMLResponse(Path(__file__).with_name("index.html").read_text())
@app.post("/api/create")
def create(a:Name):
    for c in list(rooms):
        if time.time()-rooms[c]["updated"]>21600: del rooms[c]
    if len(rooms)>=300: fail("Máy chủ đang đầy")
    code=''.join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
    token=secrets.token_urlsafe(24)
    rooms[code]={"players":[{"name":a.name[:24] or "Player 1","token":token,"ships":[],"ready":False},None],"shots":[[],[]],"turn":0,"winner":None,"phase":"lobby","updated":time.time()}
    return {"code":code,"token":token}
@app.post("/api/join")
def join(a:Join):
    r=room(a.code.upper())
    if r["players"][1]: fail("Phòng đã đủ hai người")
    if r["phase"]!="lobby": fail("Trận đã bắt đầu")
    token=secrets.token_urlsafe(24)
    r["players"][1]={"name":a.name[:24] or "Player 2","token":token,"ships":[],"ready":False}
    r["updated"]=time.time()
    return {"code":a.code.upper(),"token":token}
@app.post("/api/state")
def state(a:Secret):
    r=room(a.code.upper());i=player(r,a.token);me=r["players"][i];opp=r["players"][1-i]
    fired=set(r["shots"][i]);oppshots=set(r["shots"][1-i])
    own=occupied(me["ships"]) if me["ships"] else {}
    targets=occupied(opp["ships"]) if opp and opp["ships"] else {}
    return {"code":a.code.upper(),"you":i,"phase":r["phase"],"turn":r["turn"],"winner":r["winner"],"players":[{"name":p["name"],"ready":p["ready"]} if p else None for p in r["players"]],"ships":me["ships"],"yourHits":[c for c in oppshots if c in own],"yourMisses":[c for c in oppshots if c not in own],"hits":[c for c in fired if c in targets],"misses":[c for c in fired if c not in targets],"shotCount":len(fired),"enemyRemaining":9-len([c for c in fired if c in targets])}
@app.post("/api/place")
def place(a:Place):
    r=room(a.code.upper());i=player(r,a.token)
    if r["phase"]!="lobby":fail("Không thể đặt tàu lúc này")
    if r["players"][i]["ready"]:fail("Bạn đã sẵn sàng")
    if len(a.ships)!=4:fail("Cần đặt đủ bốn tàu")
    occupied(a.ships)
    r["players"][i]["ships"]=a.ships
    r["players"][i]["ready"]=True
    r["updated"]=time.time()
    if all(p and p["ready"] for p in r["players"]):r["phase"]="playing"
    return {"ok":True}
@app.post("/api/fire")
def fire(a:Fire):
    r=room(a.code.upper());i=player(r,a.token)
    if r["phase"]!="playing":fail("Trận chưa bắt đầu hoặc đã kết thúc")
    if r["turn"]!=i:fail("Chưa đến lượt bạn")
    if type(a.cell)!=int or not 0<=a.cell<100:fail("Ô không hợp lệ")
    if a.cell in r["shots"][i]:fail("Ô này đã bắn")
    r["shots"][i].append(a.cell)
    hit=a.cell in occupied(r["players"][1-i]["ships"])
    if hit and len([c for c in r["shots"][i] if c in occupied(r["players"][1-i]["ships"])])==9:
        r["winner"]=i;r["phase"]="ended"
    elif not hit:r["turn"]=1-i
    r["updated"]=time.time()
    return {"hit":hit,"won":r["winner"]==i}
