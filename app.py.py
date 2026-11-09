import json
import random
from typing import Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI(title="Kahoot Science Meme Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# إدارة الغرف والطلاب المتصلين أونلاين (PIN)
# ==========================================
class ConnectionManager:

  def __init__(self):
    self.rooms: Dict[str, Dict] = {}

  async def connect_host(self, websocket: WebSocket, pin: str):
    await websocket.accept()
    if pin not in self.rooms:
      self.rooms[pin] = {"host": websocket, "players": {}}
    else:
      self.rooms[pin]["host"] = websocket

  async def connect_player(
      self, websocket: WebSocket, pin: str, player_name: str
  ):
    await websocket.accept()
    if pin in self.rooms:
      self.rooms[pin]["players"][player_name] = websocket
      # إبلاغ المعلم بانضمام طالب جديد
      host_ws = self.rooms[pin]["host"]
      if host_ws:
        await host_ws.send_json({
            "type": "player_joined",
            "name": player_name,
            "count": len(self.rooms[pin]["players"]),
        })

  def disconnect(self, pin: str, player_name: str = None, is_host: bool = False):
    if pin in self.rooms:
      if is_host:
        del self.rooms[pin]
      elif player_name and player_name in self.rooms[pin]["players"]:
        del self.rooms[pin]["players"][player_name]

  async def broadcast_to_room(self, pin: str, message: dict):
    if pin in self.rooms:
      # إرسال لكافة اللاعبين والمعلم
      for player_ws in self.rooms[pin]["players"].values():
        try:
          await player_ws.send_json(message)
        except Exception:
          pass
      if self.rooms[pin]["host"]:
        try:
          await self.rooms[pin]["host"].send_json(message)
        except Exception:
          pass


manager = ConnectionManager()


@app.websocket("/ws/{pin}/{role}/{name}")
async def websocket_endpoint(
    websocket: WebSocket, pin: str, role: str, name: str
):
  if role == "host":
    await manager.connect_host(websocket, pin)
    try:
      while True:
        data = await websocket.receive_json()
        await manager.broadcast_to_room(pin, data)
    except WebSocketDisconnect:
      manager.disconnect(pin, is_host=True)
  else:
    await manager.connect_player(websocket, pin, name)
    try:
      while True:
        data = await websocket.receive_json()
        # إرسال إجابة الطالب للمعلم
        host_ws = manager.rooms.get(pin, {}).get("host")
        if host_ws:
          await host_ws.send_json(
              {"type": "student_answer", "player": name, "answer": data}
          )
    except WebSocketDisconnect:
      manager.disconnect(pin, player_name=name)


# ==========================================
# واجهة الويب المتكاملة (HTML + JS + Memes)
# ==========================================
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>كاهوت أونلاين - السنورة المصفقة والميمز</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap');
        * { box-sizing: border-box; font-family: 'Cairo', sans-serif; }
        body { margin: 0; padding: 0; background: #111827; color: #fff; text-align: center; }
        .container { max-width: 800px; margin: 30px auto; padding: 20px; background: #1e293b; border-radius: 20px; border: 2px solid #22c55e; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h1 { color: #22c55e; font-size: 32px; margin-bottom: 10px; }
        .btn { background: #22c55e; color: #000; font-weight: bold; font-size: 18px; border: none; padding: 12px 25px; border-radius: 12px; cursor: pointer; transition: 0.2s; margin: 8px; width: 80%; }
        .btn:hover { background: #4ade80; transform: scale(1.02); }
        input[type="text"] { width: 80%; padding: 12px; margin: 8px; border-radius: 10px; border: 2px solid #22c55e; background: #0f172a; color: #fff; font-size: 18px; text-align: center; }
        .screen { display: none; }
        .active { display: block; }
        .pin-display { font-size: 48px; font-weight: 900; color: #facc15; background: #0f172a; padding: 15px; border-radius: 15px; letter-spacing: 5px; margin: 15px 0; }
        .options-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 20px; }
        .opt-btn { font-size: 20px; font-weight: bold; padding: 25px; border-radius: 15px; border: none; color: #fff; cursor: pointer; transition: 0.2s; }
        .opt-0 { background: #e11d48; } .opt-1 { background: #2563eb; }
        .opt-2 { background: #d97706; } .opt-3 { background: #16a34a; }
        .opt-btn:hover { opacity: 0.9; transform: translateY(-3px); }
        .modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); display: none; align-items: center; justify-content: center; z-index: 100; }
        .modal-content { background: #0f172a; border: 4px solid #22c55e; padding: 15px; border-radius: 20px; max-width: 450px; width: 90%; }
        .modal-content img { width: 100%; max-height: 350px; border-radius: 12px; object-fit: cover; }
    </style>
</head>
<body>

<!-- نافذة الميم العشوائي عند الإجابة الصحيحة -->
<div id="memeModal" class="modal">
    <div class="modal-content">
        <img id="memeImg" src="" alt="Cat Meme">
    </div>
</div>

<div class="container">
    <h1>🐱👏 كاهوت العلوم أونلاين 🌿</h1>
    <p style="color: #86efac;">طوّر مهاراتك مع السنورة المصفقة وأثر الميمز!</p>

    <!-- شاشة الاختيار الرئيسية -->
    <div id="homeScreen" class="screen active">
        <button class="btn" onclick="setupHost()">🎓 فتح اللعبة كـ معلم (Host)</button> <br>
        <button class="btn" onclick="showPlayerJoin()">🎮 دخول كـ متسابق (Player)</button>
    </div>

    <!-- شاشة إعداد المعلم والـ PIN -->
    <div id="hostLobby" class="screen">
        <h2>رمز PIN الخاص باللعبة:</h2>
        <div id="pinBox" class="pin-display">------</div>
        <p>انتظار المتسابقين للانضمام أونلاين...</p>
        <div id="playerList" style="margin: 15px; font-size: 18px; color: #4ade80;"></div>
        <button class="btn" onclick="startHostGame()">ابدأ المسابقة الآن 🚀</button>
    </div>

    <!-- شاشة دخول المتسابق -->
    <div id="playerJoin" class="screen">
        <h2>أدخل رمز الـ PIN واسمك:</h2>
        <input type="text" id="pinInput" placeholder="رمز الـ PIN (مثال: 123456)"> <br>
        <input type="text" id="nameInput" placeholder="اسم المتسابق"> <br>
        <button class="btn" onclick="joinGame()">دخول المسابقة 🎯</button>
    </div>

    <!-- شاشة الأسئلة واللعب -->
    <div id="gameScreen" class="screen">
        <h2 id="questionTitle" style="color: #86efac;">السؤال يظهر هنا...</h2>
        <div class="options-grid" id="optionsContainer"></div>
    </div>

    <!-- شاشة الانتهاء والنتائج -->
    <div id="resultScreen" class="screen">
        <h2 style="color: #facc15;">🏆 انتهت المسابقة! 🏆</h2>
        <div id="finalScore" style="font-size: 24px; margin: 20px;"></div>
        <button class="btn" onclick="location.reload()">العودة للرئيسية 🔄</button>
    </div>
</div>

<script>
    // مكتبة الميمات العشوائية للسنورة المصفقة والميمز المضحكة
    const memes = [
        "https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExOHpqd2I0dHR5aWw3NnMzYnN3dzc0aWp3cnk2M3U3bGR0OWc0NnY1ZyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/3oKIPnAiaMCws8nOsE/giphy.gif",
        "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExbTNqZHR5c20xZHN3aXB0YWF2cGt1eW53cGVyZmZ5dnB3cGtycThibyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/artj92V8o75VPL7AeQ/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNHg5dXZ0MjAwdHR6bWZ5d3gxcDdtajh6Y2R4OGx6ZnN4NHB1MW5pZiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/JIX9t2j0ZTN9S/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNjJkMnc5a3M1anB5aGRsY3hwbW0wMHFlbjdwdmN6dGFtdTZsdXFmZiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/ICOgUNjpvO0PC/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaTJwOG9uOXVwbG8wdnEwZm51cm9ydnF3ZXVvNzY5cm40MnR1OTU2aiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/MDJ9IbxxvDUQM/giphy.gif"
    ];

    const questions = [
        { q: "س1: لماذا تحتاج الكائنات الحية إلى التغذية؟", opts: ["للحصول على الطاقة للنمو والبقاء", "لتصبح منكمشة وصغيرة", "للتوقف عن الحركة", "لصنع طاقة دون غذاء"], a: 0 },
        { q: "س2: ما هي فائدة عملية التنفس للكائنات الحية؟", opts: ["تخزين الماء فقط", "الحصول على الطاقة وإطلاق الفضلات", "التوقف عن التنفس لليلاً", "تجميد الخلايا"], a: 1 },
        { t: "س3: كيف تحمي الكائنات الحية أنواعها من الانقراض؟", opts: ["من خلال النوم المستمر", "من عدم النمو نهائياً", "عبر عملية التكاثر وإنتاج أفراد جديدة", "بالبقاء بمكان واحد"], a: 2 }
    ];

    let ws = null, currentPin = "", isHost = false, score = 0, currentQ = 0;

    function showScreen(id) {
        document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
        document.getElementById(id).classList.add('active');
    }

    function setupHost() {
        isHost = true;
        currentPin = Math.floor(100000 + Math.random() * 900000).toString();
        document.getElementById("pinBox").innerText = currentPin;
        showScreen("hostLobby");

        const protocol = location.protocol === "https:" ? "wss" : "ws";
        ws = new WebSocket(`${protocol}://${location.host}/ws/${currentPin}/host/Teacher`);

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === "player_joined") {
                let list = document.getElementById("playerList");
                list.innerHTML += `<div>👤 طالب جديد انضم: <b>${data.name}</b></div>`;
            }
        };
    }

    function showPlayerJoin() {
        showScreen("playerJoin");
    }

    function joinGame() {
        let pin = document.getElementById("pinInput").value.trim();
        let name = document.getElementById("nameInput").value.trim();
        if (!pin || !name) { alert("يرجى إدخال رقم الـ PIN والاسم!"); return; }

        currentPin = pin;
        const protocol = location.protocol === "https:" ? "wss" : "ws";
        ws = new WebSocket(`${protocol}://${location.host}/ws/${pin}/player/${encodeURIComponent(name)}`);

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === "next_question") {
                loadQuestion(data.questionIndex);
            }
        };

        showScreen("gameScreen");
        document.getElementById("questionTitle").innerText = "⏳ في انتظار بدء المعلم للمسابقة...";
    }

    function startHostGame() {
        currentQ = 0;
        sendQuestionToAll(currentQ);
    }

    function sendQuestionToAll(idx) {
        if (ws) {
            ws.send(JSON.stringify({ type: "next_question", questionIndex: idx }));
        }
        loadQuestion(idx);
    }

    function loadQuestion(idx) {
        currentQ = idx;
        if (idx >= questions.length) {
            showScreen("resultScreen");
            document.getElementById("finalScore").innerText = `مجموع نقاطك: ${score} من ${questions.length}`;
            return;
        }

        showScreen("gameScreen");
        let q = questions[idx];
        document.getElementById("questionTitle").innerText = q.q;

        let container = document.getElementById("optionsContainer");
        container.innerHTML = "";
        q.opts.forEach((opt, i) => {
            let btn = document.createElement("button");
            btn.className = `opt-btn opt-${i}`;
            btn.innerText = opt;
            btn.onclick = () => checkAnswer(i, q.a);
            container.appendChild(btn);
        });
    }

    function checkAnswer(selected, correct) {
        if (selected === correct) {
            score++;
            // عرض ميم السنورة المصفقة العشوائي بدون أي كلام
            let randomMeme = memes[Math.floor(Math.random() * memes.length)];
            document.getElementById("memeImg").src = randomMeme;
            let modal = document.getElementById("memeModal");
            modal.style.display = "flex";

            setTimeout(() => {
                modal.style.display = "none";
                if (isHost) {
                    sendQuestionToAll(currentQ + 1);
                }
            }, 3500);
        } else {
            alert("❌ إجابة خاطئة!");
            if (isHost) {
                sendQuestionToAll(currentQ + 1);
            }
        }
    }
</script>
</body>
</html>
"""


@app.get("/")
async def get_homepage():
  return HTMLResponse(content=HTML_CONTENT)


if __name__ == "__main__":
  import uvicorn

  uvicorn.run(app, host="0.0.0.0", port=8000)