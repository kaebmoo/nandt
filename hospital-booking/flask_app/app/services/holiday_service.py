# flask_app/app/services/holiday_service.py

import requests
from datetime import datetime, date
from typing import List, Dict
import os

class HolidayFetcher:
    
    @staticmethod
    def fetch_holidays_from_ical(year: int) -> List[Dict]:
        """Fetch holidays from BOT API"""
        
        # ใช้ Client ID จาก environment variable
        bot_client_id = os.environ.get('BOT_CLIENT_ID', 'YOUR_CLIENT_ID_HERE')
        
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
            
            # Parse BOT API response
            result_data = data.get('result', {}).get('data', [])
            
            for item in result_data:
                # Parse date from BOT format
                holiday_date = datetime.strptime(item['Date'], '%Y-%m-%d').date()
                
                # Use Thai description
                holiday_name = item['HolidayDescriptionThai']
                
                holidays.append({
                    'date': holiday_date,
                    'name': holiday_name,
                    'source': 'thai_official'  # ใช้ 'thai_official' แทน 'iCal_th'
                })
            
            print(f"Fetched {len(holidays)} holidays from BOT API for year {year}")
            return holidays
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching from BOT API: {e}")
            print(f"Status code: {response.status_code if 'response' in locals() else 'N/A'}")
            print(f"Response: {response.text if 'response' in locals() else 'N/A'}")
            
            # Fallback to hardcoded data
            return HolidayFetcher.get_hardcoded_holidays(year)
        except Exception as e:
            print(f"Unexpected error: {e}")
            return HolidayFetcher.get_hardcoded_holidays(year)
    
    @staticmethod
    def get_hardcoded_holidays(year: int) -> List[Dict]:
        """Fallback hardcoded holidays based on BOT data"""
        
        if year == 2025:
            # Data from BOT API response
            holidays = [
                {'date': date(2025, 1, 1), 'name': 'วันขึ้นปีใหม่'},
                {'date': date(2025, 2, 12), 'name': 'วันมาฆบูชา'},
                {'date': date(2025, 4, 7), 'name': 'ชดเชยวันพระบาทสมเด็จพระพุทธยอดฟ้าจุฬาโลกมหาราช และวันที่ระลึกมหาจักรีบรมราชวงศ์'},
                {'date': date(2025, 4, 14), 'name': 'วันสงกรานต์'},
                {'date': date(2025, 4, 15), 'name': 'วันสงกรานต์'},
                {'date': date(2025, 5, 1), 'name': 'วันแรงงานแห่งชาติ'},
                {'date': date(2025, 5, 5), 'name': 'ชดเชยวันฉัตรมงคล'},
                {'date': date(2025, 5, 12), 'name': 'ชดเชยวันวิสาขบูชา'},
                {'date': date(2025, 6, 2), 'name': 'วันหยุดพิเศษ'},
                {'date': date(2025, 6, 3), 'name': 'วันเฉลิมพระชนมพรรษาสมเด็จพระนางเจ้าสุทิดา พัชรสุธาพิมลลักษณ พระบรมราชินี'},
                {'date': date(2025, 7, 10), 'name': 'วันอาสาฬหบูชา'},
                {'date': date(2025, 7, 28), 'name': 'วันเฉลิมพระชนมพรรษาพระบาทสมเด็จพระเจ้าอยู่หัว'},
                {'date': date(2025, 8, 11), 'name': 'วันหยุดพิเศษ'},
                {'date': date(2025, 8, 12), 'name': 'วันเฉลิมพระชนมพรรษาสมเด็จพระนางเจ้าสิริกิติ์ พระบรมราชินีนาถ พระบรมราชชนนีพันปีหลวง และวันแม่แห่งชาติ'},
                {'date': date(2025, 10, 13), 'name': 'วันนวมินทรมหาราช'},
                {'date': date(2025, 10, 23), 'name': 'วันปิยมหาราช'},
                {'date': date(2025, 12, 5), 'name': 'วันคล้ายวันพระบรมราชสมภพพระบาทสมเด็จพระบรมชนกาธิเบศร มหาภูมิพลอดุลยเดชมหาราช บรมนาถบพิตร วันชาติ และวันพ่อแห่งชาติ'},
                {'date': date(2025, 12, 10), 'name': 'วันรัฐธรรมนูญ'},
                {'date': date(2025, 12, 31), 'name': 'วันสิ้นปี'}
            ]
            
            for holiday in holidays:
                holiday['source'] = 'thai_official'
            
            return holidays
        
        return []