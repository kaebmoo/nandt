#!/usr/bin/env python3
"""
Debug script to check appointment data
Usage: python debug_appointment.py <appointment_id> <subdomain>
"""

import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared_db.models import Appointment, EventType, AvailabilityTemplate
from shared_db.database import SessionLocal

def check_appointment(appointment_id: int, subdomain: str):
    """Check appointment and its related data"""
    
    db = SessionLocal()
    schema_name = f"tenant_{subdomain}"
    
    try:
        # Set search path
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        db.commit()
        
        # Get appointment
        appointment = db.query(Appointment).filter_by(id=appointment_id).first()
        
        if not appointment:
            print(f"❌ ไม่พบ appointment ID {appointment_id}")
            return
        
        print(f"✅ พบ appointment ID {appointment_id}")
        print(f"   - Booking Reference: {appointment.booking_reference}")
        print(f"   - Start Time: {appointment.start_time}")
        print(f"   - Event Type ID: {appointment.event_type_id}")
        print(f"   - Status: {appointment.status}")
        
        # Get event type
        if appointment.event_type_id:
            event_type = db.query(EventType).filter_by(id=appointment.event_type_id).first()
            
            if event_type:
                print(f"\n✅ พบ EventType ID {event_type.id}")
                print(f"   - Name: {event_type.name}")
                print(f"   - Template ID: {event_type.template_id}")
                print(f"   - Duration: {event_type.duration_minutes} minutes")
                
                # Get template
                if event_type.template_id:
                    template = db.query(AvailabilityTemplate).filter_by(id=event_type.template_id).first()
                    
                    if template:
                        print(f"\n✅ พบ AvailabilityTemplate ID {template.id}")
                        print(f"   - Name: {template.name}")
                        print(f"   - Type: {template.template_type}")
                        print(f"   - Requires Provider: {template.requires_provider_assignment}")
                    else:
                        print(f"\n❌ ไม่พบ template ID {event_type.template_id}")
                else:
                    print(f"\n❌ EventType ไม่มี template_id")
            else:
                print(f"\n❌ ไม่พบ EventType ID {appointment.event_type_id}")
        else:
            print(f"\n❌ Appointment ไม่มี event_type_id")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python debug_appointment.py <appointment_id> <subdomain>")
        print("Example: python debug_appointment.py 31 humnoi")
        sys.exit(1)
    
    appointment_id = int(sys.argv[1])
    subdomain = sys.argv[2]
    
    check_appointment(appointment_id, subdomain)
