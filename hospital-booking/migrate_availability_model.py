# migrate_availability_model.py - Migration script to fix availability model
# Changes: availability -> schedule template, event_types -> reference availability

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()
sys.path.append('flask_app/app')
import models

DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def migrate_tenant_schema(schema_name):
    """Migrate a single tenant schema to new availability model"""
    
    print(f"=== Migrating {schema_name} ===")
    
    db = SessionLocal()
    
    try:
        # Set search path
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        
        print("1. Backing up existing availability data...")
        
        # Backup existing data
        existing_availability = db.execute(text('''
            SELECT DISTINCT day_of_week, start_time, end_time, timezone
            FROM availabilities 
            WHERE is_active = true
            ORDER BY day_of_week, start_time
        ''')).fetchall()
        
        print(f"   Found {len(existing_availability)} unique availability patterns")
        
        print("2. Adding new columns to availabilities table...")
        
        # Add new columns to availabilities
        try:
            db.execute(text('ALTER TABLE availabilities ADD COLUMN name VARCHAR(100)'))
            db.execute(text('ALTER TABLE availabilities ADD COLUMN description TEXT'))
        except Exception as e:
            if "already exists" not in str(e):
                print(f"   Warning: {e}")
        
        print("3. Adding availability_id to event_types...")
        
        # Add availability_id to event_types
        try:
            db.execute(text('ALTER TABLE event_types ADD COLUMN availability_id INTEGER'))
        except Exception as e:
            if "already exists" not in str(e):
                print(f"   Warning: {e}")
        
        print("4. Creating schedule templates from existing data...")
        
        # Clear existing availabilities and create new ones
        db.execute(text('DELETE FROM availabilities'))
        
        # Create availability templates
        template_id = 1
        availability_map = {}
        
        for avail in existing_availability:
            day_name = avail[0]
            start_time = avail[1]
            end_time = avail[2]
            timezone_val = avail[3] or 'Asia/Bangkok'
            
            # Create template name
            day_names = {
                'MONDAY': 'จันทร์', 'TUESDAY': 'อังคาร', 'WEDNESDAY': 'พุธ', 
                'THURSDAY': 'พฤหัสบดี', 'FRIDAY': 'ศุกร์', 'SATURDAY': 'เสาร์', 'SUNDAY': 'อาทิตย์'
            }
            
            template_name = f"{day_names.get(day_name, day_name)} ({start_time}-{end_time})"
            template_key = f"{day_name}_{start_time}_{end_time}"
            
            if template_key not in availability_map:
                # Insert new availability template
                db.execute(text(f'''
                    INSERT INTO availabilities (id, name, description, day_of_week, start_time, end_time, timezone, is_active, created_at)
                    VALUES ({template_id}, '{template_name}', 'รูปแบบเวลาทำการ', '{day_name}', '{start_time}', '{end_time}', '{timezone_val}', true, NOW())
                '''))
                
                availability_map[template_key] = template_id
                template_id += 1
        
        print(f"   Created {len(availability_map)} availability templates")
        
        print("5. Updating event_types to reference availability templates...")
        
        # Update event_types to use first availability template
        if availability_map:
            first_availability_id = list(availability_map.values())[0]
            db.execute(text(f'UPDATE event_types SET availability_id = {first_availability_id}'))
        
        print("6. Dropping old columns...")
        
        # Drop old columns from availabilities (optional - keep for safety)
        # db.execute(text('ALTER TABLE availabilities DROP COLUMN IF EXISTS provider_id'))
        # db.execute(text('ALTER TABLE availabilities DROP COLUMN IF EXISTS event_type_id'))
        
        # Remove provider_id from date_overrides 
        try:
            db.execute(text('ALTER TABLE date_overrides DROP COLUMN IF EXISTS provider_id'))
        except Exception as e:
            print(f"   Warning dropping provider_id from date_overrides: {e}")
        
        db.commit()
        print(f"✅ Migration completed for {schema_name}")
        
    except Exception as e:
        print(f"❌ Error migrating {schema_name}: {e}")
        db.rollback()
        raise
    finally:
        db.execute(text('SET search_path TO public'))
        db.close()

def main():
    """Main migration function"""
    
    print("🔄 Hospital Booking System - Availability Model Migration")
    print("=" * 60)
    
    # Get all tenant schemas
    db = SessionLocal()
    try:
        tenant_schemas = db.execute(text('''
            SELECT schema_name 
            FROM information_schema.schemata 
            WHERE schema_name LIKE 'tenant_%'
            ORDER BY schema_name
        ''')).fetchall()
        
        print(f"Found {len(tenant_schemas)} tenant schemas to migrate:")
        for schema in tenant_schemas:
            print(f"  - {schema[0]}")
        
        confirm = input("\nProceed with migration? (y/N): ").strip().lower()
        if confirm != 'y':
            print("Migration cancelled")
            return
        
        # Migrate each tenant schema
        for schema in tenant_schemas:
            migrate_tenant_schema(schema[0])
            
        print("\n✅ All tenant schemas migrated successfully!")
        print("\nNext steps:")
        print("1. Update FastAPI registration to create correct initial data")
        print("2. Update Flask templates to work with new model")
        print("3. Test the full registration -> dashboard -> API flow")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return
    finally:
        db.close()

if __name__ == "__main__":
    main()