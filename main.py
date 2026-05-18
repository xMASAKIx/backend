import time
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)  # 允許你的 GitHub 前端網頁跨網域把 Token 傳過來

# 全域變數：儲存目前的憑證與監控狀態
CONFIG = {
    "token": "",
    "user_id": "",
    "target_ppsn": "20372100005972917",
    "webhook_url": "https://discord.com/api/webhooks/1505922010264637522/h14VhSshRBlVL_mcCFNjTZHaG6yHR1kzwBOQZ9eS8jLn32lP83M-6xkKv3Wi87SZiWpk",
    "last_hair_id": None,
    "is_token_valid": False
}

def send_discord_log(msg, is_error=False):
    """發送普通日誌或過期警報到 Discord"""
    payload = {
        "embeds": [{
            "title": "🚨 TOKEN過期警報" if is_error else "ℹ️ 系統提示",
            "description": msg,
            "color": 15158332 if is_error else 3447003
        }]
    }
    try:
        requests.post(CONFIG["webhook_url"], json=payload, timeout=5)
    except:
        pass

def get_headers():
    return {
        "mod-accesstoken": CONFIG["token"],
        "mod-user-id": CONFIG["user_id"],
        "x-mod-client": "727d112f1370415e85686530ec048fb7",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

def monitor_loop():
    """24小時不間斷監控線程"""
    print("後端監控線程已啟動...")
    while True:
        # 如果目前沒有有效的 Token，就每 10 秒檢查一次有沒有新 Token 進來
        if not CONFIG["is_token_valid"] or not CONFIG["token"]:
            time.sleep(10)
            continue

        ppsn = CONFIG["target_ppsn"]
        url = f"https://mod-gateway-prd-tokyo-2.nexon.com/mverse/v1/shop/mod/inventory/avatars/manage/equip/list/{ppsn}?_t={int(time.time()*1000)}"
        
        try:
            res = requests.get(url, headers=get_headers(), timeout=10)
            
            # 處理 Token 過期或失效
            if res.status_code in [401, 403]:
                print("偵測到 Token 已過期！")
                CONFIG["is_token_valid"] = False
                send_discord_log("❌ **Nexon 憑證已過期！** 監控已暫停，請點擊網頁重新匯入 Token JSON！", is_error=True)
                continue
                
            if res.status_code == 200:
                items = res.json().get("data", {}).get("items", [])
                hair_item = next((item for item in items if item.get("avatarType") == "HAIR"), None)
                
                if hair_item:
                    current_id = hair_item.get("itemId")
                    current_name = hair_item.get("itemName", "未命名髮型")
                    
                    # 剛匯入 Token 時的初始紀錄
                    if CONFIG["last_hair_id"] is None:
                        CONFIG["last_hair_id"] = current_id
                        print(f"紀錄初始髮型: {current_name}")
                    
                    # 發現更換髮型
                    elif current_id != CONFIG["last_hair_id"]:
                        CONFIG["last_hair_id"] = current_id
                        
                        # 抓取詳細商城資料
                        detail_url = f"https://mod-gateway-prd-tokyo-2.nexon.com/mverse/v1/shop/mod/sale/avatars/{current_id}"
                        detail_res = requests.get(detail_url, headers=get_headers(), timeout=10)
                        detail = detail_res.json().get("data", {}) if detail_res.status_code == 200 else {}
                        
                        # 發送精美換裝通知
                        img_url = hair_item.get("itemImageUrl") or hair_item.get("itemThumbnailUrl") or f"https://mod-file.dn.nexon.com/prime/inventory/icon/{current_id}"
                        price = detail.get("itemPrice") or detail.get("price") or "未上架"
                        author = f"{detail.get('nickname')}#{detail.get('profileCode')}" if detail.get('profileCode') else (detail.get('nickname') or "未知")
                        
                        payload = {
                            "embeds": [{
                                "title": "🚨 監控目標更換髮型！",
                                "color": 16743484,
                                "fields": [
                                    {"name": "📝 髮型名稱", "value": current_name, "inline": True},
                                    {"name": "🆔 商品 ID", "value": f"`{current_id}`", "inline": True},
                                    {"name": "👤 創作者", "value": author, "inline": False},
                                    {"name": "💰 商城售價", "value": f"{price} wc", "inline": True},
                                ],
                                "thumbnail": {"url": img_url}
                            }]
                        }
                        requests.post(CONFIG["webhook_url"], json=payload, timeout=5)
            
        except Exception as e:
            print(f"監控循環發生異常: {e}")
            
        # 每 30 秒輪詢檢查一次
        time.sleep(60)

# 在 Flask 啟動前，先把後端監控線程丟到背景跑
monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
monitor_thread.start()

@app.route('/')
def home():
    status = "運作中 (Token 有效)" if CONFIG["is_token_valid"] else "等待 Token 匯入中"
    return f"MSW 24H 監控服務狀態: {status}"

@app.route('/api/update-token', methods=['POST'])
def update_token():
    """接收前端網頁丟過來的 JSON Token"""
    data = request.json or {}
    token = data.get("token")
    user_id = data.get("userId")
    
    if not token or not user_id:
        return jsonify({"success": False, "message": "缺少必要的 Token 欄位"}), 400
        
    CONFIG["token"] = token
    CONFIG["user_id"] = user_id
    CONFIG["is_token_valid"] = True
    CONFIG["last_hair_id"] = None # 重新重設以防漏看
    
    print("成功從網頁更新 Token！")
    send_discord_log("🔑 **Token 更新成功！** 雲端 24H 監控已重新繼續運作。")
    
    return jsonify({"success": True, "message": "後端 Token 已成功同步並啟用監控！"})

if __name__ == '__main__':
    # Render 會自動提供 PORT 環境變數
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
