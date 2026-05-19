import time
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

# ==================== [ ⚙️ 多人多部位監控設定區 ] ====================
# 
# 你可以無限往下增加監控目標，每個人可以有獨立的名稱、部位與通知頻道。
# 部位代碼參考：HAIR(髮型), CAP(帽子), COAT(上衣), PANTS(下衣), CAPE(披風), GLOVE(手套), SHOES(鞋子)
#
MONITOR_TARGETS = [
    {
        "name": "石油王",
        "ppsn": "20372100005972917",
        "webhook_url": "https://discord.com/api/webhooks/1505922010264637522/h14VhSshRBlVL_mcCFNjTZHaG6yHR1kzwBOQZ9eS8jLn32lP83M-6xkKv3Wi87SZiWpk",
        "parts": ["HAIR"]  # 監控這人的髮型
    },
    {
        "name": "韓國PAKA頭",
        "ppsn": "20372100000900216",
        "webhook_url": "https://discord.com/api/webhooks/1505922010264637522/h14VhSshRBlVL_mcCFNjTZHaG6yHR1kzwBOQZ9eS8jLn32lP83M-6xkKv3Wi87SZiWpk",
        "parts": ["HAIR"]  # 監控這人的髮型
    }
]

# ⚠️ 請把這裡換成你「裝備提取網站」在 GitHub Pages 的真實管理面板網址
MY_EXTRACTOR_WEB_URL = "https://xmasakix.github.io/msw-extractor-web/index.html"

# 全域憑證管理
CONFIG = {
    "token": "",
    "user_id": "",
    "is_token_valid": False
}

# 記憶庫：用來儲存每個人各部位「上一次的物品ID」
history_cache = {}

# ===================================================================

def send_system_alert(msg):
    """發送系統通知（過期警報等）到名單中第一個有效的 Webhook，並附帶一鍵開啟網站連結"""
    if MONITOR_TARGETS and MONITOR_TARGETS[0]["webhook_url"]:
        # 在警報訊息底下串接藍色傳送門連結
        click_link = f"\n\n🔗 **[點我一鍵開啟裝備提取網站]({MY_EXTRACTOR_WEB_URL})**"
        payload = {
            "embeds": [{
                "title": "🚨 系統狀態回報", 
                "description": f"{msg}{click_link}", 
                "color": 15158332
            }]
        }
        try: requests.post(MONITOR_TARGETS[0]["webhook_url"], json=payload, timeout=5)
        except: pass

