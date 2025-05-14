# teamup_api.py
import requests
import json
import csv
from datetime import datetime, timedelta

class TeamupAPI:
    """
    คลาสสำหรับการเชื่อมต่อกับ TeamUp Calendar API
    """
    
    def __init__(self, api_key, calendar_id):
        """
        กำหนดค่าเริ่มต้นสำหรับการเชื่อมต่อ
        """
        self.api_key = api_key
        self.calendar_id = calendar_id
        self.base_url = f"https://api.teamup.com/{calendar_id}"
        print(f"Base URL: {self.base_url}")  # เพิ่มการ print URL เพื่อตรวจสอบ
        
        self.headers = {
            'Accept': "application/json",
            'Content-Type': "application/json",
            'Teamup-Token': api_key
        }
        print(f"Headers: {self.headers}")  # เพิ่มการ print headers เพื่อตรวจสอบ
        
        # แคชข้อมูลปฏิทินย่อย
        self.subcalendars = {}
    
    def check_access(self):
        """
        ตรวจสอบการเข้าถึง API
        
        returns: (boolean, str) - สถานะการเชื่อมต่อและข้อความ
        """
        try:
            response = requests.get(
                "https://api.teamup.com/check-access",
                headers=self.headers
            )
            
            if response.status_code == 200:
                return True, "เชื่อมต่อสำเร็จ"
            else:
                return False, f"สถานะ: {response.status_code}, ข้อความ: {response.text}"
                
        except Exception as e:
            return False, str(e)
    
    def get_subcalendars(self):
        """
        ดึงรายการปฏิทินย่อย
        
        returns: dict - ข้อมูลปฏิทินย่อย
        """
        try:
            response = requests.get(
                f"{self.base_url}/subcalendars",
                headers=self.headers
            )
            
            # print(f"API Response Status: {response.status_code}")
            # print(f"API Response Content: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                
                # เก็บข้อมูลในแคช
                for subcal in data.get('subcalendars', []):
                    self.subcalendars[subcal['name']] = subcal['id']
                
                return data
            else:
                error_msg = f"ไม่สามารถดึงรายการปฏิทินย่อยได้: {response.text}"
                print(error_msg)
                return {'error': error_msg, 'subcalendars': []}
                
        except Exception as e:
            error_msg = f"เกิดข้อผิดพลาดในการดึงรายการปฏิทินย่อย: {e}"
            print(error_msg)
            return {'error': error_msg, 'subcalendars': []}
    
    def get_subcalendar_id(self, name):
        """
        รับ ID ของปฏิทินย่อยจากชื่อ ถ้าไม่มีจะสร้างใหม่
        
        params:
            name: str - ชื่อปฏิทินย่อย
            
        returns: str - ID ของปฏิทินย่อย
        """
        # ดึงข้อมูลปฏิทินย่อยก่อนหากยังไม่มีในแคช
        if not self.subcalendars:
            self.get_subcalendars()
        
        if name in self.subcalendars:
            return self.subcalendars[name]
        
        # ถ้าไม่มีปฏิทินย่อยดังกล่าว ให้สร้างใหม่
        try:
            new_subcal = {
                'name': name,
                'color': '5', # สีเขียว (เปลี่ยนตามต้องการ)
            }
            
            response = requests.post(
                f"{self.base_url}/subcalendars",
                headers=self.headers,
                data=json.dumps(new_subcal)
            )
            
            if response.status_code == 201:
                data = response.json()
                subcal_id = data['subcalendar']['id']
                self.subcalendars[name] = subcal_id
                return subcal_id
            else:
                error_msg = f"ไม่สามารถสร้างปฏิทินย่อยได้: {response.text}"
                print(error_msg)
                return None
                
        except Exception as e:
            error_msg = f"เกิดข้อผิดพลาดในการสร้างปฏิทินย่อย: {e}"
            print(error_msg)
            return None
    
    def get_events(self, start_date=None, end_date=None, subcalendar_id=None):
        """
        ดึงรายการกิจกรรมในช่วงเวลาที่กำหนด
        
        params:
            start_date: datetime - วันที่เริ่มต้น
            end_date: datetime - วันที่สิ้นสุด
            subcalendar_id: str - ID ของปฏิทินย่อย (ถ้ามี)
            
        returns: dict - ข้อมูลกิจกรรม
        """
        if start_date is None:
            start_date = datetime.now()
        if end_date is None:
            end_date = datetime.now() + timedelta(days=7)
            
        params = {
            'startDate': start_date.strftime('%Y-%m-%d'),
            'endDate': end_date.strftime('%Y-%m-%d')
        }
        
        # ส่ง subcalendarId ในรูปแบบอาร์เรย์ตามที่ API ต้องการ
        if subcalendar_id:
            print(f"กรองตาม subcalendar_id: {subcalendar_id}")
            # กรณีเป็น list
            if isinstance(subcalendar_id, list):
                for id in subcalendar_id:
                    params.setdefault('subcalendarId[]', []).append(id)
            # กรณีเป็นค่าเดียว
            else:
                params['subcalendarId[]'] = subcalendar_id # ใช้ subcalendarId[] แทน subcalendarId
        
        response = requests.get(
            f"{self.base_url}/events",
            headers=self.headers,
            params=params
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            error_msg = f"ไม่สามารถดึงรายการกิจกรรมได้: {response.text}"
            print(error_msg)
            return {"error": error_msg, "events": []}
    
    def create_appointment(self, patient_data):
        """
        สร้างนัดหมายฟอกไตใหม่
        
        params:
            patient_data: dict - ข้อมูลผู้ป่วย
                {
                    'title': str - ชื่อผู้ป่วย
                    'start_date': str - วันที่เริ่มต้น (DD/MM/YYYY)
                    'start_time': str - เวลาเริ่มต้น (HH:MM)
                    'end_date': str - วันที่สิ้นสุด (DD/MM/YYYY)
                    'end_time': str - เวลาสิ้นสุด (HH:MM)
                    'location': str - ตำแหน่ง
                    'who': str - ผู้ดูแล
                    'description': str - รายละเอียด
                    'calendar_name': str - ชื่อปฏิทินย่อย
                }
                
        returns: (boolean, str) - สถานะการสร้างนัดหมายและข้อความหรือ ID
        """
        # ดึง ID ของปฏิทินย่อย
        subcalendar_id = self.get_subcalendar_id(patient_data['calendar_name'])
        
        if not subcalendar_id:
            return False, "ไม่สามารถดึงหรือสร้างปฏิทินย่อยได้"
        
        # แปลงรูปแบบวันที่และเวลา
        start_dt = self._format_datetime(patient_data['start_date'], patient_data['start_time'])
        end_dt = self._format_datetime(patient_data['end_date'], patient_data['end_time'])
        
        # สร้างข้อมูลสำหรับการสร้างกิจกรรม
        event_data = {
            'title': patient_data['title'],
            'start_dt': start_dt,
            'end_dt': end_dt,
            'location': patient_data.get('location', ''),
            'who': patient_data.get('who', ''),
            'notes': patient_data.get('description', ''),
            'subcalendar_ids': [subcalendar_id]
        }
        
        # แสดงข้อมูลที่จะส่งไป (เพื่อการตรวจสอบ)
        print("ข้อมูลที่จะส่งไปยัง API:")
        print(f"URL: {self.base_url}/events")
        print(f"Headers: {self.headers}")
        print(f"ข้อมูล: {json.dumps(event_data, indent=2, ensure_ascii=False)}")
        
        try:
            response = requests.post(
                f"{self.base_url}/events",
                headers=self.headers,
                data=json.dumps(event_data)
            )
            
            # แสดงข้อมูลการตอบกลับ
            print(f"สถานะการตอบกลับ: {response.status_code}")
            print(f"เนื้อหาการตอบกลับ: {response.text}")
            
            if response.status_code == 201:
                data = response.json()
                return True, data['event']['id']
            else:
                return False, f"การสร้างนัดหมายล้มเหลว: {response.text}"
                
        except Exception as e:
            return False, f"เกิดข้อผิดพลาด: {e}"
    
    def update_appointment_status(self, event_id, status):
        """
        อัปเดตสถานะการนัดหมาย
        
        params:
            event_id: str - ID ของกิจกรรม
            status: str - สถานะใหม่ ("มาตามนัด", "ยกเลิก", "ไม่มา")
            
        returns: (boolean, str) - สถานะการอัปเดตและข้อความ
        """
        try:
            # ดึงข้อมูลกิจกรรมปัจจุบัน
            response = requests.get(
                f"{self.base_url}/events/{event_id}",
                headers=self.headers
            )
            
            if response.status_code != 200:
                return False, f"ไม่สามารถดึงข้อมูลนัดหมายได้: {response.text}"
                
            current_event = response.json()['event']
            
            # สร้างชื่อใหม่ตามสถานะ
            title = current_event['title']
            
            # ลบสถานะเดิม (ถ้ามี)
            for old_status in ["(มาตามนัด)", "(ยกเลิก)", "(ไม่มา)"]:
                title = title.replace(old_status, "").strip()
            
            # เพิ่มสถานะใหม่
            new_title = f"{title} ({status})"
            
            # กำหนดข้อมูลที่จะอัปเดต
            update_data = {
                'title': new_title,
                'start_dt': current_event['start_dt'],  # เพิ่มบรรทัดนี้
                'end_dt': current_event['end_dt']       # เพิ่มบรรทัดนี้
            }
            
            # เพิ่มบันทึกเกี่ยวกับการเปลี่ยนสถานะ
            update_data['notes'] = current_event.get('notes', '') + f"\n\nอัปเดตสถานะเป็น '{status}' เมื่อ {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            
            # กำหนดสีตามสถานะ
            if status == "มาตามนัด":
                update_data['color_id'] = "10"  # สีเขียว
            elif status == "ยกเลิก":
                update_data['color_id'] = "9"   # สีแดง
            elif status == "ไม่มา":
                update_data['color_id'] = "8"   # สีเทา
            
            # ส่งคำขออัปเดต
            response = requests.put(
                f"{self.base_url}/events/{event_id}",
                headers=self.headers,
                data=json.dumps(update_data)
            )
            
            if response.status_code == 200:
                return True, "อัปเดตสถานะสำเร็จ"
            else:
                return False, f"การอัปเดตสถานะล้มเหลว: {response.text}"
                
        except Exception as e:
            return False, f"เกิดข้อผิดพลาด: {e}"
    
    def import_from_csv(self, file_path):
        """
        นำเข้าตารางนัดหมายฟอกไตจากไฟล์ CSV
        
        params:
            file_path: str - พาธของไฟล์ CSV
            
        returns: dict - ผลลัพธ์การนำเข้า
        """
        results = {
            'success': 0,
            'failed': 0,
            'errors': []
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for i, row in enumerate(reader, 1):
                    try:
                        # ตรวจสอบข้อมูลที่จำเป็น
                        required_fields = ['Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 'Calendar Name']
                        for field in required_fields:
                            if field not in row or not row[field]:
                                raise ValueError(f"ไม่พบข้อมูลที่จำเป็น: {field}")
                        
                        # แปลงข้อมูลเป็นรูปแบบที่ฟังก์ชัน create_appointment ต้องการ
                        patient_data = {
                            'title': row['Subject'],
                            'start_date': row['Start Date'],
                            'start_time': row['Start Time'],
                            'end_date': row['End Date'],
                            'end_time': row['End Time'],
                            'location': row.get('Location', ''),
                            'who': row.get('Who', ''),
                            'description': row.get('Description', ''),
                            'calendar_name': row['Calendar Name']
                        }
                        
                        # สร้างนัดหมาย
                        success, result = self.create_appointment(patient_data)
                        
                        if success:
                            results['success'] += 1
                        else:
                            results['failed'] += 1
                            results['errors'].append({
                                'row': i,
                                'patient': patient_data['title'],
                                'error': result
                            })
                            
                    except Exception as e:
                        results['failed'] += 1
                        results['errors'].append({
                            'row': i,
                            'error': str(e)
                        })
                
            return results
                
        except Exception as e:
            results['errors'].append({
                'error': f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}"
            })
            return results
    
    def create_recurring_appointments(self, patient_data, recurrence_pattern, weeks=4):
        """
        สร้างนัดหมายที่เกิดซ้ำ
        
        params:
            patient_data: dict - ข้อมูลผู้ป่วย
            recurrence_pattern: list - รูปแบบการเกิดซ้ำ เช่น ['จันทร์', 'พุธ', 'ศุกร์']
            weeks: int - จำนวนสัปดาห์ที่ต้องการสร้างนัดหมาย
            
        returns: dict - ผลลัพธ์การสร้างนัดหมาย
        """
        results = {
            'success': 0,
            'failed': 0,
            'errors': [],
            'event_ids': []
        }
        
        # แปลงรูปแบบวันในสัปดาห์เป็นตัวเลข (0=จันทร์, 6=อาทิตย์)
        day_mapping = {
            'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6,
            'จันทร์': 0, 'อังคาร': 1, 'พุธ': 2, 'พฤหัส': 3, 'ศุกร์': 4, 'เสาร์': 5, 'อาทิตย์': 6
        }
        
        try:
            # แปลงรูปแบบวันที่และเวลาเริ่มต้น
            start_date = datetime.strptime(patient_data['start_date'], '%d/%m/%Y')
            start_time = patient_data['start_time']
            
            # คำนวณระยะเวลาของการนัดหมาย (ชั่วโมง)
            start_dt = datetime.strptime(f"{patient_data['start_date']} {start_time}", '%d/%m/%Y %H:%M')
            end_dt = datetime.strptime(f"{patient_data['end_date']} {patient_data['end_time']}", '%d/%m/%Y %H:%M')
            duration = end_dt - start_dt
            
            # สร้างนัดหมายสำหรับทุกวันในรูปแบบการเกิดซ้ำ ตามจำนวนสัปดาห์ที่กำหนด
            for week in range(weeks):
                for day_name in recurrence_pattern:
                    if day_name in day_mapping:
                        # คำนวณวันที่ให้ตรงกับวันในสัปดาห์ที่ต้องการ
                        target_weekday = day_mapping[day_name]
                        current_weekday = start_date.weekday()
                        days_to_add = (target_weekday - current_weekday) % 7
                        
                        appointment_date = start_date + timedelta(days=days_to_add + (week * 7))
                        
                        # สร้างข้อมูลสำหรับนัดหมายใหม่
                        new_appointment = patient_data.copy()
                        new_appointment['start_date'] = appointment_date.strftime('%d/%m/%Y')
                        new_appointment['end_date'] = appointment_date.strftime('%d/%m/%Y')
                        
                        # เพิ่มข้อมูลเกี่ยวกับการเกิดซ้ำในคำอธิบาย
                        recurrence_info = f"\nนัดหมายซ้ำ: สัปดาห์ที่ {week + 1} / {weeks}, วัน{day_name}"
                        if 'description' in new_appointment:
                            new_appointment['description'] += recurrence_info
                        else:
                            new_appointment['description'] = recurrence_info
                        
                        # สร้างนัดหมาย
                        success, result = self.create_appointment(new_appointment)
                        
                        if success:
                            results['success'] += 1
                            results['event_ids'].append(result)
                        else:
                            results['failed'] += 1
                            results['errors'].append({
                                'date': new_appointment['start_date'],
                                'error': result
                            })
                    else:
                        results['errors'].append({
                            'error': f"รูปแบบวันไม่ถูกต้อง: {day_name}"
                        })
            
            return results
                
        except Exception as e:
            results['errors'].append({
                'error': f"เกิดข้อผิดพลาด: {e}"
            })
            return results
    
    def _format_datetime(self, date_str, time_str):
        """
        แปลงรูปแบบวันที่และเวลาให้ถูกต้องตาม API
        เช่น "12/05/2025", "09:00" เป็น "2025-05-12T09:00:00+07:00"
        
        params:
            date_str: str - วันที่ในรูปแบบ DD/MM/YYYY
            time_str: str - เวลาในรูปแบบ HH:MM
            
        returns: str - วันที่และเวลาในรูปแบบ ISO
        """
        try:
            # แปลงรูปแบบวันที่ (DD/MM/YYYY)
            if '/' in date_str:
                day, month, year = date_str.split('/')
                date_formatted = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            else:
                # ถ้าไม่ได้อยู่ในรูปแบบ DD/MM/YYYY ให้ส่งคืนค่าเดิม
                date_formatted = date_str
            
            # แปลงรูปแบบเวลา (HH:MM)
            time_parts = time_str.split(':')
            hour = time_parts[0].zfill(2)
            minute = time_parts[1].zfill(2) if len(time_parts) > 1 else "00"
            
            # รวมวันที่และเวลา พร้อม timezone (+07:00 สำหรับประเทศไทย)
            datetime_str = f"{date_formatted}T{hour}:{minute}:00+07:00"
            print(f"แปลงวันที่จาก {date_str} {time_str} เป็น {datetime_str}")
            return datetime_str
            
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการแปลงรูปแบบวันที่และเวลา: {e}")
            # ส่งคืนค่าเดิมในกรณีที่มีข้อผิดพลาด
            return f"{date_str}T{time_str}:00+07:00"