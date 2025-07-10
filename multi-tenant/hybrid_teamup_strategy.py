# hybrid_teamup_strategy.py
"""
Hybrid TeamUp Strategy:
1. แต่ละ Organization = 1 Master Calendar
2. ใน 1 Master Calendar มีหลาย Subcalendars (จำกัดตาม TeamUp plan)
3. ถ้า subcalendars เต็มแล้ว สร้าง Master Calendar ใหม่
"""

import requests
import json
from datetime import datetime, timedelta
import os
import uuid

class HybridTeamUpManager:
    """จัดการ TeamUp Calendars แบบ Hybrid"""
    
    def __init__(self):
        self.master_api_key = os.getenv('MASTER_TEAMUP_API')
        self.base_url = "https://api.teamup.com"
        self.headers = {
            'Accept': "application/json",
            'Content-Type': "application/json",
            'Teamup-Token': self.master_api_key
        }
        
        # ขีดจำกัด subcalendars ตาม TeamUp plan
        self.subcalendar_limits = {
            'free': 8,
            'plus': 48,
            'pro': 48,
            'business': 96
        }
        
        # Plan ที่เราใช้ (ควรเก็บใน config)
        self.teamup_plan = os.getenv('TEAMUP_PLAN', 'free')
        self.max_subcalendars = self.subcalendar_limits[self.teamup_plan]
    
    def create_organization_setup(self, organization):
        """สร้าง TeamUp setup สำหรับ organization ใหม่"""
        try:
            # Import ที่นี่เพื่อป้องกัน circular import
            from models import db, TeamUpCalendar, OrganizationSubcalendar
            
            # สร้าง Master Calendar แรก
            calendar_result = self.create_master_calendar(organization)
            if not calendar_result['success']:
                return calendar_result
            
            calendar_id = calendar_result['calendar_id']
            
            # บันทึก Master Calendar
            teamup_calendar = TeamUpCalendar(
                organization_id=organization.id,
                calendar_id=calendar_id,
                calendar_name=f"{organization.name} - Main",
                is_primary=True,
                subcalendar_count=0,
                max_subcalendars=self.max_subcalendars
            )
            db.session.add(teamup_calendar)
            
            # สร้าง subcalendars เริ่มต้น
            default_subcalendars = [
                "ฟอกไต", "ตรวจสุขภาพ", "นัดหมายแพทย์", "ฉีดวัคซีน"
            ]
            
            created_subcalendars = []
            for subcal_name in default_subcalendars:
                result = self.create_subcalendar(
                    organization.id, 
                    calendar_id, 
                    subcal_name
                )
                if result['success']:
                    created_subcalendars.append(result['subcalendar'])
            
            db.session.commit()
            
            return {
                'success': True,
                'primary_calendar_id': calendar_id,
                'subcalendars': created_subcalendars
            }
            
        except Exception as e:
            from models import db
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def create_master_calendar(self, organization):
        """สร้าง Master Calendar ใหม่"""
        try:
            from models import TeamUpCalendar
            
            # นับจำนวน calendar ที่มีอยู่
            calendar_count = TeamUpCalendar.query.filter_by(
                organization_id=organization.id
            ).count()
            
            calendar_name = f"{organization.name}"
            if calendar_count > 0:
                calendar_name += f" - Calendar {calendar_count + 1}"
            
            calendar_data = {
                'name': calendar_name,
                'description': f'Appointment calendar for {organization.name}',
                'timezone': 'Asia/Bangkok'
            }
            
            response = requests.post(
                f"{self.base_url}/calendars",
                headers=self.headers,
                json=calendar_data
            )
            
            if response.status_code == 201:
                calendar_info = response.json()['calendar']
                return {
                    'success': True,
                    'calendar_id': calendar_info['id'],
                    'calendar_info': calendar_info
                }
            else:
                return {
                    'success': False,
                    'error': f"TeamUp API Error: {response.text}"
                }
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_available_calendar(self, organization_id):
        """หา calendar ที่ยังไม่เต็ม subcalendars"""
        from models import TeamUpCalendar
        
        available_calendar = TeamUpCalendar.query.filter(
            TeamUpCalendar.organization_id == organization_id,
            TeamUpCalendar.subcalendar_count < TeamUpCalendar.max_subcalendars,
            TeamUpCalendar.is_active == True
        ).first()
        
        return available_calendar
    
    def create_subcalendar(self, organization_id, calendar_id, subcalendar_name):
        """สร้าง subcalendar ใน calendar ที่กำหนด"""
        try:
            from models import db, TeamUpCalendar, OrganizationSubcalendar
            
            # ตรวจสอบว่า calendar นี้เต็มหรือยัง
            teamup_calendar = TeamUpCalendar.query.filter_by(
                organization_id=organization_id,
                calendar_id=calendar_id
            ).first()
            
            if not teamup_calendar:
                return {'success': False, 'error': 'ไม่พบ calendar'}
            
            if teamup_calendar.subcalendar_count >= teamup_calendar.max_subcalendars:
                return {'success': False, 'error': 'calendar เต็มแล้ว'}
            
            # สร้าง subcalendar ใน TeamUp
            subcal_data = {
                'name': subcalendar_name,
                'color': 5,
                'active': True,
                'overlap': True
            }
            
            response = requests.post(
                f"{self.base_url}/{calendar_id}/subcalendars",
                headers=self.headers,
                json=subcal_data
            )
            
            if response.status_code == 201:
                subcal_info = response.json()['subcalendar']
                
                # บันทึกการ mapping
                org_subcal = OrganizationSubcalendar(
                    organization_id=organization_id,
                    calendar_id=calendar_id,
                    subcalendar_id=subcal_info['id'],
                    subcalendar_name=subcalendar_name,
                    is_active=True
                )
                db.session.add(org_subcal)
                
                # อัปเดตจำนวน subcalendar
                teamup_calendar.subcalendar_count += 1
                
                db.session.commit()
                
                return {
                    'success': True,
                    'subcalendar': subcal_info,
                    'calendar_id': calendar_id
                }
            else:
                return {
                    'success': False,
                    'error': f"TeamUp API Error: {response.text}"
                }
                
        except Exception as e:
            from models import db
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def auto_create_subcalendar(self, organization_id, subcalendar_name):
        """อัตโนมัติสร้าง subcalendar (หา calendar ว่างหรือสร้างใหม่)"""
        try:
            from models import db, Organization, TeamUpCalendar
            
            organization = Organization.query.get(organization_id)
            if not organization:
                return {'success': False, 'error': 'ไม่พบ organization'}
            
            # หา calendar ที่ยังไม่เต็ม
            available_calendar = self.get_available_calendar(organization_id)
            
            if available_calendar:
                # ใช้ calendar ที่มีอยู่
                return self.create_subcalendar(
                    organization_id,
                    available_calendar.calendar_id,
                    subcalendar_name
                )
            else:
                # สร้าง calendar ใหม่
                calendar_result = self.create_master_calendar(organization)
                if not calendar_result['success']:
                    return calendar_result
                
                # บันทึก calendar ใหม่
                new_calendar = TeamUpCalendar(
                    organization_id=organization_id,
                    calendar_id=calendar_result['calendar_id'],
                    calendar_name=calendar_result['calendar_info']['name'],
                    is_primary=False,
                    subcalendar_count=0,
                    max_subcalendars=self.max_subcalendars
                )
                db.session.add(new_calendar)
                db.session.commit()
                
                # สร้าง subcalendar ใน calendar ใหม่
                return self.create_subcalendar(
                    organization_id,
                    calendar_result['calendar_id'],
                    subcalendar_name
                )
                
        except Exception as e:
            return {'success': False, 'error': str(e)}

