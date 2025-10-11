#!/usr/bin/env python3
"""
Migration script to fix availability_templates unique constraint issue
This script removes the unique constraint on 'name' field to allow
duplicate template names across different tenants.

Run this script from the migrations directory:
python fix_availability_template_constraint.py
"""

import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def fix_availability_template_constraints():
    """Remove unique constraint from availability_templates.name in all tenant schemas"""
    
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not found in environment variables")
        return False
    
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = SessionLocal()
    
    try:
        print("🔍 Finding all tenant schemas...")
        
        # Get all tenant schemas from hospitals table
        result = db.execute(text("SELECT subdomain, schema_name FROM public.hospitals"))
        tenant_data = result.fetchall()
        
        if not tenant_data:
            print("⚠️  No tenant schemas found in hospitals table")
            return True
            
        print(f"📋 Found {len(tenant_data)} tenant schemas:")
        for subdomain, schema_name in tenant_data:
            print(f"   - {subdomain} -> {schema_name}")
        
        print("\n🔧 Processing each tenant schema...")
        
        success_count = 0
        error_count = 0
        
        for subdomain, schema_name in tenant_data:
            try:
                print(f"\n📂 Processing schema: {schema_name} (subdomain: {subdomain})")
                
                # Set search path to tenant schema
                db.execute(text(f'SET search_path TO "{schema_name}", public'))
                
                # Check if availability_templates table exists
                table_exists = db.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = :schema 
                        AND table_name = 'availability_templates'
                    )
                """), {"schema": schema_name}).scalar()
                
                if not table_exists:
                    print(f"   ⏭️  Table availability_templates not found in {schema_name}, skipping...")
                    continue
                
                # Check if unique constraint exists
                constraint_exists = db.execute(text("""
                    SELECT constraint_name 
                    FROM information_schema.table_constraints 
                    WHERE table_schema = :schema 
                    AND table_name = 'availability_templates' 
                    AND constraint_type = 'UNIQUE'
                    AND constraint_name LIKE '%name%'
                """), {"schema": schema_name}).fetchone()
                
                if constraint_exists:
                    constraint_name = constraint_exists[0]
                    print(f"   🗑️  Removing constraint: {constraint_name}")
                    
                    # Drop the unique constraint
                    db.execute(text(f'''
                        ALTER TABLE "{schema_name}".availability_templates 
                        DROP CONSTRAINT IF EXISTS "{constraint_name}"
                    '''))
                    
                    print(f"   ✅ Successfully removed unique constraint from {schema_name}")
                else:
                    print(f"   ✅ No unique constraint found on name field in {schema_name}")
                
                success_count += 1
                
            except Exception as e:
                print(f"   ❌ Error processing {schema_name}: {str(e)}")
                error_count += 1
                db.rollback()
                continue
            
            # Commit changes for this schema
            db.commit()
        
        # Reset search path
        db.execute(text('SET search_path TO public'))
        db.commit()
        
        print(f"\n📊 Migration Summary:")
        print(f"   ✅ Successfully processed: {success_count} schemas")
        print(f"   ❌ Errors: {error_count} schemas")
        
        if error_count == 0:
            print("\n🎉 Migration completed successfully!")
            return True
        else:
            print(f"\n⚠️  Migration completed with {error_count} errors")
            return False
            
    except Exception as e:
        print(f"❌ Fatal error during migration: {str(e)}")
        db.rollback()
        return False
        
    finally:
        db.close()

def verify_fix():
    """Verify that the fix was applied correctly"""
    print("\n🔍 Verifying the fix...")
    
    DATABASE_URL = os.environ.get("DATABASE_URL")
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = SessionLocal()
    
    try:
        # Get tenant schemas
        result = db.execute(text("SELECT schema_name FROM public.hospitals LIMIT 1"))
        schema_result = result.fetchone()
        
        if not schema_result:
            print("⚠️  No tenant schemas to verify")
            return
        
        schema_name = schema_result[0]
        print(f"🧪 Testing with schema: {schema_name}")
        
        # Set search path
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        
        # Check if we can create templates with duplicate names
        try:
            # This should work now without unique constraint
            test_name = "Test Template (Migration Verification)"
            
            # Clean up any existing test templates first
            db.execute(text("""
                DELETE FROM availability_templates 
                WHERE name = :name
            """), {"name": test_name})
            db.commit()
            
            # Try to create two templates with same name
            db.execute(text("""
                INSERT INTO availability_templates (name, description, timezone, is_active, created_at, updated_at)
                VALUES (:name, 'Test 1', 'Asia/Bangkok', true, NOW(), NOW())
            """), {"name": test_name})
            
            db.execute(text("""
                INSERT INTO availability_templates (name, description, timezone, is_active, created_at, updated_at)
                VALUES (:name, 'Test 2', 'Asia/Bangkok', true, NOW(), NOW())
            """), {"name": test_name})
            
            db.commit()
            
            # Clean up test data
            db.execute(text("""
                DELETE FROM availability_templates 
                WHERE name = :name
            """), {"name": test_name})
            db.commit()
            
            print("✅ Verification successful! Duplicate template names are now allowed.")
            
        except Exception as e:
            print(f"❌ Verification failed: {str(e)}")
            db.rollback()
            
    finally:
        db.execute(text('SET search_path TO public'))
        db.close()

if __name__ == '__main__':
    print("🚀 Starting availability_templates constraint fix migration...")
    print("=" * 60)
    
    success = fix_availability_template_constraints()
    
    if success:
        verify_fix()
        print("\n" + "=" * 60)
        print("✨ Migration completed! You can now create templates with duplicate names.")
        print("💡 Next step: Update models.py to remove unique=True from name field")
    else:
        print("\n" + "=" * 60)
        print("❌ Migration failed. Please check the errors above and try again.")
        sys.exit(1)