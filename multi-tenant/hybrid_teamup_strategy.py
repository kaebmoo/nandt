# hybrid_teamup_strategy.py - Complete Updated Version for ks-key retrieval
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
import time
from datetime import timezone

from config import Config

class HybridTeamUpManager:
    """จัดการ TeamUp Calendars แบบ Hybrid"""
    
    def __init__(self):
        self.master_api_key = Config.MASTER_TEAMUP_API
        self.template_calendar_key = Config.TEMPLATE_CALENDAR_KEY # This is a ks-key
        self.base_url = "https://api.teamup.com"
        
        self.admin_email = Config.TEAMUP_ADMIN_EMAIL
        self.admin_password = Config.TEAMUP_ADMIN_PASSWORD
        self.app_name = Config.TEAMUP_APP_NAME
        self.device_id = Config.TEAMUP_DEVICE_ID

        self._bearer_token = None
        self._token_expiry = 0

        self._base_headers = {
            'Accept': "application/json",
            'Content-Type': "application/json",
            'Teamup-Token': self.master_api_key # This token is always present
        }
        
        self.subcalendar_limits = {
            'free': 8, 'plus': 48, 'pro': 48, 'business': 96
        }
        self.teamup_plan = Config.TEAMUP_PLAN
        self.max_subcalendars = self.subcalendar_limits[self.teamup_plan]
        
        print(f"HybridTeamUpManager initialized:")
        print(f"  - Master API Key: {'***' if self.master_api_key else 'None'}")
        print(f"  - Template Calendar (ks-key): {self.template_calendar_key}") # Clarify this is ks-key
        print(f"  - Plan: {self.teamup_plan} (max {self.max_subcalendars} subcalendars)")
        print(f"  - Admin Email: {self.admin_email}")
    
    def _get_bearer_token(self):
        """Obtains or refreshes a bearer token from TeamUp API."""
        now = time.time()
        if self._bearer_token is None or self._token_expiry < now + 60:
            print("Obtaining new Bearer token from TeamUp API...")
            try:
                auth_data = {
                    "app_name": self.app_name,
                    "device_id": self.device_id,
                    "email": self.admin_email,
                    "password": self.admin_password
                }
                
                response = requests.post(
                    f"{self.base_url}/auth/tokens",
                    headers=self._base_headers, # Use base headers (Teamup-Token only)
                    json=auth_data,
                    timeout=15
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    self._bearer_token = response_data['auth_token']
                    self._token_expiry = now + 3500 
                    print("✅ Bearer token obtained.")
                    return self._bearer_token
                else:
                    error_msg = response.text
                    try:
                        error_json = response.json()
                        if 'error' in error_json and 'message' in error_json['error']:
                            error_msg = error_json['error']['message']
                    except json.JSONDecodeError:
                        pass
                    print(f"❌ Failed to obtain Bearer token: Status {response.status_code}, Error: {error_msg}")
                    raise Exception(f"Failed to obtain TeamUp Bearer token: {error_msg}")
            except Exception as e:
                import traceback
                traceback.print_exc()
                raise Exception(f"Exception during Bearer token acquisition: {str(e)}")
        
        return self._bearer_token

    def _get_headers_with_auth(self):
        """Returns headers including the Teamup-Token and the Bearer token."""
        bearer_token = self._get_bearer_token()
        headers = self._base_headers.copy() # Start with _base_headers
        if bearer_token:
            headers['Authorization'] = f'Bearer {bearer_token}'
        return headers
    
    def create_organization_setup(self, organization):
        """สร้าง TeamUp setup สำหรับ organization ใหม่"""
        try:
            from models import db, TeamUpCalendar, OrganizationSubcalendar
            
            print(f"Creating TeamUp setup for organization: {organization.name}")
            
            if not self.template_calendar_key:
                return {
                    'success': False, 
                    'error': 'TEMPLATE_CALENDAR_KEY is not configured. Please set it in .env file.'
                }
            if not self.admin_email or not self.admin_password:
                return {
                    'success': False,
                    'error': 'TeamUp admin credentials (TEAMUP_ADMIN_EMAIL, TEAMUP_ADMIN_PASSWORD) are required in .env for Master Calendar creation.'
                }
            
            # ทดสอบการเข้าถึง template calendar ก่อน (จะใช้ Bearer Token แล้ว)
            test_result = self._test_template_access()
            if not test_result['success']:
                return test_result
            
            # สร้าง Master Calendar แรกโดยใช้ Template (และพยายามดึง ks-key)
            calendar_result = self.create_master_calendar(organization)
            if not calendar_result['success']:
                return calendar_result
            
            # calendar_id ที่ได้จาก create_master_calendar จะเป็น ks-key แล้ว
            calendar_id = calendar_result['calendar_id'] 
            
            # บันทึก Master Calendar
            teamup_calendar = TeamUpCalendar(
                organization_id=organization.id,
                calendar_id=calendar_id, # This is the ks-key
                calendar_name=calendar_result['calendar_name'],
                is_primary=True,
                subcalendar_count=0,
                max_subcalendars=self.max_subcalendars
            )
            db.session.add(teamup_calendar)
            db.session.flush()
            
            # ดึงข้อมูล subcalendars เริ่มต้นจากปฏิทินที่เพิ่งคัดลอกมา (ใช้ ks-key)
            initial_subcals_data = self._get_subcalendars_from_teamup(calendar_id)
            created_subcalendars = []
            
            for subcal_info in initial_subcals_data.get('subcalendars', []):
                org_subcal = OrganizationSubcalendar(
                    organization_id=organization.id,
                    calendar_id=calendar_id, # This is the ks-key
                    subcalendar_id=subcal_info['id'],
                    subcalendar_name=subcal_info['name'],
                    is_active=subcal_info.get('active', True)
                )
                db.session.add(org_subcal)
                created_subcalendars.append(subcal_info)
            
            teamup_calendar.subcalendar_count = len(created_subcalendars)
            db.session.commit()
            
            print(f"✅ TeamUp setup created successfully:")
            print(f"  - Calendar ID (ks-key): {calendar_id}")
            print(f"  - Subcalendars: {len(created_subcalendars)}")
            
            return {
                'success': True,
                'primary_calendar_id': calendar_id, # Return the ks-key
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
        """ทดสอบการเข้าถึง template calendar โดยใช้ Bearer token."""
        try:
            print(f"Testing access to template calendar: {self.template_calendar_key}")
            
            headers_with_auth = self._get_headers_with_auth()

            response = requests.get(
                f"{self.base_url}/{self.template_calendar_key}/configuration",
                headers=headers_with_auth,
                timeout=10
            )
            
            print(f"Template access test - Status: {response.status_code}")
            
            if response.status_code == 200:
                config_data = response.json()
                print(f"✅ Template calendar accessible: {config_data.get('configuration', {}).get('identity', {}).get('title', 'Unknown')}")
                return {'success': True}
            elif response.status_code == 401:
                return {
                    'success': False,
                    'error': 'Bearer token issue (401). Please check TEAMUP_ADMIN_EMAIL/PASSWORD or MASTER_TEAMUP_API key.'
                }
            elif response.status_code == 403:
                return {
                    'success': False,
                    'error': 'No permission (403) to access template calendar. Ensure TeamUp admin account has access to the template.'
                }
            elif response.status_code == 404:
                return {
                    'success': False,
                    'error': 'Template calendar not found (404). Please check TEMPLATE_CALENDAR_KEY in .env.'
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
        """
        สร้าง Master Calendar ใหม่โดยการคัดลอกจาก Template Calendar.
        และพยายามดึง calendarKey (ks-key) ที่ถูกต้อง.
        """
        try:
            print(f"Creating master calendar for: {organization.name}")
            
            calendar_name = f"{organization.name} - Main Calendar"
            
            copy_data = {
                'title': calendar_name,
                'copySubcalendars': True,
                'copyEvents': False
            }
            
            print(f"Copying template calendar with data: {copy_data}")
            
            headers_with_auth = self._get_headers_with_auth()

            response = requests.post(
                f"{self.base_url}/{self.template_calendar_key}/copy",
                headers=headers_with_auth,
                json=copy_data,
                allow_redirects=False, # We want to handle the redirect manually
                timeout=30
            )
            
            print(f"Copy calendar response - Status: {response.status_code}")
            print(f"Copy calendar response - Headers: {dict(response.headers)}")
            print(f"Copy calendar response - Text: {response.text[:500]}")
            
            if response.status_code == 302:
                redirect_url = response.headers.get('Location')
                if redirect_url:
                    # UPDATED REGEX: Capture both 'ksXXXXXX' and 'c/ID' patterns
                    # new_calendar_id_short will be 'b12prg' or 'ksXXXXXX'
                    match = re.search(r'https?://(?:www\.)?teamup\.com/(?:ks/|c/)([a-zA-Z0-9]+)', redirect_url)
                    
                    if match:
                        new_calendar_id_short = match.group(1) # e.g., 'b12prg'
                        print(f"Potential new calendar ID from redirect: {new_calendar_id_short}")

                        # Now, use this short ID to query the /configuration endpoint
                        # to get the actual ks-key
                        config_response = requests.get(
                            f"{self.base_url}/{new_calendar_id_short}/configuration",
                            headers=headers_with_auth,
                            timeout=10
                        )
                        
                        if config_response.status_code == 200:
                            config_data = config_response.json()
                            actual_ks_key = config_data.get('configuration', {}).get('link', {}).get('key')
                            
                            if actual_ks_key:
                                print(f"✅ Successfully retrieved actual ks-key: {actual_ks_key}")
                                if self._verify_calendar_creation(actual_ks_key): # Verify with the ks-key
                                    return {
                                        'success': True,
                                        'calendar_id': actual_ks_key, # Store the actual ks-key
                                        'calendar_name': calendar_name
                                    }
                                else:
                                    return {
                                        'success': False,
                                        'error': 'Calendar was created but actual ks-key access failed. Check API permissions or TeamUp status.'
                                    }
                            else:
                                return {
                                    'success': False,
                                    'error': f"Could not find 'key' in /configuration response for {new_calendar_id_short}"
                                }
                        else:
                            return {
                                'success': False,
                                'error': f"Failed to get configuration for new calendar ({new_calendar_id_short}). Status: {config_response.status_code}, Text: {config_response.text}"
                            }
                    else:
                        return {
                            'success': False,
                            'error': f"Cannot parse calendar ID from redirect URL: {redirect_url}. Expected format like teamup.com/c/ID or teamup.com/ksID."
                        }
                else:
                    return {
                        'success': False,
                        'error': "No Location header in redirect response for 302 status."
                    }
            # ... (ส่วน response.status_code == 200 และ else เหมือนเดิม) ...
            elif response.status_code == 200:
                # Handle cases where 200 is returned directly (less common for copy)
                try:
                    response_data = response.json()
                    # Check if it contains a 'calendar' object with an 'id' that might be the ks-key
                    # This path is less reliable for new calendars created via copy.
                    if 'calendar' in response_data and 'id' in response_data['calendar']:
                        potential_ks_key = response_data['calendar']['id'] # This is likely a ks-key
                        print(f"Attempting to verify potential ks-key from 200 response body: {potential_ks_key}")
                        if self._verify_calendar_creation(potential_ks_key):
                            return {
                                'success': True,
                                'calendar_id': potential_ks_key,
                                'calendar_name': calendar_name
                            }
                        else:
                            return {
                                'success': False,
                                'error': 'Calendar was created (200) but cannot be accessed with potential ks-key. Check API permissions or TeamUp status.'
                            }
                except json.JSONDecodeError:
                    pass # Not a JSON response
                
                return {
                    'success': False,
                    'error': f"Unexpected success response format (Status 200): {response.text}. Could not find calendar ID."
                }
            else:
                # Standard error handling
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
                
                if response.status_code == 401:
                    error_msg = "Authentication failed (401). Bearer token expired or invalid. Check TEAMUP_ADMIN_EMAIL/PASSWORD."
                elif response.status_code == 403:
                    error_msg = "No permission to copy calendar. Ensure TeamUp admin account has 'administrator' access to the template calendar."
                elif response.status_code == 404:
                    error_msg = "Template calendar not found. Please check TEMPLATE_CALENDAR_KEY in .env."
                elif response.status_code == 429:
                    error_msg = "Too many requests to TeamUp API (429). Please wait and try again."
                elif response.status_code == 400:
                    error_msg = f"Bad request to TeamUp API: {error_msg}"
                
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
        """ตรวจสอบว่า calendar ถูกสร้างและเข้าถึงได้จริงโดยใช้ Bearer token (และเป็น ks-key)."""
        # Note: calendar_id passed here is expected to be a ks-key
        try:
            print(f"Verifying calendar creation (with ks-key): {calendar_id}")
            
            headers_with_auth = self._get_headers_with_auth()

            response = requests.get(
                f"{self.base_url}/{calendar_id}/configuration",
                headers=headers_with_auth,
                timeout=10
            )
            
            print(f"Verification response - Status: {response.status_code}")
            
            if response.status_code == 200:
                config_data = response.json()
                retrieved_key = config_data.get('configuration', {}).get('link', {}).get('key')
                if retrieved_key == calendar_id:
                    print(f"✅ Calendar verified: {config_data.get('configuration', {}).get('identity', {}).get('title', 'Unknown')} (Matching ks-key: {retrieved_key})")
                    return True
                else:
                    print(f"❌ Calendar verification failed: Retrieved key '{retrieved_key}' does not match expected '{calendar_id}'")
                    return False
            else:
                print(f"❌ Calendar verification failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Calendar verification error: {str(e)}")
            return False

    def _get_subcalendars_from_teamup(self, calendar_id):
        """ดึงรายการ subcalendars จาก TeamUp API ของ calendar ที่ระบุ (ใช้ ks-key)"""
        try:
            print(f"Fetching subcalendars for calendar (using ks-key): {calendar_id}")
            
            headers_with_auth = self._get_headers_with_auth()

            response = requests.get(
                f"{self.base_url}/{calendar_id}/subcalendars",
                headers=headers_with_auth,
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
        """สร้าง subcalendar ใน calendar ที่กำหนด (ใช้ ks-key)"""
        try:
            from models import db, TeamUpCalendar, OrganizationSubcalendar
            
            teamup_calendar = TeamUpCalendar.query.filter_by(
                organization_id=organization_id,
                calendar_id=calendar_id # This is the ks-key
            ).first()
            
            if not teamup_calendar:
                return {'success': False, 'error': 'ไม่พบ calendar ในระบบ'}
            
            if teamup_calendar.subcalendar_count >= teamup_calendar.max_subcalendars:
                return {'success': False, 'error': 'Calendar เต็มแล้ว'}
            
            subcal_data = {
                'name': subcalendar_name,
                'color': 5,
                'active': True,
                'overlap': True
            }
            
            print(f"Creating subcalendar '{subcalendar_name}' in calendar {calendar_id}")
            
            headers_with_auth = self._get_headers_with_auth()
            response = requests.post(
                f"{self.base_url}/{calendar_id}/subcalendars", # Use ks-key here
                headers=headers_with_auth,
                json=subcal_data,
                timeout=15
            )
            
            print(f"Create subcalendar response: {response.status_code} - {response.text}")

            if response.status_code == 201:
                subcal_info = response.json()['subcalendar']
                
                org_subcal = OrganizationSubcalendar(
                    organization_id=organization_id,
                    calendar_id=calendar_id, # Store the ks-key
                    subcalendar_id=subcal_info['id'],
                    subcalendar_name=subcalendar_name,
                    is_active=True
                )
                db.session.add(org_subcal)
                
                teamup_calendar.subcalendar_count += 1
                
                db.session.commit()
                
                print(f"✅ Subcalendar created successfully: {subcal_info['id']}")
                
                return {
                    'success': True,
                    'subcalendar': subcal_info,
                    'calendar_id': calendar_id # Return the ks-key
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
            
            available_calendar = self.get_available_calendar(organization_id)
            
            if available_calendar:
                print(f"Using existing calendar: {available_calendar.calendar_id}")
                return self.create_subcalendar(
                    organization_id,
                    available_calendar.calendar_id, # This is a ks-key
                    subcalendar_name
                )
            else:
                print("No available calendar found. Creating new master calendar.")
                calendar_result = self.create_master_calendar(organization)
                if not calendar_result['success']:
                    return calendar_result
                
                new_calendar = TeamUpCalendar(
                    organization_id=organization_id,
                    calendar_id=calendar_result['calendar_id'], # This is a ks-key
                    calendar_name=calendar_result['calendar_name'],
                    is_primary=False,
                    subcalendar_count=0,
                    max_subcalendars=self.max_subcalendars
                )
                db.session.add(new_calendar)
                db.session.commit()
                
                print(f"New master calendar created: {new_calendar.calendar_id}")
                
                return self.create_subcalendar(
                    organization_id,
                    new_calendar.calendar_id, # This is a ks-key
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
                headers_with_auth = self.manager._get_headers_with_auth()
                response = requests.get(
                    f"{self.manager.base_url}/{calendar.calendar_id}/configuration", # Use ks-key here
                    headers=headers_with_auth,
                    timeout=10
                )
                
                if response.status_code == 200:
                    subcal_response = requests.get(
                        f"{self.manager.base_url}/{calendar.calendar_id}/subcalendars", # Use ks-key here
                        headers=headers_with_auth,
                        timeout=10
                    )
                    
                    if subcal_response.status_code == 200:
                        teamup_subcalendars_data = subcal_response.json().get('subcalendars', [])
                        calendar.subcalendar_count = len(teamup_subcalendars_data)
                        
                        teamup_subcal_ids = {sub['id'] for sub in teamup_subcalendars_data}
                        
                        db_subcals = OrganizationSubcalendar.query.filter_by(
                            calendar_id=calendar.calendar_id # Use ks-key here
                        ).all()
                        db_subcal_ids = {sub.subcalendar_id for sub in db_subcals}
                        
                        for sub_info in teamup_subcalendars_data:
                            if sub_info['id'] not in db_subcal_ids:
                                new_org_subcal = OrganizationSubcalendar(
                                    organization_id=calendar.organization_id,
                                    calendar_id=calendar.calendar_id, # Store ks-key
                                    subcalendar_id=sub_info['id'],
                                    subcalendar_name=sub_info['name'],
                                    is_active=sub_info.get('active', True)
                                )
                                db.session.add(new_org_subcal)
                                print(f"Added new subcalendar {sub_info['name']} to DB for {calendar.calendar_name}")
                        
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
                'backup_date': datetime.now(timezone.utc).isoformat()
            },
            'calendars': [],
            'events': []
        }
        
        calendars = TeamUpCalendar.query.filter_by(
            organization_id=organization_id,
            is_active=True
        ).all()
        
        for calendar in calendars:
            cal_data = {
                'calendar_id': calendar.calendar_id, # This is a ks-key
                'calendar_name': calendar.calendar_name,
                'is_primary': calendar.is_primary,
                'subcalendars': []
            }
            backup_data['calendars'].append(cal_data)

            headers_with_auth = self.manager._get_headers_with_auth()
            subcal_response = requests.get(
                f"{self.manager.base_url}/{calendar.calendar_id}/subcalendars", # Use ks-key here
                headers=headers_with_auth,
                timeout=10
            )
            if subcal_response.status_code == 200:
                subcals_on_teamup = subcal_response.json().get('subcalendars', [])
                cal_data['subcalendars'].extend(subcals_on_teamup)
            else:
                print(f"Warning: Could not fetch subcalendars for backup of {calendar.calendar_id}: {subcal_response.text}")
            
            end_date = datetime.now() + timedelta(days=30)
            start_date = datetime.now() - timedelta(days=365)
            
            try:
                events_response = requests.get(
                    f"{self.manager.base_url}/{calendar.calendar_id}/events", # Use ks-key here
                    headers=headers_with_auth,
                    params={
                        'startDate': start_date.strftime('%Y-%m-%d'),
                        'endDate': end_date.strftime('%Y-%m-%d')
                    },
                    timeout=15
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
    
    # method get_subcalendars ของ class HybridTeamUpAPI
    def get_subcalendars(self):
        """ดึงรายการ subcalendars ทั้งหมดของ organization (จาก TeamUp API พร้อมข้อมูลสี)"""
        subcal_list = []
        
        try:
            headers_with_auth = self.manager._get_headers_with_auth()
            
            # ดึงข้อมูลจากทุก Master Calendar ขององค์กร
            for calendar in self.calendars:
                try:
                    print(f"Fetching subcalendars from calendar: {calendar.calendar_id}")
                    
                    response = requests.get(
                        f"{self.manager.base_url}/{calendar.calendar_id}/subcalendars",
                        headers=headers_with_auth,
                        timeout=10
                    )
                    
                    print(f"Response status: {response.status_code}")
                    print(f"Response text: {response.text[:500]}")  # Debug first 500 chars
                    
                    if response.status_code == 200:
                        teamup_data = response.json()
                        print(f"TeamUp subcalendars data: {teamup_data}")
                        
                        for subcal_info in teamup_data.get('subcalendars', []):
                            print(f"Processing subcalendar: {subcal_info}")
                            
                            # รวมข้อมูลจาก TeamUp API (ครบถ้วนพร้อมสี)
                            enhanced_subcal = {
                                # ข้อมูลหลักจาก TeamUp API
                                'id': subcal_info['id'],
                                'name': subcal_info['name'],
                                'color': subcal_info.get('color', 5),  # ข้อมูลสีจาก TeamUp
                                'active': subcal_info.get('active', True),
                                'readonly': subcal_info.get('readonly', False),
                                'overlap': subcal_info.get('overlap', True),
                                'creation_dt': subcal_info.get('creation_dt', ''),
                                
                                # ข้อมูลเพิ่มเติมจาก database
                                'calendar_id': calendar.calendar_id,
                                'is_active': subcal_info.get('active', True),  # alias
                                'calendar_name': calendar.calendar_name,
                                'is_primary': calendar.is_primary,
                            }
                            
                            subcal_list.append(enhanced_subcal)
                            
                    else:
                        print(f"Warning: Failed to get subcalendars from TeamUp for {calendar.calendar_id}: {response.status_code} - {response.text}")
                        
                        # Fallback: ใช้ข้อมูลจาก database (แต่ไม่มีสี)
                        db_subcals = [s for s in self.subcalendars if s.calendar_id == calendar.calendar_id]
                        for subcal_obj in db_subcals:
                            fallback_subcal = {
                                'id': subcal_obj.subcalendar_id,
                                'name': subcal_obj.subcalendar_name,
                                'calendar_id': subcal_obj.calendar_id,
                                'is_active': subcal_obj.is_active,
                                'color': 5,  # default color เนื่องจากไม่มีข้อมูลจาก API
                                'active': subcal_obj.is_active,
                                'readonly': False,  # default
                                'overlap': True,    # default
                                'creation_dt': '',  # ไม่มีข้อมูล
                                'calendar_name': calendar.calendar_name,
                                'is_primary': calendar.is_primary,
                            }
                            subcal_list.append(fallback_subcal)
                                
                except Exception as e:
                    print(f"Error fetching subcalendars from calendar {calendar.calendar_id}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    continue
        
        except Exception as e:
            print(f"Error in get_subcalendars: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Ultimate fallback: ข้อมูลจาก database เท่านั้น (ไม่มีสี)
            for subcal_obj in self.subcalendars:
                fallback_subcal = {
                    'id': subcal_obj.subcalendar_id,
                    'name': subcal_obj.subcalendar_name,
                    'calendar_id': subcal_obj.calendar_id,
                    'is_active': subcal_obj.is_active,
                    'color': 5,  # default color
                    'active': subcal_obj.is_active,
                    'readonly': False,
                    'overlap': True,
                    'creation_dt': '',
                }
                subcal_list.append(fallback_subcal)
        
        print(f"Final subcalendars list: {len(subcal_list)} items")
        if subcal_list:
            print(f"Sample subcalendar with all fields: {subcal_list[0]}")
        
        return {'subcalendars': subcal_list}
    
    def create_appointment(self, appointment_data):
        """
        สร้างนัดหมายในระบบ hybrid โดยค้นหา subcalendar_id จากชื่อโดยอัตโนมัติ
        """
        try:
            from models import OrganizationSubcalendar
            
            # 1. ดึงชื่อปฏิทินย่อยจากข้อมูลที่ส่งมา
            subcalendar_name = appointment_data.get('calendar_name')
            if not subcalendar_name:
                return False, "จำเป็นต้องระบุชื่อปฏิทิน (Calendar Name)"

            # 2. ค้นหา subcalendar จากฐานข้อมูล
            subcal_mapping = OrganizationSubcalendar.query.filter_by(
                organization_id=self.organization_id,
                subcalendar_name=subcalendar_name,
                is_active=True
            ).first()
            
            # 3. หากไม่พบ ให้ลองสร้าง subcalendar ใหม่โดยอัตโนมัติ
            if not subcal_mapping:
                print(f"Subcalendar '{subcalendar_name}' not found for org {self.organization_id}. Attempting to auto-create.")
                create_result = self.manager.auto_create_subcalendar(
                    self.organization_id, 
                    subcalendar_name
                )
                if not create_result.get('success'):
                    error_message = create_result.get('error', 'Unknown error during auto-creation')
                    print(f"Failed to auto-create subcalendar: {error_message}")
                    return False, error_message
                
                # ดึงข้อมูล mapping ของ subcalendar ที่เพิ่งสร้างใหม่
                new_subcal_id = create_result.get('subcalendar', {}).get('id')
                subcal_mapping = OrganizationSubcalendar.query.filter_by(subcalendar_id=new_subcal_id).first()

                if not subcal_mapping:
                    return False, f"Could not find the newly created subcalendar '{subcalendar_name}' in the database."

            # 4. เตรียมข้อมูลสำหรับส่งให้ TeamUp API
            calendar_id = subcal_mapping.calendar_id      # ks-key ของ Master Calendar
            subcalendar_id = subcal_mapping.subcalendar_id  # ID ของ Subcalendar (ตัวเลข)
            
            event_payload = {
                "title": appointment_data.get('title'),
                "start_dt": f"{appointment_data.get('start_date')}T{appointment_data.get('start_time')}",
                "end_dt": f"{appointment_data.get('end_date')}T{appointment_data.get('end_time')}",
                "subcalendar_ids": [subcalendar_id], # TeamUp API รับเป็น Array
                "notes": appointment_data.get('description', ''),
                "location": appointment_data.get('location', ''),
                "who": appointment_data.get('who', '')
            }
            
            print(f"Creating event in calendar '{calendar_id}' with subcalendar ID {subcalendar_id}")
            
            # 5. เรียก API เพื่อสร้าง Event
            headers = self.manager._get_headers_with_auth()
            response = requests.post(
                f"{self.manager.base_url}/{calendar_id}/events",
                headers=headers,
                json=event_payload,
                timeout=15
            )

            if response.status_code == 201:
                event = response.json().get('event', {})
                self.log_usage('create', 'appointment', event.get('id'), {'title': event.get('title')})
                return True, event
            else:
                error_details = response.json().get('error', {}).get('message', response.text)
                return False, f"TeamUp API Error: {error_details}"
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"An unexpected error occurred: {str(e)}"
    
    def get_events(self, start_date=None, end_date=None, subcalendar_id=None, event_id=None):
        """ดึง events จากทุก calendars ของ organization หรือเฉพาะ event_id - แก้ไข parameter handling"""
        all_events = []
        
        try:
            from models import OrganizationSubcalendar
            
            headers_with_auth = self.manager._get_headers_with_auth()

            if event_id:
                for cal in self.calendars:
                    try:
                        single_event_response = requests.get(
                            f"{self.manager.base_url}/{cal.calendar_id}/events/{event_id}",
                            headers=headers_with_auth,
                            timeout=15
                        )
                        if single_event_response.status_code == 200:
                            found_event = single_event_response.json().get('event')
                            if found_event:
                                found_event['source_calendar_id'] = cal.calendar_id
                                return {"events": [found_event]}
                    except Exception as e:
                        print(f"Error checking calendar {cal.calendar_id} for event {event_id}: {e}")
                return {"error": "Event not found across calendars", "events": []}
            
            subcalendar_filter_ids = []
            calendars_to_query_keys = []
            
            if subcalendar_id:
                # **แก้ไขการจัดการ subcalendar_id parameter**
                if isinstance(subcalendar_id, list) and len(subcalendar_id) > 0:
                    # ถ้าเป็น list ให้ใช้ตัวแรกเพื่อหา calendar_id
                    first_subcal_id = subcalendar_id[0]
                    try:
                        # แปลงเป็น int ถ้าเป็น string
                        first_subcal_id = int(first_subcal_id) if isinstance(first_subcal_id, str) else first_subcal_id
                    except (ValueError, TypeError):
                        print(f"Invalid subcalendar_id format: {first_subcal_id}")
                        first_subcal_id = None
                    
                    if first_subcal_id:
                        subcal_mapping = OrganizationSubcalendar.query.filter_by(
                            organization_id=self.organization_id,
                            subcalendar_id=first_subcal_id,
                            is_active=True
                        ).first()
                        
                        if subcal_mapping:
                            calendars_to_query_keys = [subcal_mapping.calendar_id]
                            # **แก้ไข: แปลง subcalendar_id ทั้งหมดเป็น int**
                            subcalendar_filter_ids = []
                            for sid in subcalendar_id:
                                try:
                                    subcalendar_filter_ids.append(int(sid) if isinstance(sid, str) else sid)
                                except (ValueError, TypeError):
                                    print(f"Skipping invalid subcalendar_id: {sid}")
                        else:
                            return {"error": "ไม่พบ subcalendar ที่ระบุ", "events": []}
                    else:
                        # ถ้า parse ไม่ได้ให้ query ทุก calendar
                        calendars_to_query_keys = [cal.calendar_id for cal in self.calendars]
                        subcalendar_filter_ids = [sub.subcalendar_id for sub in self.subcalendars]
                else:
                    # ถ้าไม่ใช่ list หรือเป็น list ว่าง
                    calendars_to_query_keys = [cal.calendar_id for cal in self.calendars]
                    subcalendar_filter_ids = [sub.subcalendar_id for sub in self.subcalendars]
            else:
                calendars_to_query_keys = [cal.calendar_id for cal in self.calendars]
                subcalendar_filter_ids = [sub.subcalendar_id for sub in self.subcalendars]
            
            # **แก้ไข: ตรวจสอบ date types**
            if not isinstance(start_date, datetime):
                start_date = datetime.strptime(start_date, '%Y-%m-%d') if isinstance(start_date, str) else datetime.now() - timedelta(days=7)
            if not isinstance(end_date, datetime):
                end_date = datetime.strptime(end_date, '%Y-%m-%d') if isinstance(end_date, str) else datetime.now() + timedelta(days=30)
            
            print(f"DEBUG: Querying {len(calendars_to_query_keys)} calendars with {len(subcalendar_filter_ids)} subcalendars")
            
            for calendar_id_key in calendars_to_query_keys:
                events = self.fetch_calendar_events(
                    calendar_id=calendar_id_key,
                    start_date=start_date,
                    end_date=end_date,
                    subcalendar_ids=subcalendar_filter_ids  # ส่งเป็น list ของ integers
                )
                
                if events.get('events'):
                    for event in events['events']:
                        event['source_calendar_id'] = calendar_id_key
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
        """ดึง events จาก calendar เดียว (ใช้ ks-key) - แก้ไข method call"""
        try:
            params = {}
            
            if start_date:
                params['startDate'] = start_date.strftime('%Y-%m-%d')
            if end_date:
                params['endDate'] = end_date.strftime('%Y-%m-%d')
            
            # **แก้ไขตรงนี้: เปลี่ยนจาก self._get_headers_with_auth() เป็น self.manager._get_headers_with_auth()**
            headers_with_auth = self.manager._get_headers_with_auth()
            
            # สร้าง URL params สำหรับ subcalendarId array
            url = f"{self.manager.base_url}/{calendar_id}/events"
            
            # เพิ่ม query parameters
            query_params = []
            if 'startDate' in params:
                query_params.append(f"startDate={params['startDate']}")
            if 'endDate' in params:
                query_params.append(f"endDate={params['endDate']}")
                
            # แก้ไขสำคัญ: format subcalendarId เป็น array
            if subcalendar_ids is not None and len(subcalendar_ids) > 0:
                for sid in subcalendar_ids:
                    query_params.append(f"subcalendarId[]={sid}")
            
            # รวม URL ถ้ามี query params
            if query_params:
                url += "?" + "&".join(query_params)
            
            print(f"DEBUG: Fetching events from URL: {url}")
            
            response = requests.get(
                url,
                headers=headers_with_auth,
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
    
    def update_appointment_status(self, event_id, new_status_text):
        """
        อัปเดตสถานะของนัดหมายโดยการแก้ไขฟิลด์ 'notes'
        โดยจะทำการค้นหา event ในทุก Master Calendar ขององค์กร
        """
        try:
            # 1. ค้นหา Event และ Master Calendar (ks-key) ที่ถูกต้อง
            event_data = None
            target_calendar_id = None
            
            for calendar in self.calendars:
                response = requests.get(
                    f"{self.manager.base_url}/{calendar.calendar_id}/events/{event_id}",
                    headers=self.manager._get_headers_with_auth(),
                    timeout=10
                )
                if response.status_code == 200:
                    event_data = response.json().get('event')
                    target_calendar_id = calendar.calendar_id
                    break # เมื่อเจอ event ให้หยุดค้นหาทันที
            
            if not event_data:
                return False, "ไม่พบนัดหมายที่ระบุ หรือไม่มีสิทธิ์เข้าถึง"

            # 2. เตรียมข้อมูลใหม่เพื่ออัปเดต
            # ลบ tag สถานะเก่าออกก่อน (ถ้ามี)
            original_notes = event_data.get('notes', '')
            cleaned_notes = re.sub(r'\s*\[สถานะ:.*?\]', '', original_notes).strip()

            # สร้าง notes ใหม่โดยเพิ่ม tag สถานะใหม่เข้าไป
            updated_notes = f"{cleaned_notes} [สถานะ: {new_status_text}]".strip()

            # 3. สร้าง Payload สำหรับ PUT request โดยใช้ข้อมูลเดิมเกือบทั้งหมด
            update_payload = {
                'id': event_data['id'],
                'subcalendar_ids': event_data['subcalendar_ids'],
                'title': event_data['title'],
                'start_dt': event_data['start_dt'],
                'end_dt': event_data['end_dt'],
                'notes': updated_notes, # << ใส่ notes ที่อัปเดตแล้ว
                # คงค่าเดิมของฟิลด์อื่นๆ
                'location': event_data.get('location'),
                'who': event_data.get('who'),
                'rrule': event_data.get('rrule'),
                'version': event_data.get('version') # สำคัญมากสำหรับการป้องกัน conflict
            }

            # 4. ส่ง PUT request เพื่ออัปเดต Event
            update_response = requests.put(
                f"{self.manager.base_url}/{target_calendar_id}/events/{event_id}",
                headers=self.manager._get_headers_with_auth(),
                json=update_payload,
                timeout=15
            )

            if update_response.status_code == 200:
                self.log_usage('update', 'appointment', event_id, {'status': new_status_text})
                return True, "อัปเดตสถานะสำเร็จ"
            else:
                error_details = update_response.json().get('error', {}).get('message', update_response.text)
                return False, f"อัปเดตสถานะล้มเหลว: {error_details}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"An unexpected error occurred: {str(e)}"
    
    def _update_event_in_calendar(self, calendar_id, event_id, status):
        """อัปเดต event ใน calendar ที่ระบุ (ใช้ ks-key)"""
        try:
            headers_with_auth = self.manager._get_headers_with_auth()

            response = requests.get(
                f"{self.manager.base_url}/{calendar_id}/events/{event_id}", # Use ks-key here
                headers=headers_with_auth,
                timeout=15
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
            
            updated_notes = re.sub(r'\s*\[สถานะ:.*?\]\s*', '', current_notes)
            new_status_tag = f" [สถานะ: {status}]"
            
            if updated_notes:
                if updated_notes.endswith('.'):
                    updated_notes = updated_notes[:-1] + new_status_tag + "."
                else:
                    updated_notes += new_status_tag
            else:
                updated_notes = new_status_tag.strip()
            
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

            for field in ['location', 'who', 'rrule', 'subcalendar_ids', 'subcalendar_remote_ids']:
                if field in event_data:
                    update_data[field] = event_data[field]
            
            update_response = requests.put(
                f"{self.manager.base_url}/{calendar_id}/events/{event_id}", # Use ks-key here
                headers=headers_with_auth,
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
                    error_json = response.json()
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
        """
        สร้างนัดหมายเกิดซ้ำ (Recurring) โดยใช้ TeamUp RRULE
        ฟังก์ชันนี้จะใช้ Logic ค้นหา Subcalendar จาก create_appointment
        """
        try:
            from models import OrganizationSubcalendar
            
            # 1. ดึงชื่อปฏิทินย่อยและค้นหา ID (เหมือน create_appointment)
            subcalendar_name = patient_data.get('calendar_name')
            if not subcalendar_name:
                return False, "จำเป็นต้องระบุชื่อปฏิทิน (Calendar Name)"

            subcal_mapping = OrganizationSubcalendar.query.filter_by(
                organization_id=self.organization_id,
                subcalendar_name=subcalendar_name,
                is_active=True
            ).first()

            if not subcal_mapping:
                # (ส่วนของการ auto-create subcalendar เหมือนเดิม)
                return False, f"ไม่พบปฏิทินย่อยชื่อ '{subcalendar_name}'"

            calendar_id = subcal_mapping.calendar_id
            subcalendar_id = subcal_mapping.subcalendar_id

            # 2. สร้าง RRULE
            if not selected_days:
                return False, "กรุณาเลือกอย่างน้อยหนึ่งวันสำหรับนัดหมายที่เกิดซ้ำ"
            rrule = f"FREQ=WEEKLY;BYDAY={','.join(selected_days)};COUNT={weeks}"

            # 3. เตรียม Payload สำหรับ Recurring Event
            event_payload = {
                "title": patient_data.get('title'),
                "start_dt": f"{patient_data.get('start_date')}T{patient_data.get('start_time')}",
                "end_dt": f"{patient_data.get('end_date')}T{patient_data.get('end_time')}",
                "subcalendar_ids": [subcalendar_id],
                "rrule": rrule, # เพิ่ม RRULE
                "notes": patient_data.get('description', ''),
                "location": patient_data.get('location', ''),
                "who": patient_data.get('who', '')
            }
            
            # 4. เรียก API เพื่อสร้าง Event
            headers = self.manager._get_headers_with_auth()
            response = requests.post(
                f"{self.manager.base_url}/{calendar_id}/events",
                headers=headers,
                json=event_payload,
                timeout=15
            )

            if response.status_code == 201:
                event = response.json().get('event', {})
                self.log_usage('create', 'recurring_appointment', event.get('id'), {'title': event.get('title'), 'rrule': rrule})
                return True, event
            else:
                error_details = response.json().get('error', {}).get('message', response.text)
                return False, f"TeamUp API Error: {error_details}"
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"An unexpected error occurred: {str(e)}"
    
    def get_organization_stats(self):
        """ดึงสถิติการใช้งานของ organization"""
        try:
            from models import UsageStat, AuditLog
            from datetime import datetime, timedelta
            
            current_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            monthly_stats = UsageStat.query.filter(
                UsageStat.organization_id == self.organization_id,
                UsageStat.date >= current_month
            ).all()
            
            total_appointments = sum(stat.appointments_created for stat in monthly_stats)
            total_updates = sum(stat.appointments_updated for stat in monthly_stats)
            
            active_calendars = len(self.calendars)
            active_subcalendars = len(self.subcalendars)
            
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
            
            audit_log = AuditLog(
                organization_id=self.organization_id,
                user_id=self.user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details
            )
            db.session.add(audit_log)
            
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

    def build_teamup_url_with_array_params(base_url, params):
        """
        Helper สำหรับสร้าง URL ที่มี array parameters
        เช่น subcalendarId[]=123&subcalendarId[]=456
        """
        url = base_url
        query_parts = []
        
        for key, value in params.items():
            if isinstance(value, list):
                # สำหรับ array parameters
                for item in value:
                    query_parts.append(f"{key}[]={item}")
            else:
                # สำหรับ normal parameters
                query_parts.append(f"{key}={value}")
        
        if query_parts:
            url += "?" + "&".join(query_parts)
        
        return url

    # Test function สำหรับทดสอบ API call
    def test_teamup_api_call():
        """ทดสอบการเรียก TeamUp API ด้วย subcalendarId array"""
        # สำหรับ debug เท่านั้น
        test_url = build_teamup_url_with_array_params(
            "https://api.teamup.com/ksa5n83we4xo5qtb1c/events",
            {
                'startDate': '2025-07-01',
                'endDate': '2025-07-31',
                'subcalendarId': [123, 456, 789]
            }
        )
        print(f"Test URL: {test_url}")
        # Expected: https://api.teamup.com/ksa5n83we4xo5qtb1c/events?startDate=2025-07-01&endDate=2025-07-31&subcalendarId[]=123&subcalendarId[]=456&subcalendarId[]=789

# Factory function
def get_hybrid_teamup_api(organization_id, user_id=None):
    """Factory function สำหรับสร้าง HybridTeamUpAPI instance"""
    return HybridTeamUpAPI(organization_id, user_id)