class TeamUpMonitor:
    """Monitor การใช้งาน TeamUp"""
    
    def __init__(self):
        self.manager = HybridTeamUpManager()
    
    def check_calendar_usage(self):
        """ตรวจสอบการใช้งาน calendars"""
        from models import TeamUpCalendar
        
        calendars = TeamUpCalendar.query.filter_by(is_active=True).all()
        
        usage_report = {
            'total_calendars': len(calendars),
            'calendars_near_limit': [],
            'calendars_full': [],
            'total_subcalendars': 0
        }
        
        for calendar in calendars:
            usage_percent = (calendar.subcalendar_count / calendar.max_subcalendars) * 100
            
            usage_report['total_subcalendars'] += calendar.subcalendar_count
            
            if usage_percent >= 100:
                usage_report['calendars_full'].append({
                    'calendar_id': calendar.calendar_id,
                    'organization': calendar.organization.name,
                    'count': calendar.subcalendar_count
                })
            elif usage_percent >= 80:
                usage_report['calendars_near_limit'].append({
                    'calendar_id': calendar.calendar_id,
                    'organization': calendar.organization.name,
                    'usage_percent': usage_percent,
                    'count': calendar.subcalendar_count
                })
        
        return usage_report
    
    def sync_with_teamup(self):
        """ซิงค์ข้อมูลกับ TeamUp (ตรวจสอบความถูกต้อง)"""
        from models import db, TeamUpCalendar
        
        calendars = TeamUpCalendar.query.filter_by(is_active=True).all()
        
        sync_results = []
        
        for calendar in calendars:
            try:
                # ตรวจสอบว่า calendar ยังมีอยู่ใน TeamUp หรือไม่
                response = requests.get(
                    f"{self.manager.base_url}/{calendar.calendar_id}/configuration",
                    headers=self.manager.headers
                )
                
                if response.status_code == 200:
                    # ตรวจสอบ subcalendars
                    subcal_response = requests.get(
                        f"{self.manager.base_url}/{calendar.calendar_id}/subcalendars",
                        headers=self.manager.headers
                    )
                    
                    if subcal_response.status_code == 200:
                        teamup_subcalendars = subcal_response.json().get('subcalendars', [])
                        
                        # อัปเดตจำนวนที่ถูกต้อง
                        calendar.subcalendar_count = len(teamup_subcalendars)
                        sync_results.append({
                            'calendar_id': calendar.calendar_id,
                            'organization': calendar.organization.name,
                            'status': 'synced',
                            'subcalendar_count': len(teamup_subcalendars)
                        })
                
                else:
                    # Calendar ไม่มีใน TeamUp แล้ว
                    sync_results.append({
                        'calendar_id': calendar.calendar_id,
                        'organization': calendar.organization.name,
                        'status': 'calendar_not_found',
                        'action_needed': 'deactivate'
                    })
                    
            except Exception as e:
                sync_results.append({
                    'calendar_id': calendar.calendar_id,
                    'organization': calendar.organization.name,
                    'status': 'error',
                    'error': str(e)
                })
        
        db.session.commit()
        return sync_results

