# fastapi_app/app/holiday_service.py

import requests
from datetime import datetime, date
from typing import List, Dict
import os

class HolidayService:
    
    @staticmethod
    def fetch_from_bot_api(year: int) -> List[Dict]:
        """Fetch holidays from BOT API"""
        
        bot_client_id = os.environ.get('BOT_CLIENT_ID', '')
        if not bot_client_id:
            return []
            
        url = f'https://apigw1.bot.or.th/bot/public/financial-institutions-holidays/?year={year}'
        headers = {
            'X-IBM-Client-Id': bot_client_id,
            'accept': 'application/json'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            holidays = []
            
            for item in data.get('result', {}).get('data', []):
                holiday_date = datetime.strptime(item['Date'], '%Y-%m-%d').date()
                holiday_name = item['HolidayDescriptionThai']
                
                # ตัดข้อความในวงเล็บออก
                if '(' in holiday_name:
                    holiday_name = holiday_name.split('(')[0].strip()
                
                # ย่อชื่อยาว
                name_mapping = {
                    'ชดเชยวันพระบาทสมเด็จพระพุทธยอดฟ้าจุฬาโลกมหาราช และวันที่ระลึกมหาจักรีบรมราชวงศ์': 'วันจักรี (ชดเชย)',
                    'วันเฉลิมพระชนมพรรษาสมเด็จพระนางเจ้าสุทิดา พัชรสุธาพิมลลักษณ พระบรมราชินี': 'วันเฉลิมพระชนมพรรษาสมเด็จพระราชินี',
                    'วันเฉลิมพระชนมพรรษาสมเด็จพระนางเจ้าสิริกิติ์ พระบรมราชินีนาถ พระบรมราชชนนีพันปีหลวง และวันแม่แห่งชาติ': 'วันแม่แห่งชาติ',
                    'วันคล้ายวันพระบรมราชสมภพพระบาทสมเด็จพระบรมชนกาธิเบศร มหาภูมิพลอดุลยเดชมหาราช บรมนาถบพิตร วันชาติ และวันพ่อแห่งชาติ': 'วันพ่อแห่งชาติ'
                }
                
                holiday_name = name_mapping.get(holiday_name, holiday_name)
                
                holidays.append({
                    'date': holiday_date,
                    'name': holiday_name,
                    'source': 'bot_official'
                })
            
            return holidays
            
        except Exception as e:
            print(f"Error fetching from BOT: {e}")
            return []