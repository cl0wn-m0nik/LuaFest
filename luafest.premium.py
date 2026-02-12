import webview
import requests
import threading
import zipfile
import io
import os
import json
import time
import webbrowser

# ================== BACKEND: LUA-CORE ==================

CONFIG_FILE = "config.json"
MANIFEST_URL = "https://codeload.github.com/SteamAutoCracks/ManifestHub/zip/refs/heads/{}"

class LuaFestApi:
    def __init__(self):
        self._window = None
        self.config = self.load_all_config()

    def set_window(self, window):
        self._window = window

    def load_all_config(self):
        default = {"base_dir": "Seçilmedi", "library": []}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "library" not in data: data["library"] = []
                    return data
            except: return default
        return default

    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=4)

    def select_folder(self):
        folder = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if folder and len(folder) > 0:
            self.config["base_dir"] = folder[0]
            self.save_config()
            return {"status": "success", "path": folder[0]}
        return {"status": "error"}

    def get_game_details(self, appid):
        appid = str(appid)
        try:
            url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=turkish"
            r = requests.get(url, timeout=5).json()
            if r[appid]["success"]:
                data = r[appid]["data"]
                return {
                    "status": "success",
                    "name": data.get("name"),
                    "description": data.get("short_description", "Açıklama bulunamadı."),
                    "image": data.get("header_image"),
                    "id": appid,
                    "developer": data.get("developers", ["Bilinmiyor"])[0]
                }
        except: pass
        return {"status": "error"}

    def search_steam(self, query):
        if len(query) < 2: return []
        try:
            url = f"https://store.steampowered.com/api/storesearch/?term={query}&l=turkish&cc=TR"
            data = requests.get(url, timeout=5).json()
            return [{"name": i['name'], "id": str(i['id']), "image": i.get('tiny_image', '').replace('capsule_sm_120', 'capsule_184x69')} for i in data.get('items', [])]
        except: return []

    def add_to_local_library(self, game_data):
        # ID'yi stringe zorla (Çakışma olmaması için)
        game_id = str(game_data['id'])
        if not any(str(g['id']) == game_id for g in self.config['library']):
            self.config['library'].append({
                "id": game_id,
                "name": game_data['name'],
                "image": game_data['image']
            })
            self.save_config()
            return {"status": "success"}
        return {"status": "exists"}

    def remove_from_library(self, appid):
        self.config['library'] = [g for g in self.config['library'] if str(g['id']) != str(appid)]
        self.save_config()
        return {"status": "success"}

    def get_library(self): return self.config['library']
    def get_base_dir(self): return self.config['base_dir']
    def open_discord(self): webbrowser.open("https://dsc.gg/mtamc")

    def start_manifest_download(self, appid):
        if self.config["base_dir"] == "Seçilmedi":
            return {"status": "error", "message": "Lütfen Ayarlar'dan indirme klasörü seçin!"}
        threading.Thread(target=self._download_logic, args=(appid,), daemon=True).start()
        return {"status": "started"}

    def _download_logic(self, appid):
        try:
            self._js("updateStatus", "Sistem Bağlanıyor...", "loading")
            time.sleep(0.5)
            path = os.path.join(self.config["base_dir"], str(appid))
            os.makedirs(path, exist_ok=True)
            r = requests.get(MANIFEST_URL.format(appid), timeout=20)
            if r.status_code == 200:
                self._js("updateStatus", "Manifest Yazılıyor...", "loading")
                zipfile.ZipFile(io.BytesIO(r.content)).extractall(path)
                self._js("updateStatus", "TAMAMLANDI!", "success")
            else:
                self._js("updateStatus", "Hata: Dosya Yok.", "error")
        except Exception as e:
            self._js("updateStatus", f"Hata: {str(e)}", "error")

    def _js(self, func, *args):
        if self._window:
            args_str = ",".join([f"'{str(a)}'" for a in args])
            self._window.evaluate_js(f"{func}({args_str})")

# ================== FRONTEND: BLACK-UI ==================