class TeamUpBackup:
    """สำรองข้อมูล TeamUp"""
    
    def __init__(self):
        self.manager = HybridTeamUpManager()
    
    def backup_organization_calendars(self, organization_id):
        """สำรองข้อมูล calendars ของ organization"""
        from models import Organization, TeamUpCalendar
        
        org = Organization.query.get(organization_id)
        if not org:
            return {'success': False, 'error': 'Organization not found'}
        
        backup_data = {
            'organization': {
                'id': org.id,
                'name': org.name,
                'backup_date': datetime.utcnow().isoformat()
            },
            'calendars': [],
            'events': []
        }
        
        # Backup calendars และ subcalendars
        calendars = TeamUpCalendar.query.filter_by(
            organization_id=organization_id,
            is_active=True
        ).all()
        
        for calendar in calendars:
            cal_data = {
                'calendar_id': calendar.calendar_id,
                'calendar_name': calendar.calendar_name,
                'is_primary': calendar.is_primary,
                'subcalendars': []
            }
            backup_data['calendars'].append(cal_data)
        
        return {'success': True, 'data': backup_data}
    
    def save_backup_to_file(self, organization_id, backup_data):
        """บันทึก backup ลงไฟล์"""
        import json
        from pathlib import Path
        
        backup_dir = Path('backups/teamup')
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"org_{organization_id}_{timestamp}.json"
        filepath = backup_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        
        return str(filepath)

