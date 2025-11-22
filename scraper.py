import time
import json
import re 
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, WebDriverException

# ==========================================================
# 🔴 定数定義
# ==========================================================
IFRAME_URL = "https://beyblade.takaratomy.co.jp/beyblade-x/shop_event/manage_jpnew/open_list_all.html"
OUTPUT_JSON_FILENAME = "events.json"
TABLE_SELECTOR = "table.event_list"
WAIT_TIMEOUT = 30
# ==========================================================

# 都道府県名のリスト
PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", 
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県", 
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", 
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県", 
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県", 
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県", 
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"
]


def fetch_schedule_data(url):
    """
    Seleniumを使用して、指定されたURLからイベントデータを抽出する
    (Col1の抽出条件修正: 当日受付をentryへ)
    """
    print(f"スケジュールデータソースに直接アクセス中: {url}")

    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--headless')

    try:
        driver_path = ChromeDriverManager().install()
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"WebDriverの起動に失敗しました: {e}")
        return None

    try:
        driver.get(url)
        wait = WebDriverWait(driver, WAIT_TIMEOUT)

        print(f"テーブル要素 ('{TABLE_SELECTOR}') のロードを待機中...")
        table_element = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, TABLE_SELECTOR))
        )

        time.sleep(2)

        events_data = []
        rows = table_element.find_elements(By.TAG_NAME, 'tr')

        if len(rows) <= 1:
            print("🚨 警告: ヘッダー行しか見つかりませんでした。")
            return []

        print(f"✅ テーブル内に {len(rows)} 行のデータが見つかりました。抽出を開始します。")

        # ヘッダー行 (rows[0]) はスキップ
        for i, row in enumerate(rows[1:]):
            row_index = i + 1
            cols = row.find_elements(By.TAG_NAME, 'td')

            if len(cols) != 2:
                continue

            try:
                col1_text = cols[0].text.strip()
                col2_text = cols[1].text.strip()

                # -------------------------------------------------------
                # 1. Col 1 Parsing (Type分解ロジック)
                # -------------------------------------------------------
                
                # Date & Time
                date_match = re.search(r'(\d{4}年\s*\d{1,2}月\s*\d{1,2}日)', col1_text)
                date_info = date_match.group(1).strip() if date_match else "日付不明"

                time_match = re.search(r'(\d{1,2}：\d{2})', col1_text)
                time_info = time_match.group(1).strip() if time_match else "時間不明"

                # Raw Type Extraction
                type_start_index = col1_text.find(time_info) + len(time_info)
                type_end_index = col1_text.find("詳細はこちら")
                
                raw_type_lines = []
                if type_start_index != -1 and type_end_index != -1 and type_end_index > type_start_index:
                    raw_text = col1_text[type_start_index:type_end_index].strip()
                    # 不要な文字を削除
                    raw_text = raw_text.replace('Share', '').replace('X-TREME', '').strip()
                    raw_type_lines = raw_text.split('\n')
                
                # Typeの中身を分別
                final_type_lines = []
                col1_fee_parts = []
                col1_entry_parts = [] 

                for line in raw_type_lines:
                    line = line.strip()
                    if not line: continue

                    # 条件分岐の修正箇所
                    if "参加費：" in line:
                        col1_fee_parts.append(line)
                    elif "当日受付：" in line:   # 👈 ここを修正 (旧: 参加資格)
                        col1_entry_parts.append(line)
                    else:
                        final_type_lines.append(line)
                
                event_type = "\n".join(final_type_lines).strip()
                if not event_type: event_type = "種別不明"


                # -------------------------------------------------------
                # 2. Col 2 Parsing (Consumed Indices & 統合)
                # -------------------------------------------------------
                
                lines2 = [line.strip() for line in col2_text.split('\n') if line.strip()]
                num_lines = len(lines2)
                consumed_indices = set()

                # 結果格納用リスト（Col 1からのデータを初期値として入れる）
                fee_parts = col1_fee_parts[:]
                entry_parts = col1_entry_parts[:] 
                
                event_name = "名前不明"
                location = "-"
                capacity = "-"
                eligibility = "-"
                address_info = "-"

                # (1) Name (1行目)
                if num_lines > 0:
                    event_name = lines2[0]
                    consumed_indices.add(0)

                # (2) Location (2行目)
                if num_lines > 1:
                    if "定員数 " not in lines2[1]:
                        location = lines2[1]
                        consumed_indices.add(1)
                    else:
                        location = "-"
                        # "定員数"を含む場合はここでは処理せず、ループで拾う

                # (3) Loop for others
                for idx, line in enumerate(lines2):
                    if idx in consumed_indices:
                        continue

                    # --- Fee (参加費) ---
                    if "参加費：" in line:
                        fee_parts.append(line)
                        consumed_indices.add(idx)
                    
                    # --- Capacity (定員数) ---
                    elif "定員数 " in line:
                        capacity = line
                        consumed_indices.add(idx)

                    # --- Eligibility (参加資格) ---
                    elif "参加資格：" in line:
                        eligibility = line
                        consumed_indices.add(idx)

                    # --- Address (住所) ---
                    elif any(line.startswith(pref) for pref in PREFECTURES):
                        address_info = line
                        consumed_indices.add(idx)
                    
                    # --- Entry Logic A: "当日受付：" ---
                    elif "当日受付：" in line:
                        entry_parts.append(line)
                        consumed_indices.add(idx)
                    
                    # --- Entry Logic B: "参加方法" ---
                    elif "参加方法" in line:
                        consumed_indices.add(idx) # ラベル行を使用済みに
                        next_idx = idx + 1
                        if next_idx < num_lines:
                            entry_parts.append(lines2[next_idx])
                            consumed_indices.add(next_idx) # 次の行も使用済みに

                # データの整形・結合
                fee_info = "\n".join(fee_parts) if fee_parts else "-"
                entry_info = "\n".join(entry_parts) if entry_parts else "-"

                # Details (残り)
                details_list = []
                for idx, line in enumerate(lines2):
                    if idx not in consumed_indices:
                        details_list.append(line)
                
                location_details = "\n".join(details_list).strip()
                if not location_details:
                    location_details = "詳細情報なし"

                events_data.append({
                    "date": date_info,
                    "time": time_info,
                    "name": event_name,
                    "location": location,
                    "type": event_type,         # Col 1の残り
                    "fee": fee_info,            # Col 1 + Col 2
                    "capacity": capacity,
                    "eligibility": eligibility, 
                    "address": address_info,
                    "entry": entry_info,        # Col 1(当日受付) + Col 2(当日受付/参加方法)
                    "details": location_details
                })

            except Exception as row_e:
                print(f"❌ 抽出エラー: {row_index}行目の処理中に予期せぬエラーが発生しました: {row_e}")
                continue

        print(f"✅ スケジュールデータ {len(events_data)} 件の抽出に成功しました。")
        return events_data

    except TimeoutException:
        print(f"\n🛑 タイムアウトエラーが発生しました。")
        return None
    except WebDriverException as e:
        print(f"\n❌ WebDriver通信エラー: {e.msg}")
        return None
    except Exception as e:
        print(f"\n❌ エラー: {e}")
        return None
    finally:
        driver.quit()


def save_to_json(data, filename):
    if not data:
        return
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"✅ 保存完了: {filename}")
    except IOError as e:
        print(f"書き込みエラー: {e}")

if __name__ == "__main__":
    extracted_data = fetch_schedule_data(IFRAME_URL)
    if extracted_data is not None:
        save_to_json(extracted_data, OUTPUT_JSON_FILENAME)
