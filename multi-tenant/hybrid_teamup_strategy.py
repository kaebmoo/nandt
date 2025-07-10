# hybrid_teamup_strategy.py - Complete Updated Version
"""
Hybrid TeamUp Strategy:
1. แต่ละ Organization = 1 Master Calendar (copied from template)
2. ใน 1 Master Calendar มีหลาย Subcalendars (จำกัดตาม TeamUp plan)
3. ถ้า subcalendars เต็มแล้ว สร้าง Master Calendar ใหม่
"""

import requests
import json
from datetime import datetime, timedelta
import os
import uuid
import re

# Import Config to get TEMPLATE_CALENDAR_KEY
from config import Config

class HybridTeamUpManager:
    """จัดการ TeamUp Calendars แบบ Hybrid"""
    
    def __init__(self):
        self.master_api_key = Config.MASTER_TEAMUP_API
        self.template_calendar_key = Config.TEMPLATE_CALENDAR_KEY
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
        
        self.teamup_plan = Config.TEAMUP_PLAN
        self.max_subcalendars = self.subcalendar_limits[self.teamup_plan]
        
        print(f"HybridTeamUpManager initialized:")
        print(f"  - Master API Key: {'***' if self.master_api_key else 'None'}")
        print(f"  - Template Calendar: {self.template_calendar_key}")
        print(f"  - Plan: {self.teamup_plan} (max {self.max_subcalendars} subcalendars)")
    
    def create_organization_setup(self, organization):
        """สร้าง TeamUp setup สำหรับ organization ใหม่"""
        try:
            from models import db, TeamUpCalendar, OrganizationSubcalendar
            
            print(f"Creating TeamUp setup for organization: {organization.name}")
            
            # ตรวจสอบว่า template calendar key ถูกต้องหรือไม่
            if not self.template_calendar_key:
                return {
                    'success': False, 
                    'error': 'TEMPLATE_CALENDAR_KEY is not configured. Please set it in .env file.'
                }
            
            # ทดสอบการเข้าถึง template calendar ก่อน
            test_result = self._test_template_access()
            if not test_result['success']:
                return test_result
            
            # สร้าง Master Calendar แรกโดยใช้ Template
            calendar_result = self.create_master_calendar(organization)
            if not calendar_result['success']:
                return calendar_result
            
            calendar_id = calendar_result['calendar_id']
            
            # บันทึก Master Calendar
            teamup_calendar = TeamUpCalendar(
                organization_id=organization.id,
                calendar_id=calendar_id,
                calendar_name=calendar_result['calendar_name'],
                is_primary=True,
                subcalendar_count=0,
                max_subcalendars=self.max_subcalendars
            )
            db.session.add(teamup_calendar)
            db.session.flush()
            
            # ดึงข้อมูล subcalendars เริ่มต้นจากปฏิทินที่เพิ่งคัดลอกมา
            initial_subcals_data = self._get_subcalendars_from_teamup(calendar_id)
            created_subcalendars = []
            
            for subcal_info in initial_subcals_data.get('subcalendars', []):
                org_subcal = OrganizationSubcalendar(
                    organization_id=organization.id,
                    calendar_id=calendar_id,
                    subcalendar_id=subcal_info['id'],
                    subcalendar_name=subcal_info['name'],
                    is_active=subcal_info.get('active', True)
                )
                db.session.add(org_subcal)
                created_subcalendars.append(subcal_info)
            
            teamup_calendar.subcalendar_count = len(created_subcalendars)
            db.session.commit()
            
            print(f"✅ TeamUp setup created successfully:")
            print(f"  - Calendar ID: {calendar_id}")
            print(f"  - Subcalendars: {len(created_subcalendars)}")
            
            return {
                'success': True,
                'primary_calendar_id': calendar_id,
                'subcalendars': created_subcalendars
            }
            
        except Exception as e:
            from models import db
            db.session.rollback()
            print(f"❌ TeamUp setup failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': f"Manager setup failed: {str(e)}"}
    
    def _test_template_access(self):
        """ทดสอบการเข้าถึง template calendar"""
        try:
            print(f"Testing access to template calendar: {self.template_calendar_key}")
            
            # ทดสอบด้วยการดึงข้อมูล configuration
            response = requests.get(
                f"{self.base_url}/{self.template_calendar_key}/configuration",
                headers=self.headers,
                timeout=10
            )
            
            print(f"Template access test - Status: {response.status_code}")
            
            if response.status_code == 200:
                config_data = response.json()
                print(f"✅ Template calendar accessible: {config_data.get('name', 'Unknown')}")
                return {'success': True}
            elif response.status_code == 403:
                return {
                    'success': False,
                    'error': 'No permission to access template calendar. Please check MASTER_TEAMUP_API permissions.'
                }
            elif response.status_code == 404:
                return {
                    'success': False,
                    'error': 'Template calendar not found. Please check TEMPLATE_CALENDAR_KEY.'
                }
            else:
                return {
                    'success': False,
                    'error': f'Cannot access template calendar. HTTP {response.status_code}: {response.text}'
                }
                
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': 'Timeout accessing TeamUp API. Please check your internet connection.'
            }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': 'Cannot connect to TeamUp API. Please check your internet connection.'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error testing template access: {str(e)}'
            }
    
    def create_master_calendar(self, organization):
        """สร้าง Master Calendar ใหม่โดยการคัดลอกจาก Template Calendar"""
        try:
            print(f"Creating master calendar for: {organization.name}")
            
            # ชื่อปฏิทินใหม่
            calendar_name = f"{organization.name} - Main Calendar"
            
            # เรียก API copy calendar
            copy_data = {
                'title': calendar_name,
                'copySubcalendars': True,  # คัดลอก subcalendars ด้วย
                'copyEvents': False       # ไม่คัดลอก events
            }
            
            print(f"Copying template calendar with data: {copy_data}")
            
            response = requests.post(
                f"{self.base_url}/{self.template_calendar_key}/copy",
                headers=self.headers,
                json=copy_data,  # ใช้ json แทน params
                allow_redirects=False,
                timeout=30
            )
            
            print(f"Copy calendar response - Status: {response.status_code}")
            print(f"Copy calendar response - Headers: {dict(response.headers)}")
            print(f"Copy calendar response - Text: {response.text[:500]}")
            
            if response.status_code == 302:
                # Success - ดึง calendar ID จาก Location header
                redirect_url = response.headers.get('Location')
                if redirect_url:
                    # ดึง calendarKey จาก URL
                    match = re.search(r'https?://(?:www\.)?teamup\.com/(ks[a-zA-Z0-9]+)', redirect_url)
                    if match:
                        new_calendar_id = match.group(1)
                        print(f"✅ New calendar created: {new_calendar_id}")
                        
                        # ตรวจสอบว่า calendar ถูกสร้างจริงหรือไม่
                        if self._verify_calendar_creation(new_calendar_id):
                            return {
                                'success': True,
                                'calendar_id': new_calendar_id,
                                'calendar_name': calendar_name
                            }
                        else:
                            return {
                                'success': False,
                                'error': 'Calendar was created but cannot be accessed. Please check permissions.'
                            }
                    else:
                        return {
                            'success': False,
                            'error': f"Cannot parse calendar ID from redirect URL: {redirect_url}"
                        }
                else:
                    return {
                        'success': False,
                        'error': "No Location header in redirect response"
                    }
            elif response.status_code == 200:
                # Alternative response format - check if calendar ID is in response body
                try:
                    response_data = response.json()
                    if 'calendar' in response_data and 'id' in response_data['calendar']:
                        new_calendar_id = response_data['calendar']['id']
                        print(f"✅ New calendar created (from body): {new_calendar_id}")
                        return {
                            'success': True,
                            'calendar_id': new_calendar_id,
                            'calendar_name': calendar_name
                        }
                except json.JSONDecodeError:
                    pass
                
                return {
                    'success': False,
                    'error': f"Unexpected success response format: {response.text}"
                }
            else:
                # Error response
                error_msg = response.text
                try:
                    error_json = response.json()
                    if 'error' in error_json:
                        if isinstance(error_json['error'], dict) and 'message' in error_json['error']:
                            error_msg = error_json['error']['message']
                        elif isinstance(error_json['error'], str):
                            error_msg = error_json['error']
                except json.JSONDecodeError:
                    pass
                
                # Provide specific error messages for common issues
                if response.status_code == 403:
                    error_msg = "No permission to copy calendar. Please ensure MASTER_TEAMUP_API has admin access to the template calendar."
                elif response.status_code == 404:
                    error_msg = "Template calendar not found. Please check TEMPLATE_CALENDAR_KEY."
                elif response.status_code == 400:
                    error_msg = f"Invalid request: {error_msg}"
                
                return {
                    'success': False,
                    'error': f"TeamUp API Error (Status {response.status_code}): {error_msg}"
                }
                
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': 'Request timeout. TeamUp API may be slow or unavailable.'
            }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': 'Connection error. Please check your internet connection.'
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': f"Exception during calendar creation: {str(e)}"
            }
    
    def _verify_calendar_creation(self, calendar_id):
        """ตรวจสอบว่า calendar ถูกสร้างและเข้าถึงได้จริง"""
        try:
            print(f"Verifying calendar creation: {calendar_id}")
            
            response = requests.get(
                f"{self.base_url}/{calendar_id}/configuration",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                config_data = response.json()
                print(f"✅ Calendar verified: {config_data.get('name', 'Unknown')}")
                return True
            else:
                print(f"❌ Calendar verification failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Calendar verification error: {str(e)}")
            return False

    def _get_subcalendars_from_teamup(self, calendar_id):
        """ดึงรายการ subcalendars จาก TeamUp API ของ calendar ที่ระบุ"""
        try:
            print(f"Fetching subcalendars for calendar: {calendar_id}")
            
            response = requests.get(
                f"{self.base_url}/{calendar_id}/subcalendars",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                subcalendars = data.get('subcalendars', [])
                print(f"✅ Found {len(subcalendars)} subcalendars")
                return data
            else:
                print(f"❌ Failed to fetch subcalendars: {response.status_code} - {response.text}")
                return {'subcalendars': []}
                
        except Exception as e:
            print(f"❌ Error fetching subcalendars: {str(e)}")
            return {'subcalendars': []}

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
                return {'success': False, 'error': 'ไม่พบ calendar ในระบบ'}
            
            if teamup_calendar.subcalendar_count >= teamup_calendar.max_subcalendars:
                return {'success': False, 'error': 'Calendar เต็มแล้ว'}
            
            # สร้าง subcalendar ใน TeamUp
            subcal_data = {
                'name': subcalendar_name,
                'color': 5,
                'active': True,
                'overlap': True
            }
            
            print(f"Creating subcalendar '{subcalendar_name}' in calendar {calendar_id}")
            
            response = requests.post(
                f"{self.base_url}/{calendar_id}/subcalendars",
                headers=self.headers,
                json=subcal_data,
                timeout=15
            )
            
            print(f"Create subcalendar response: {response.status_code} - {response.text}")

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
                
                print(f"✅ Subcalendar created successfully: {subcal_info['id']}")
                
                return {
                    'success': True,
                    'subcalendar': subcal_info,
                    'calendar_id': calendar_id
                }
            else:
                error_msg = response.text
                try:
                    error_json = response.json()
                    if 'error' in error_json and 'message' in error_json['error']:
                        error_msg = error_json['error']['message']
                except json.JSONDecodeError:
                    pass
                
                return {
                    'success': False,
                    'error': f"TeamUp API Error (Status {response.status_code}): {error_msg}"
                }
                
        except Exception as e:
            from models import db
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': f"Exception during subcalendar creation: {str(e)}"}
    
    def auto_create_subcalendar(self, organization_id, subcalendar_name):
        """อัตโนมัติสร้าง subcalendar (หา calendar ว่างหรือสร้างใหม่)"""
        try:
            from models import db, Organization, TeamUpCalendar
            
            organization = Organization.query.get(organization_id)
            if not organization:
                return {'success': False, 'error': 'ไม่พบ organization'}
            
            print(f"Auto-creating subcalendar '{subcalendar_name}' for {organization.name}")
            
            # หา calendar ที่ยังไม่เต็ม
            available_calendar = self.get_available_calendar(organization_id)
            
            if available_calendar:
                print(f"Using existing calendar: {available_calendar.calendar_id}")
                return self.create_subcalendar(
                    organization_id,
                    available_calendar.calendar_id,
                    subcalendar_name
                )
            else:
                print("No available calendar found. Creating new master calendar.")
                calendar_result = self.create_master_calendar(organization)
                if not calendar_result['success']:
                    return calendar_result
                
                # บันทึก calendar ใหม่
                new_calendar = TeamUpCalendar(
                    organization_id=organization_id,
                    calendar_id=calendar_result['calendar_id'],
                    calendar_name=calendar_result['calendar_name'],
                    is_primary=False,
                    subcalendar_count=0,
                    max_subcalendars=self.max_subcalendars
                )
                db.session.add(new_calendar)
                db.session.commit()
                
                print(f"New master calendar created: {new_calendar.calendar_id}")
                
                # สร้าง subcalendar ใน calendar ใหม่
                return self.create_subcalendar(
                    organization_id,
                    new_calendar.calendar_id,
                    subcalendar_name
                )
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': f"Exception in auto_create_subcalendar: {str(e)}"}

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
        from models import db, TeamUpCalendar, OrganizationSubcalendar
        
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
                        teamup_subcalendars_data = subcal_response.json().get('subcalendars', [])
                        
                        # อัปเดตจำนวนที่ถูกต้อง
                        calendar.subcalendar_count = len(teamup_subcalendars_data)
                        
                        # Sync subcalendar mappings
                        teamup_subcal_ids = {sub['id'] for sub in teamup_subcalendars_data}
                        
                        db_subcals = OrganizationSubcalendar.query.filter_by(
                            calendar_id=calendar.calendar_id
                        ).all()
                        db_subcal_ids = {sub.subcalendar_id for sub in db_subcals}
                        
                        # เพิ่ม subcalendar ที่ TeamUp มีแต่เราไม่มี
                        for sub_info in teamup_subcalendars_data:
                            if sub_info['id'] not in db_subcal_ids:
                                new_org_subcal = OrganizationSubcalendar(
                                    organization_id=calendar.organization_id,
                                    calendar_id=calendar.calendar_id,
                                    subcalendar_id=sub_info['id'],
                                    subcalendar_name=sub_info['name'],
                                    is_active=sub_info.get('active', True)
                                )
                                db.session.add(new_org_subcal)
                                print(f"Added new subcalendar {sub_info['name']} to DB for {calendar.calendar_name}")
                        
                        # ลบ subcalendar ที่เรามีแต่ TeamUp ไม่มี
                        for db_subcal in db_subcals:
                            if db_subcal.subcalendar_id not in teamup_subcal_ids:
                                db.session.delete(db_subcal)
                                print(f"Removed subcalendar {db_subcal.subcalendar_name} from DB for {calendar.calendar_name}")
                        
                        sync_results.append({
                            'calendar_id': calendar.calendar_id,
                            'organization': calendar.organization.name,
                            'status': 'synced',
                            'subcalendar_count': len(teamup_subcalendars_data)
                        })
                
                else:
                    # Calendar ไม่มีใน TeamUp แล้ว
                    calendar.is_active = False
                    sync_results.append({
                        'calendar_id': calendar.calendar_id,
                        'organization': calendar.organization.name,
                        'status': 'calendar_not_found_or_permission_error',
                        'action_needed': 'deactivated in DB',
                        'error_detail': response.text
                    })
                    
            except Exception as e:
                import traceback
                traceback.print_exc()
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

            # ดึง subcalendars จาก TeamUp API
            subcal_response = requests.get(
                f"{self.manager.base_url}/{calendar.calendar_id}/subcalendars",
                headers=self.manager.headers
            )
            if subcal_response.status_code == 200:
                subcals_on_teamup = subcal_response.json().get('subcalendars', [])
                cal_data['subcalendars'].extend(subcals_on_teamup)
            else:
                print(f"Warning: Could not fetch subcalendars for backup of {calendar.calendar_id}: {subcal_response.text}")
            
            # ดึง events ทั้งหมดในช่วง 1 ปีที่ผ่านมา
            end_date = datetime.now() + timedelta(days=30)
            start_date = datetime.now() - timedelta(days=365)
            
            try:
                events_response = requests.get(
                    f"{self.manager.base_url}/{calendar.calendar_id}/events",
                    headers=self.manager.headers,
                    params={
                        'startDate': start_date.strftime('%Y-%m-%d'),
                        'endDate': end_date.strftime('%Y-%m-%d')
                    }
                )
                if events_response.status_code == 200:
                    events_data = events_response.json().get('events', [])
                    backup_data['events'].extend([{'calendar_id': calendar.calendar_id, 'event': event} for event in events_data])
                else:
                    print(f"Warning: Could not fetch events for backup of {calendar.calendar_id}: {events_response.text}")
            except Exception as e:
                print(f"Error fetching events for backup of {calendar.calendar_id}: {e}")

        return {'success': True, 'data': backup_data}
    
    def save_backup_to_file(self, organization_id, backup_data):
        """บันทึก backup ลงไฟล์"""
        import json
        from pathlib import Path
        
        backup_dir = Path(Config.BACKUP_STORAGE_PATH) / "teamup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"org_{organization_id}_{timestamp}.json"
        filepath = backup_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        
        return str(filepath)

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
                print(f"Subcalendar '{subcalendar_name}' not found for org {self.organization_id}. Attempting to auto-create.")
                create_result = self.manager.auto_create_subcalendar(
                    self.organization_id, 
                    subcalendar_name
                )
                if not create_result['success']:
                    print(f"Failed to auto-create subcalendar: {create_result['error']}")
                    return False, create_result['error']
                
                # Refresh subcalendars property
                self._subcalendars = None 
                subcal_mapping = OrganizationSubcalendar.query.filter_by(
                    organization_id=self.organization_id,
                    subcalendar_name=subcalendar_name,
                    is_active=True
                ).first()
                if not subcal_mapping:
                    return False, f"Failed to retrieve newly created subcalendar mapping for {subcalendar_name}"
            
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
            
            print(f"Creating event in calendar {calendar_id} with subcalendar {subcalendar_id}")
            
            # ส่งไป TeamUp
            response = requests.post(
                f"{self.manager.base_url}/{calendar_id}/events",
                headers=self.manager.headers,
                json=event_data,
                timeout=15
            )
            
            print(f"Event creation response: {response.status_code} - {response.text}")

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
                error_msg = response.text
                try:
                    error_json = response.json()
                    if 'error' in error_json and 'message' in error_json['error']:
                        error_msg = error_json['error']['message']
                except json.JSONDecodeError:
                    pass
                return False, f"TeamUp API Error (Status {response.status_code}): {error_msg}"
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Exception during appointment creation: {str(e)}"
    
    def get_events(self, start_date=None, end_date=None, subcalendar_id=None, event_id=None):
        """ดึง events จากทุก calendars ของ organization หรือเฉพาะ event_id"""
        all_events = []
        
        try:
            from models import OrganizationSubcalendar
            
            # Handle fetching a specific event by event_id
            if event_id:
                for cal in self.calendars:
                    try:
                        single_event_response = requests.get(
                            f"{self.manager.base_url}/{cal.calendar_id}/events/{event_id}",
                            headers=self.manager.headers
                        )
                        if single_event_response.status_code == 200:
                            found_event = single_event_response.json().get('event')
                            if found_event:
                                found_event['source_calendar_id'] = cal.calendar_id
                                return {"events": [found_event]}
                    except Exception as e:
                        print(f"Error checking calendar {cal.calendar_id} for event {event_id}: {e}")
                return {"error": "Event not found across calendars", "events": []}
            
            # Date/subcalendar filtering
            subcalendar_filter_ids = []
            calendars_to_query_keys = []
            
            if subcalendar_id:
                subcal_mapping = OrganizationSubcalendar.query.filter_by(
                    organization_id=self.organization_id,
                    subcalendar_id=subcalendar_id,
                    is_active=True
                ).first()
                
                if not subcal_mapping:
                    return {"error": "ไม่พบ subcalendar ที่ระบุ", "events": []}
                
                calendars_to_query_keys = [subcal_mapping.calendar_id]
                subcalendar_filter_ids = [subcal_mapping.subcalendar_id]
            else:
                calendars_to_query_keys = [cal.calendar_id for cal in self.calendars]
                subcalendar_filter_ids = [sub.subcalendar_id for sub in self.subcalendars]
            
            # Ensure dates are valid
            if not isinstance(start_date, datetime):
                start_date = datetime.strptime(start_date, '%Y-%m-%d') if isinstance(start_date, str) else datetime.now() - timedelta(days=7)
            if not isinstance(end_date, datetime):
                end_date = datetime.strptime(end_date, '%Y-%m-%d') if isinstance(end_date, str) else datetime.now() + timedelta(days=30)
            
            # Query each calendar
            for calendar_id_key in calendars_to_query_keys:
                events = self.fetch_calendar_events(
                    calendar_id=calendar_id_key,
                    start_date=start_date,
                    end_date=end_date,
                    subcalendar_ids=subcalendar_filter_ids
                )
                
                if events.get('events'):
                    for event in events['events']:
                        event['source_calendar_id'] = calendar_id_key
                        # เพิ่มชื่อ subcalendar
                        if 'subcalendar_ids' in event and event['subcalendar_ids']:
                            subcal_names = []
                            for sid in event['subcalendar_ids']:
                                mapped_subcal = next((s for s in self.subcalendars if s.subcalendar_id == sid and s.calendar_id == calendar_id_key), None)
                                if mapped_subcal:
                                    subcal_names.append(mapped_subcal.subcalendar_name)
                            event['subcalendar_names'] = subcal_names
                            event['subcalendar_display'] = ', '.join(subcal_names) if subcal_names else 'ไม่ระบุ'
                        else:
                            event['subcalendar_names'] = []
                            event['subcalendar_display'] = 'ไม่ระบุ'
                        
                    all_events.extend(events['events'])
            
            return {"events": all_events}
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"Exception in get_events: {str(e)}", "events": []}
    
    def fetch_calendar_events(self, calendar_id, start_date=None, end_date=None, subcalendar_ids=None):
        """ดึง events จาก calendar เดียว"""
        try:
            params = {}
            
            if start_date:
                params['startDate'] = start_date.strftime('%Y-%m-%d')
            if end_date:
                params['endDate'] = end_date.strftime('%Y-%m-%d')
            
            if subcalendar_ids:
                params['subcalendarId'] = [str(sid) for sid in subcalendar_ids]
            
            response = requests.get(
                f"{self.manager.base_url}/{calendar_id}/events",
                headers=self.manager.headers,
                params=params,
                timeout=15
            )

            if response.status_code == 200:
                return response.json()
            else:
                error_msg = response.text
                try:
                    error_json = response.json()
                    if 'error' in error_json and 'message' in error_json['error']:
                        error_msg = error_json['error']['message']
                except json.JSONDecodeError:
                    pass
                print(f"TeamUp API Error fetching events from {calendar_id} (Status: {response.status_code}): {error_msg}")
                return {"error": f"API Error: {error_msg}", "events": []}
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Exception fetching events from {calendar_id}: {e}")
            return {"error": str(e), "events": []}
    
    def update_appointment_status(self, event_id, status, calendar_id=None):
        """อัปเดตสถานะนัดหมาย"""
        try:
            target_calendar_id = None
            if calendar_id:
                target_calendar_id = calendar_id
            else:
                # หาจากทุก calendars
                for cal in self.calendars:
                    events_response = self.fetch_calendar_events(
                        calendar_id=cal.calendar_id,
                        start_date=datetime.now() - timedelta(days=30),
                        end_date=datetime.now() + timedelta(days=30),
                    )
                    found_event_data = next((e for e in events_response.get('events', []) if e.get('id') == event_id), None)
                    if found_event_data:
                        target_calendar_id = cal.calendar_id
                        break
                
                if not target_calendar_id:
                    return False, "ไม่พบนัดหมายที่ระบุใน calendars ขององค์กร"

            return self._update_event_in_calendar(target_calendar_id, event_id, status)
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Exception in update_appointment_status: {str(e)}"
    
    def _update_event_in_calendar(self, calendar_id, event_id, status):
        """อัปเดต event ใน calendar ที่ระบุ"""
        try:
            # ดึงข้อมูล event ปัจจุบัน
            response = requests.get(
                f"{self.manager.base_url}/{calendar_id}/events/{event_id}",
                headers=self.manager.headers
            )

            if response.status_code != 200:
                error_msg = response.text
                try:
                    error_json = response.json()
                    if 'error' in error_json and 'message' in error_json['error']:
                        error_msg = error_json['error']['message']
                except json.JSONDecodeError:
                    pass
                return False, f"ไม่พบนัดหมาย หรือไม่สามารถดึงข้อมูลได้: {error_msg}"
            
            event_data = response.json()['event']
            current_title = event_data.get('title', '')
            current_notes = event_data.get('notes', '')
            current_version = event_data.get('version')
            
            # อัปเดต notes ด้วยสถานะใหม่
            updated_notes = re.sub(r'\s*\[สถานะ:.*?\]\s*', '', current_notes)
            new_status_tag = f" [สถานะ: {status}]"
            
            if updated_notes:
                if updated_notes.endswith('.'):
                    updated_notes = updated_notes[:-1] + new_status_tag + "."
                else:
                    updated_notes += new_status_tag
            else:
                updated_notes = new_status_tag.strip()
            
            # สร้างข้อมูลสำหรับการอัปเดต
            update_data = {
                'title': current_title,
                'notes': updated_notes,
                'start_dt': event_data['start_dt'],
                'end_dt': event_data['end_dt'],
                'all_day': event_data.get('all_day', False),
                'signup_enabled': event_data.get('signup_enabled', False),
                'comments_enabled': event_data.get('comments_enabled', False),
                'attachments': event_data.get('attachments', []),
            }
            
            if current_version:
                update_data['version'] = current_version

            # เพิ่มฟิลด์ที่จำเป็นอื่นๆ
            for field in ['location', 'who', 'rrule', 'subcalendar_ids', 'subcalendar_remote_ids']:
                if field in event_data:
                    update_data[field] = event_data[field]
            
            update_response = requests.put(
                f"{self.manager.base_url}/{calendar_id}/events/{event_id}",
                headers=self.manager.headers,
                json=update_data,
                timeout=15
            )
            
            if update_response.status_code == 200:
                self.log_usage('update', 'appointment', event_id, {
                    'status': status,
                    'calendar_id': calendar_id
                })
                return True, "อัปเดตสถานะสำเร็จ"
            else:
                error_msg = update_response.text
                try:
                    error_json = update_response.json()
                    if 'error' in error_json and 'message' in error_json['error']:
                        error_msg = error_json['error']['message']
                except json.JSONDecodeError:
                    pass
                return False, f"อัปเดตสถานะล้มเหลว: {error_msg}"
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Exception during event status update: {str(e)}"
    
    def create_recurring_appointments_simple(self, patient_data, selected_days, weeks):
        """สร้างนัดหมายเกิดซ้ำแบบง่ายโดยใช้ TeamUp RRULE"""
        try:
            from models import OrganizationSubcalendar
            
            subcalendar_name = patient_data['calendar_name']
            subcal_mapping = OrganizationSubcalendar.query.filter_by(
                organization_id=self.organization_id,
                subcalendar_name=subcalendar_name,
                is_active=True
            ).first()
            
            if not subcal_mapping:
                create_result = self.manager.auto_create_subcalendar(
                    self.organization_id, 
                    subcalendar_name
                )
                if not create_result['success']:
                    return False, create_result['error']
                
                self._subcalendars = None 
                subcal_mapping = OrganizationSubcalendar.query.filter_by(
                    organization_id=self.organization_id,
                    subcalendar_name=subcalendar_name,
                    is_active=True
                ).first()
                if not subcal_mapping:
                    return False, f"Failed to retrieve newly created subcalendar mapping for {subcalendar_name}"
            
            calendar_id = subcal_mapping.calendar_id
            subcalendar_id = subcal_mapping.subcalendar_id
            
            # สร้าง RRULE string
            if not selected_days:
                return False, "กรุณาเลือกอย่างน้อยหนึ่งวันสำหรับนัดหมายที่เกิดซ้ำ"

            rrule = f"FREQ=WEEKLY;BYDAY={','.join(selected_days)};COUNT={weeks}"
            
            event_data = {
                "title": patient_data['title'],
                "start_dt": f"{patient_data['start_date']}T{patient_data['start_time']}:00",
                "end_dt": f"{patient_data['end_date']}T{patient_data['end_time']}:00",
                "all_day": False,
                "rrule": rrule,
                "subcalendar_ids": [subcalendar_id]
            }
            
            # เพิ่มข้อมูลเสริม
            for field in ['location', 'who', 'description']:
                if patient_data.get(field):
                    event_data[field if field != 'description' else 'notes'] = patient_data[field]

            response = requests.post(
                f"{self.manager.base_url}/{calendar_id}/events",
                headers=self.manager.headers,
                json=event_data,
                timeout=15
            )
            
            if response.status_code == 201:
                event_id = response.json().get('event', {}).get('id')
                self.log_usage('create', 'recurring_appointment', event_id, {
                    'title': patient_data['title'],
                    'rrule': rrule,
                    'calendar_id': calendar_id
                })
                return True, event_id
            else:
                error_msg = response.text
                try:
                    error_json = response.json()
                    if 'error' in error_json and 'message' in error_json['error']:
                        error_msg = error_json['error']['message']
                except json.JSONDecodeError:
                    pass
                return False, f"TeamUp API Error (Status {response.status_code}): {error_msg}"
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Exception during recurring appointment creation: {str(e)}"
    
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
            import traceback
            traceback.print_exc()
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
            
            if action == 'create' and ('appointment' in resource_type):
                usage_stat.appointments_created += 1
            elif action == 'update' and resource_type == 'appointment':
                usage_stat.appointments_updated += 1
            
            db.session.commit()
            
        except Exception as e:
            print(f"Error logging usage: {e}")
            import traceback
            traceback.print_exc()

# Factory function
def get_hybrid_teamup_api(organization_id, user_id=None):
    """Factory function สำหรับสร้าง HybridTeamUpAPI instance"""
    return HybridTeamUpAPI(organization_id, user_id)