# Enhanced API Class
class HybridTeamUpAPI:
    """API สำหรับ Multi-calendar Organization"""
    
    def __init__(self, organization_id, user_id=None):
        self.organization_id = organization_id
        self.user_id = user_id
        self.manager = HybridTeamUpManager()
        
        # Load organization's calendars และ subcalendars (lazy loading)
        self._calendars = None
        self._subcalendars = None
        self._organization = None
    
    @property
    def organization(self):
        if self._organization is None:
            from models import Organization
            self._organization = Organization.query.get(self.organization_id)
        return self._organization
    
    @property
    def calendars(self):
        if self._calendars is None:
            from models import TeamUpCalendar
            self._calendars = TeamUpCalendar.query.filter_by(
                organization_id=self.organization_id,
                is_active=True
            ).all()
        return self._calendars
    
    @property
    def subcalendars(self):
        if self._subcalendars is None:
            from models import OrganizationSubcalendar
            self._subcalendars = OrganizationSubcalendar.query.filter_by(
                organization_id=self.organization_id,
                is_active=True
            ).all()
        return self._subcalendars
    
    def get_subcalendars(self):
        """ดึงรายการ subcalendars ทั้งหมดของ organization"""
        subcal_list = []
        
        for subcal in self.subcalendars:
            subcal_list.append({
                'id': subcal.subcalendar_id,
                'name': subcal.subcalendar_name,
                'calendar_id': subcal.calendar_id,
                'is_active': subcal.is_active
            })
        
        return {'subcalendars': subcal_list}
    
    def create_appointment(self, patient_data):
        """สร้างนัดหมายในระบบ hybrid"""
        try:
            from models import OrganizationSubcalendar
            
            # หา subcalendar จากชื่อ
            subcalendar_name = patient_data['calendar_name']
            subcal_mapping = OrganizationSubcalendar.query.filter_by(
                organization_id=self.organization_id,
                subcalendar_name=subcalendar_name,
                is_active=True
            ).first()
            
            if not subcal_mapping:
                # ถ้าไม่มี subcalendar ให้สร้างใหม่
                create_result = self.manager.auto_create_subcalendar(
                    self.organization_id, 
                    subcalendar_name
                )
                if not create_result['success']:
                    return False, create_result['error']
                
                # Refresh subcalendars
                self._subcalendars = None
                subcal_mapping = OrganizationSubcalendar.query.filter_by(
                    organization_id=self.organization_id,
                    subcalendar_name=subcalendar_name
                ).first()
            
            # สร้าง event ใน calendar ที่ถูกต้อง
            calendar_id = subcal_mapping.calendar_id
            subcalendar_id = subcal_mapping.subcalendar_id
            
            event_data = {
                "title": patient_data['title'],
                "start_dt": f"{patient_data['start_date']}T{patient_data['start_time']}:00",
                "end_dt": f"{patient_data['end_date']}T{patient_data['end_time']}:00",
                "all_day": False,
                "subcalendar_ids": [subcalendar_id]
            }
            
            # เพิ่มข้อมูลเสริม
            for field in ['location', 'who', 'description']:
                if patient_data.get(field):
                    event_data[field if field != 'description' else 'notes'] = patient_data[field]
            
            # ส่งไป TeamUp
            response = requests.post(
                f"{self.manager.base_url}/{calendar_id}/events",
                headers=self.manager.headers,
                json=event_data
            )
            
            if response.status_code == 201:
                event_id = response.json().get('event', {}).get('id')
                
                # บันทึกการใช้งาน
                self.log_usage('create', 'appointment', event_id, {
                    'title': patient_data['title'],
                    'subcalendar': subcalendar_name,
                    'calendar_id': calendar_id
                })
                
                return True, event_id
            else:
                return False, f"TeamUp API Error: {response.text}"
                
        except Exception as e:
            return False, str(e)
    
    def get_events(self, start_date=None, end_date=None, subcalendar_id=None):
        """ดึง events จากทุก calendars ของ organization"""
        all_events = []
        
        try:
            from models import OrganizationSubcalendar
            
            # ถ้าระบุ subcalendar_id ให้หา calendar ที่ถูกต้อง
            if subcalendar_id:
                subcal_mapping = OrganizationSubcalendar.query.filter_by(
                    organization_id=self.organization_id,
                    subcalendar_id=subcalendar_id
                ).first()
                
                if not subcal_mapping:
                    return {"error": "ไม่พบ subcalendar", "events": []}
                
                calendars_to_query = [subcal_mapping.calendar_id]
                subcalendar_filter = [subcalendar_id]
            else:
                # Query ทุก calendars
                calendars_to_query = [cal.calendar_id for cal in self.calendars]
                subcalendar_filter = [sub.subcalendar_id for sub in self.subcalendars]
            
            # Query แต่ละ calendar
            for calendar_id in calendars_to_query:
                events = self.fetch_calendar_events(
                    calendar_id=calendar_id,
                    start_date=start_date,
                    end_date=end_date,
                    subcalendar_ids=subcalendar_filter if not subcalendar_id else [subcalendar_id]
                )
                
                if events.get('events'):
                    # เพิ่มข้อมูล calendar_id ให้แต่ละ event
                    for event in events['events']:
                        event['source_calendar_id'] = calendar_id
                    
                    all_events.extend(events['events'])
            
            return {"events": all_events}
            
        except Exception as e:
            return {"error": str(e), "events": []}
    
    def fetch_calendar_events(self, calendar_id, start_date=None, end_date=None, subcalendar_ids=None):
        """ดึง events จาก calendar เดียว"""
        try:
            params = {}
            
            if start_date:
                params['startDate'] = start_date.strftime('%Y-%m-%d')
            if end_date:
                params['endDate'] = end_date.strftime('%Y-%m-%d')
            
            if subcalendar_ids:
                for i, sid in enumerate(subcalendar_ids):
                    params[f'subcalendarId[{i}]'] = str(sid)
            
            response = requests.get(
                f"{self.manager.base_url}/{calendar_id}/events",
                headers=self.manager.headers,
                params=params
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"API Error: {response.text}", "events": []}
                
        except Exception as e:
            return {"error": str(e), "events": []}
    
    def update_appointment_status(self, event_id, status, calendar_id=None):
        """อัปเดตสถานะนัดหมาย"""
        try:
            # ถ้าไม่ระบุ calendar_id ให้หาจากทุก calendars
            if not calendar_id:
                for cal in self.calendars:
                    result = self._update_event_in_calendar(cal.calendar_id, event_id, status)
                    if result[0]:  # success
                        return result
                return False, "ไม่พบนัดหมายที่ระบุ"
            else:
                return self._update_event_in_calendar(calendar_id, event_id, status)
                
        except Exception as e:
            return False, str(e)
    
    def _update_event_in_calendar(self, calendar_id, event_id, status):
        """อัปเดต event ใน calendar ที่ระบุ"""
        try:
            # ดึงข้อมูล event ปัจจุบัน
            response = requests.get(
                f"{self.manager.base_url}/{calendar_id}/events/{event_id}",
                headers=self.manager.headers
            )
            
            if response.status_code != 200:
                return False, f"ไม่พบนัดหมาย: {response.text}"
            
            event_data = response.json()['event']
            
            # อัปเดตสถานะในฟิลด์ notes หรือ custom field
            notes = event_data.get('notes', '')
            
            # ลบสถานะเก่า
            import re
            notes = re.sub(r'สถานะ: [^\n]*\n?', '', notes)
            
            # เพิ่มสถานะใหม่
            status_text = f"สถานะ: {status}"
            if notes:
                notes = f"{notes}\n{status_text}"
            else:
                notes = status_text
            
            # อัปเดต event
            update_data = {
                'notes': notes
            }
            
            update_response = requests.put(
                f"{self.manager.base_url}/{calendar_id}/events/{event_id}",
                headers=self.manager.headers,
                json=update_data
            )
            
            if update_response.status_code == 200:
                self.log_usage('update', 'appointment', event_id, {
                    'status': status,
                    'calendar_id': calendar_id
                })
                return True, "อัปเดตสถานะสำเร็จ"
            else:
                return False, f"อัปเดตล้มเหลว: {update_response.text}"
                
        except Exception as e:
            return False, str(e)
    
    def create_recurring_appointments_simple(self, patient_data, selected_days, weeks):
        """สร้างนัดหมายเกิดซ้ำแบบง่าย"""
        try:
            from datetime import datetime, timedelta
            
            created_events = []
            start_date = datetime.strptime(patient_data['start_date'], '%Y-%m-%d')
            
            # Day mapping
            day_map = {
                'MO': 0, 'TU': 1, 'WE': 2, 'TH': 3, 'FR': 4, 'SA': 5, 'SU': 6
            }
            
            selected_weekdays = [day_map[day] for day in selected_days]
            
            for week in range(weeks):
                for weekday in selected_weekdays:
                    # คำนวณวันที่
                    days_ahead = weekday - start_date.weekday()
                    if days_ahead < 0:  # วันที่ผ่านไปแล้วในสัปดาห์นี้
                        days_ahead += 7
                    
                    event_date = start_date + timedelta(days=days_ahead + (week * 7))
                    
                    # สร้างข้อมูลนัดหมาย
                    recurring_data = patient_data.copy()
                    recurring_data['start_date'] = event_date.strftime('%Y-%m-%d')
                    recurring_data['end_date'] = event_date.strftime('%Y-%m-%d')
                    
                    # สร้างนัดหมาย
                    success, result = self.create_appointment(recurring_data)
                    if success:
                        created_events.append(result)
                    else:
                        # Log error but continue
                        print(f"Failed to create appointment on {event_date}: {result}")
            
            if created_events:
                return True, f"สร้างนัดหมายเกิดซ้ำสำเร็จ {len(created_events)} รายการ"
            else:
                return False, "ไม่สามารถสร้างนัดหมายเกิดซ้ำได้"
                
        except Exception as e:
            return False, str(e)
    
    def get_organization_stats(self):
        """ดึงสถิติการใช้งานของ organization"""
        try:
            from models import UsageStat, AuditLog
            from datetime import datetime, timedelta
            
            # สถิติการใช้งานเดือนนี้
            current_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            monthly_stats = UsageStat.query.filter(
                UsageStat.organization_id == self.organization_id,
                UsageStat.date >= current_month
            ).all()
            
            total_appointments = sum(stat.appointments_created for stat in monthly_stats)
            total_updates = sum(stat.appointments_updated for stat in monthly_stats)
            
            # Active calendars และ subcalendars
            active_calendars = len(self.calendars)
            active_subcalendars = len(self.subcalendars)
            
            # Recent activities
            recent_activities = AuditLog.query.filter_by(
                organization_id=self.organization_id
            ).order_by(AuditLog.created_at.desc()).limit(10).all()
            
            return {
                'monthly_appointments': total_appointments,
                'monthly_updates': total_updates,
                'active_calendars': active_calendars,
                'active_subcalendars': active_subcalendars,
                'recent_activities': [
                    {
                        'action': activity.action,
                        'resource_type': activity.resource_type,
                        'created_at': activity.created_at.isoformat(),
                        'details': activity.details
                    } for activity in recent_activities
                ]
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'monthly_appointments': 0,
                'monthly_updates': 0,
                'active_calendars': 0,
                'active_subcalendars': 0,
                'recent_activities': []
            }
    
    def log_usage(self, action, resource_type, resource_id=None, details=None):
        """บันทึกการใช้งาน"""
        try:
            from models import db, AuditLog, UsageStat
            from datetime import datetime
            
            # บันทึก Audit Log
            audit_log = AuditLog(
                organization_id=self.organization_id,
                user_id=self.user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details
            )
            db.session.add(audit_log)
            
            # อัปเดต Usage Stats
            today = datetime.now().date()
            usage_stat = UsageStat.query.filter_by(
                organization_id=self.organization_id,
                date=today
            ).first()
            
            if not usage_stat:
                usage_stat = UsageStat(
                    organization_id=self.organization_id,
                    date=today
                )
                db.session.add(usage_stat)
            
            if action == 'create' and resource_type == 'appointment':
                usage_stat.appointments_created += 1
            elif action == 'update' and resource_type == 'appointment':
                usage_stat.appointments_updated += 1
            
            db.session.commit()
            
        except Exception as e:
            print(f"Error logging usage: {e}")

# Factory function
def get_hybrid_teamup_api(organization_id, user_id=None):
    """Factory function สำหรับสร้าง HybridTeamUpAPI instance"""
    return HybridTeamUpAPI(organization_id, user_id)