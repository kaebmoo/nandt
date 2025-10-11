# fastapi_app/app/holiday_service.py

import requests
from datetime import datetime, date
from typing import List, Dict
import os

class HolidayService:
    '''
    Service to fetch and process holiday data from BOT API
    https://portal.api.bot.or.th/
    '''
    
    @staticmethod
    def fetch_from_bot_api(year: int) -> List[Dict]:
        """Fetch holidays from BOT API"""
        
        token = os.environ.get('BOT_TOKEN', '')
        if not token:
            return []
            
        url = f'https://gateway.api.bot.or.th/financial-institutions-holidays/?year={year}'
        headers = {
            'Authorization': token,
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