def get_headers():
    return {
        "mod-accesstoken": CONFIG["token"],
        "mod-user-id": CONFIG["user_id"],
        "x-mod-client": "727d112f1370415e85686530ec048fb7",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

def monitor_loop():
    print("🚀 造型部位獵手已啟動...")
    
    while True:
        # 如果 Token 還沒匯入或失效，先暫停等候
        if not CONFIG["is_token_valid"] or not CONFIG["token"]:
            time.sleep(10)
            continue
            
        # 開始輪詢名單上的每一個人
        for target in MONITOR_TARGETS:
            name = target["name"]
            ppsn = target["ppsn"]
            webhook = target["webhook_url"]
            monitored_parts = target["parts"]
            
            # 初始化該玩家的記憶庫
            if ppsn not in history_cache:
                history_cache[ppsn] = {}
                
            url = f"https://mod-gateway-prd-tokyo-2.nexon.com/mverse/v1/shop/mod/inventory/avatars/manage/equip/list/{ppsn}?_t={int(time.time()*1000)}"
            
            try:
                res = requests.get(url, headers=get_headers(), timeout=10)
                
                # 處理 Token 過期
                if res.status_code in [401, 403]:
                    print("⚠️ Token 已過期！")
                    CONFIG["is_token_valid"] = False
                    send_system_alert("❌ **憑證已過期！** 請重新更新 Token。")
                    break # 跳出人物循環，等待新 Token
                    
                if res.status_code == 200:
                    items = res.json().get("data", {}).get("items", [])
                    
                    # 針對該玩家指定的「每個部位」進行檢查
                    for part in monitored_parts:
                        # 找出對應部位的穿戴道具
                        equip_item = next((item for item in items if item.get("avatarType") == part), None)
                        
                        if equip_item:
                            current_id = equip_item.get("itemId")
                            current_name = equip_item.get("itemName", f"未命名{part}")
                            
                            # 取得上一次記錄的 ID
                            last_id = history_cache[ppsn].get(part)
                            
                            # 1. 第一次監控到此部位：只紀錄，不發通知
                            if last_id is None:
                                history_cache[ppsn][part] = current_id
                                print(f"📌 [{name}] 已紀錄初始 {part}: {current_name} ({current_id})")
                                
                            # 2. 發現更換（目前 ID 與上次紀錄不同）
                            elif current_id != last_id:
                                print(f"🔥 偵測到 [{name}] 更換了 {part}！新造型: {current_name}")
                                history_cache[ppsn][part] = current_id # 更新記憶庫
                                
                                # 抓取商城詳細資料 (作者與價格)
                                detail_url = f"https://mod-gateway-prd-tokyo-2.nexon.com/mverse/v1/shop/mod/sale/avatars/{current_id}"
                                detail_res = requests.get(detail_url, headers=get_headers(), timeout=10)
                                detail = detail_res.json().get("data", {}) if detail_res.status_code == 200 else {}
                                
                                # 組合 Discord 通知卡片
                                img_url = equip_item.get("itemImageUrl") or equip_item.get("itemThumbnailUrl") or f"https://mod-file.dn.nexoncdn.com/prime/inventory/icon/{current_id}"
                                author = f"{detail.get('nickname')}#{detail.get('profileCode')}" if detail.get('profileCode') else (detail.get('nickname') or "未知")
                                
                                part_names = {"HAIR": " 髮型 ", "CAP": " 帽子 ", "COAT": " 上衣 ", "PANTS": " 下衣 ", "CAPE": " 披風 ", "SHOES": " 鞋子 "}
                                part_display = part_names.get(part, part)

                                # 🛠️ 自動生成帶有商品 ID 參數的一鍵搜尋網址
                                auto_search_url = f"{MY_EXTRACTOR_WEB_URL}?search_id={current_id}"

                                payload = {
                                    "embeds": [{
                                        "title": f"🚨 {name} 更換造型！",
                                        # 這裡把道具名稱加上 Markdown 語法，變成一鍵跳轉搜尋按鈕
                                        "description": f"玩家穿上了 **{part_display}** 部位：**[{current_name}]({auto_search_url})**\n\n💡 *[點擊上方藍字道具名稱，即可自動開啟網站並搜尋該商品]*",
                                        "color": 3447003 if part == "HAIR" else 10181046, 
                                        "fields": [
                                            {"name": "🆔 商品 ID", "value": f"`{current_id}`", "inline": True},
                                            {"name": "👤 創作者", "value": author, "inline": True}
                                        ],
                                        "thumbnail": {"url": img_url},
                                        "footer": {"text": f"造型獵手捕捉 • 部位: {part}"}
                                    }]
                                }
                                requests.post(webhook, json=payload, timeout=5)
                                
            except Exception as e:
                print(f"❌ 監控 [{name}] 時發生異常: {e}")
                
            time.sleep(0.5)
            
        time.sleep(15)

# 啟動背景線程
monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
monitor_thread.start()

@app.route('/')
def home():
    status = "運作中 (Token 有效)" if CONFIG["is_token_valid"] else "等待 Token 匯入中"
    return f"MSW 多人多部位監控服務已啟動。當前狀態: {status}"

@app.route('/api/update-token', methods=['POST'])
def update_token():
    data = request.json or {}
    token = data.get("token")
    user_id = data.get("userId")
    
    if not token or not user_id:
        return jsonify({"success": False, "message": "缺少 Token 欄位"}), 400
        
    CONFIG["token"] = token
    CONFIG["user_id"] = user_id
    CONFIG["is_token_valid"] = True
    
    global history_cache
    history_cache = {}
    
    print("🔑 雲端已同步收到網頁更新的 Token，重置監控快取！")
    send_system_alert("🔑 **Token 更新成功！** 監控已重新開始運作。")
    
    return jsonify({"success": True, "message": "雲端多目標監控已重新繼續運作！"})

# 🌐 新增：供前端網頁自動過來「撈取目前有效 Token」的 API 路由
@app.route('/api/get-current-token', methods=['GET'])
def get_current_token():
    if CONFIG["is_token_valid"] and CONFIG["token"]:
        return jsonify({
            "success": True, 
            "token": CONFIG["token"], 
            "userId": CONFIG["user_id"]
        })
    else:
        return jsonify({
            "success": False, 
            "message": "雲端目前沒有有效的 Token，請先更新"
        }), 404

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