html_content = """
<!DOCTYPE html>
<html>
<head>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');
        :root { --bg: #09090b; --sidebar: #000000; --card: #141417; --accent: #ffffff; --text: #fafafa; --text-dim: #a1a1aa; --border: #27272a; }
        
        * { margin:0; padding:0; box-sizing:border-box; font-family:'Inter', sans-serif; }
        body { background: var(--bg); color: var(--text); display: flex; height: 100vh; overflow: hidden; }

        /* --- SIDEBAR (Stealth Look) --- */
        .sidebar { width: 70px; background: var(--sidebar); border-right: 1px solid var(--border); display: flex; flex-direction: column; align-items: center; padding: 25px 0; gap: 25px; }
        .nav-item { width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; border-radius: 12px; color: var(--text-dim); cursor: pointer; transition: 0.2s; }
        .nav-item:hover { color: var(--accent); background: #18181b; }
        .nav-item.active { background: var(--accent); color: var(--sidebar); }

        /* --- MAIN AREA --- */
        .main { flex: 1; padding: 40px 60px; overflow-y: auto; position: relative; }
        .view { display: none; }
        .view.active { display: block; animation: slideUp 0.4s ease; }

        /* --- PREMIUM HEADER --- */
        .hero { background: linear-gradient(135deg, #18181b 0%, #09090b 100%); border: 1px solid var(--border); padding: 40px; border-radius: 24px; margin-bottom: 40px; }
        h1 { font-size: 2.2rem; font-weight: 800; letter-spacing: -1px; margin-bottom: 8px; }
        .badge { display: inline-block; padding: 5px 12px; border-radius: 6px; background: #27272a; color: var(--text-dim); font-size: 0.7rem; font-weight: 700; text-transform: uppercase; margin-bottom: 15px; }

        /* --- SEARCH BOX --- */
        .search-wrap { position: relative; width: 100%; max-width: 600px; }
        input { width: 100%; background: #000000; border: 1px solid var(--border); padding: 16px 20px; border-radius: 12px; color: white; font-size: 0.95rem; }
        input:focus { border-color: var(--accent); }
        .search-results { position: absolute; width: 100%; background: #000000; border: 1px solid var(--border); border-radius: 12px; margin-top: 8px; z-index: 100; display: none; overflow: hidden; box-shadow: 0 20px 40px rgba(0,0,0,0.8); }
        .res-item { display: flex; align-items: center; padding: 12px; cursor: pointer; border-bottom: 1px solid var(--border); }
        .res-item:hover { background: #18181b; }
        .res-item img { width: 45px; border-radius: 4px; margin-right: 15px; }

        /* --- GAME GRID --- */
        .section-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 20px; color: var(--text-dim); }
        .game-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 20px; }
        .game-card { background: var(--card); border-radius: 16px; padding: 10px; cursor: pointer; transition: 0.2s; border: 1px solid var(--border); }
        .game-card:hover { border-color: var(--accent); transform: translateY(-5px); }
        .game-card img { width: 100%; border-radius: 10px; margin-bottom: 10px; }
        .game-card span { font-size: 0.85rem; font-weight: 600; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

        /* --- OVERLAY MODAL (Black Out) --- */
        .overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); z-index: 1000; display: none; justify-content: center; align-items: center; }
        .detail-card { width: 700px; background: #000; border: 1px solid var(--border); border-radius: 24px; display: flex; overflow: hidden; animation: popUp 0.3s ease; }
        .detail-img { width: 280px; height: 100%; object-fit: cover; }
        .detail-content { flex: 1; padding: 40px; }
        
        .btn { width: 100%; padding: 14px; border-radius: 8px; border: none; font-weight: 600; cursor: pointer; margin-top: 12px; font-size: 0.85rem; transition: 0.2s; }
        .btn-primary { background: var(--accent); color: #000; }
        .btn-secondary { background: transparent; border: 1px solid var(--border); color: white; }
        .btn-danger { color: #ff4444; background: rgba(255,68,68,0.05); }
        .btn:hover { opacity: 0.8; }

        /* --- SETTINGS --- */
        .settings-item { background: var(--card); border: 1px solid var(--border); padding: 25px; border-radius: 16px; margin-bottom: 15px; }
        .path-label { font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; }
        .path-value { background: #000; padding: 12px; border-radius: 8px; margin: 10px 0; font-family: monospace; font-size: 0.8rem; border: 1px solid var(--border); }
        .warning-box { border-left: 2px solid #eab308; background: rgba(234,179,8,0.05); padding: 15px; color: #facc15; font-size: 0.85rem; border-radius: 0 8px 8px 0; }

        /* --- STATUS & TOAST --- */
        #statusBox { margin-top: 20px; padding: 15px; border-radius: 8px; background: #09090b; border: 1px solid var(--border); display: none; align-items: center; gap: 10px; }
        .spinner { width: 18px; height: 18px; border: 2px solid #222; border-top-color: white; border-radius: 50%; animation: spin 0.8s linear infinite; }
        #toast { position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%); background: white; color: black; padding: 10px 25px; border-radius: 8px; font-weight: 600; font-size: 0.85rem; display: none; z-index: 2000; }

        @keyframes slideUp { from { opacity:0; transform: translateY(20px); } to { opacity:1; transform: translateY(0); } }
        @keyframes popUp { from { opacity:0; transform: scale(0.95); } to { opacity:1; transform: scale(1); } }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>

    <div id="toast">Bildirim</div>

    <div class="sidebar">
        <div class="nav-item active" onclick="showView('search', this)"><svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg></div>
        <div class="nav-item" onclick="showView('library', this)"><svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg></div>
        <div class="nav-item" onclick="showView('settings', this)"><svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg></div>
        <div style="margin-top: auto;" class="nav-item" onclick="pywebview.api.open_discord()"><svg width="22" height="22" fill="currentColor" viewBox="0 0 24 24"><path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.862-1.297 1.187-1.995a.076.076 0 0 0-.041-.105 13.1 13.1 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.06.06 0 0 0-.031-.03z"/></svg></div>
    </div>

    <div class="main">
        <div id="view-search" class="view active">
            <div class="hero">
                <div class="badge">V2 Stable</div>
                <h1>Keşfetmeye Başla</h1>
                <p style="color:var(--text-dim); font-size:0.9rem;">Tüm Steam kütüphanesine eriş ve manifestleri yerelleştir.</p>
            </div>
            
            <div class="section-title">Oyun Ara</div>
            <div class="search-wrap">
                <input type="text" id="searchInput" placeholder="Oyunun adını yazınız..." oninput="searchGame(this.value)">
                <div id="resBox" class="search-results"></div>
            </div>
        </div>

        <div id="view-library" class="view">
            <h1>Kütüphanem</h1>
            <p style="color:var(--text-dim); margin-bottom:40px;">Eklediğiniz tüm oyunlar ve yerel kopyalar.</p>
            <div id="libGrid" class="game-grid"></div>
        </div>

        <div id="view-settings" class="view">
            <h1>Ayarlar</h1>
            <p style="color:var(--text-dim); margin-bottom:40px;">Uygulama konfigürasyonu ve sistem bilgileri.</p>
            
            <div class="settings-item">
                <div class="path-label">İndirme Klasörü</div>
                <div id="pathDisplay" class="path-value">...</div>
                <button class="btn btn-primary" style="width:auto; padding:10px 20px" onclick="changeFolder()">Değiştir</button>
            </div>

            <div class="settings-item">
                <div class="path-label">Sistem Uyarısı</div>
                <div class="warning-box" style="margin-top:10px">
                    <b>Dikkat:</b> Bu uygulama yalnızca oyunların manifest dosyalarını indiren bir araçtır. Oyun kopyalama veya dağıtma işlevi görmez.
                </div>
            </div>
        </div>
    </div>

    <div id="overlay" class="overlay">
        <div class="detail-card">
            <img id="dImg" class="detail-img" src="">
            <div class="detail-content">
                <div style="text-align:right; margin-bottom:-20px;"><span onclick="closeDetail()" style="cursor:pointer; color:var(--text-dim)">Kapat</span></div>
                <h2 id="dTitle" style="margin-top:20px; font-size:1.8rem;">Oyun İsmi</h2>
                <p id="dDev" style="color:var(--text-dim); font-size:0.8rem; margin-top:5px; margin-bottom:20px;">Geliştirici</p>
                <div id="dDesc" style="font-size:0.85rem; line-height:1.6; color:#ccc; max-height:120px; overflow-y:auto; margin-bottom:25px;">...</div>
                
                <div id="dButtons"></div>

                <div id="statusBox">
                    <div class="spinner"></div>
                    <span id="statusText" style="font-size:0.8rem">Yükleniyor...</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        function showView(id, el) {
            document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
            document.getElementById('view-'+id).classList.add('active');
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            el.classList.add('active');
            if(id === 'library') loadLibrary();
            if(id === 'settings') updatePathUI();
        }

        async function updatePathUI() {
            const path = await pywebview.api.get_base_dir();
            document.getElementById('pathDisplay').innerText = path;
        }

        async function changeFolder() {
            const res = await pywebview.api.select_folder();
            if(res.status === 'success') { updatePathUI(); showToast("Klasör güncellendi."); }
        }

        async function searchGame(q) {
            const box = document.getElementById('resBox');
            if(q.length < 2) { box.style.display = 'none'; return; }
            const res = await pywebview.api.search_steam(q);
            box.innerHTML = '';
            res.forEach(g => {
                const item = document.createElement('div');
                item.className = 'res-item';
                item.innerHTML = `<img src="${g.image}"><span>${g.name}</span>`;
                item.onclick = () => openDetail(g.id, true);
                box.appendChild(item);
            });
            box.style.display = 'block';
        }

        async function openDetail(appid, isSearch) {
            const detail = await pywebview.api.get_game_details(appid);
            if(detail.status === 'error') return;

            document.getElementById('dTitle').innerText = detail.name;
            document.getElementById('dDev').innerText = detail.developer;
            document.getElementById('dDesc').innerText = detail.description;
            document.getElementById('dImg').src = detail.image;
            
            const btnContainer = document.getElementById('dButtons');
            btnContainer.innerHTML = '';
            
            if(isSearch) {
                const addBtn = document.createElement('button');
                addBtn.className = 'btn btn-primary';
                addBtn.innerText = 'KÜTÜPHANEYE EKLE';
                addBtn.onclick = async () => {
                    const res = await pywebview.api.add_to_local_library({id: detail.id, name: detail.name, image: detail.image});
                    showToast(res.status === 'success' ? "Eklendi!" : "Zaten Mevcut.");
                    closeDetail();
                };
                btnContainer.appendChild(addBtn);
            }

            const dlBtn = document.createElement('button');
            dlBtn.className = 'btn btn-secondary';
            dlBtn.innerText = 'MANIFEST İNDİR';
            dlBtn.onclick = () => {
                document.getElementById('statusBox').style.display = 'flex';
                pywebview.api.start_manifest_download(detail.id);
            };
            btnContainer.appendChild(dlBtn);

            if(!isSearch) {
                const remBtn = document.createElement('button');
                remBtn.className = 'btn btn-danger';
                remBtn.innerText = 'Kütüphaneden Kaldır';
                remBtn.onclick = async () => {
                    await pywebview.api.remove_from_library(detail.id);
                    closeDetail();
                    loadLibrary();
                };
                btnContainer.appendChild(remBtn);
            }

            document.getElementById('overlay').style.display = 'flex';
            document.getElementById('resBox').style.display = 'none';
        }

        function closeDetail() { 
            document.getElementById('overlay').style.display = 'none'; 
            document.getElementById('statusBox').style.display = 'none';
        }

        async function loadLibrary() {
            const grid = document.getElementById('libGrid');
            const lib = await pywebview.api.get_library();
            grid.innerHTML = '';
            lib.forEach(g => {
                const card = document.createElement('div');
                card.className = 'game-card';
                card.innerHTML = `<img src="${g.image}"><span>${g.name}</span>`;
                card.onclick = () => openDetail(g.id, false);
                grid.appendChild(card);
            });
        }

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.innerText = msg;
            t.style.display = 'block';
            setTimeout(() => { t.style.display = 'none'; }, 3000);
        }

        function updateStatus(msg, type) {
            const txt = document.getElementById('statusText');
            txt.innerText = msg;
            if(type === 'success') {
                showToast("Manifest hazır.");
                setTimeout(closeDetail, 1500);
            }
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    api = LuaFestApi()
    window = webview.create_window('LuaFest', html=html_content, js_api=api, width=1100, height=750, background_color='#09090b')
    api.set_window(window)
    webview.start()