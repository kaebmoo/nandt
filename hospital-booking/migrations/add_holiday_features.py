# migrations/versions/001_update_holiday_model.py

from sqlalchemy import text, inspect

# Revision identifiers, used by Alembic.
# คุณอาจจะต้องปรับค่าเหล่านี้ตามระบบ Alembic ของคุณ
revision = '001'
down_revision = None # หรือ revision ก่อนหน้า
branch_labels = None
depends_on = None

def upgrade(engine):
    """
    อัปเกรดตาราง Holiday ในทุก tenant schema ให้ตรงกับโมเดลล่าสุด
    - เปลี่ยน date เป็น DATE และเพิ่ม UNIQUE constraint
    - เพิ่ม/ปรับปรุงคอลัมน์ source, is_active, is_recurring, updated_at
    - ลบคอลัมน์ที่ไม่ต้องการแล้ว (ถ้ามี)
    """
    with engine.connect() as conn:
        # ใช้ transaction เพื่อให้แน่ใจว่าการเปลี่ยนแปลงในแต่ละ schema จะสำเร็จทั้งหมดหรือไม่ก็ไม่สำเร็จเลย
        with conn.begin():
            # ดึงรายชื่อ schema ทั้งหมด
            result = conn.execute(text("SELECT schema_name FROM public.hospitals"))
            schemas = [row[0] for row in result]

        for schema in schemas:
            print(f"Applying migration to schema: {schema}...")
            with conn.begin():
                # ตั้งค่า search_path สำหรับ transaction นี้
                conn.execute(text(f'SET search_path TO "{schema}"'))

                inspector = inspect(conn)
                columns = [col['name'] for col in inspector.get_columns('holidays')]

                # 1. เปลี่ยน date -> DATE และเพิ่ม UNIQUE
                conn.execute(text("""
                    ALTER TABLE holidays
                    ALTER COLUMN date TYPE DATE USING date::DATE;
                    
                    -- ลบ constraint เดิมถ้ามีชื่อซ้ำ
                    ALTER TABLE holidays DROP CONSTRAINT IF EXISTS holidays_date_key;
                    -- เพิ่ม constraint ใหม่
                    ALTER TABLE holidays ADD CONSTRAINT holidays_date_key UNIQUE (date);
                """))
                print(f"  -> Column 'date' updated to DATE with UNIQUE constraint.")

                # 2. เพิ่ม/แก้ไขคอลัมน์ 'source'
                if 'source' not in columns:
                    conn.execute(text("ALTER TABLE holidays ADD COLUMN source VARCHAR(50) NOT NULL DEFAULT 'manual'"))
                else:
                    conn.execute(text("""
                        ALTER TABLE holidays ALTER COLUMN source SET NOT NULL,
                        ALTER COLUMN source SET DEFAULT 'manual';
                    """))
                print(f"  -> Column 'source' ensured.")

                # 3. เพิ่ม/แก้ไขคอลัมน์ 'is_active'
                if 'is_active' not in columns:
                    conn.execute(text("ALTER TABLE holidays ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"))
                else:
                    conn.execute(text("""
                        ALTER TABLE holidays ALTER COLUMN is_active SET NOT NULL,
                        ALTER COLUMN is_active SET DEFAULT TRUE;
                    """))
                print(f"  -> Column 'is_active' ensured.")

                # 4. เพิ่ม/แก้ไขคอลัมน์ 'is_recurring' (ตามโมเดลของคุณ)
                if 'is_recurring' not in columns:
                    conn.execute(text("ALTER TABLE holidays ADD COLUMN is_recurring BOOLEAN NOT NULL DEFAULT FALSE"))
                else:
                    conn.execute(text("""
                        ALTER TABLE holidays ALTER COLUMN is_recurring SET NOT NULL,
                        ALTER COLUMN is_recurring SET DEFAULT FALSE;
                    """))
                print(f"  -> Column 'is_recurring' ensured.")
                
                # 5. เพิ่มคอลัมน์ 'updated_at' (ถ้ายังไม่มี)
                if 'updated_at' not in columns:
                    conn.execute(text("ALTER TABLE holidays ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE"))
                print(f"  -> Column 'updated_at' ensured.")

            print(f"  -> Successfully migrated schema: {schema}")


def downgrade(engine):
    """
    ย้อนกลับการเปลี่ยนแปลงในตาราง Holiday (เป็นทางเลือก แต่แนะนำให้มี)
    """
    with engine.connect() as conn:
        with conn.begin():
            result = conn.execute(text("SELECT schema_name FROM public.hospitals"))
            schemas = [row[0] for row in result]
        
        for schema in schemas:
            print(f"Reverting migration for schema: {schema}...")
            with conn.begin():
                conn.execute(text(f'SET search_path TO "{schema}"'))
                
                # เปลี่ยน date กลับเป็น TIMESTAMP และลบ UNIQUE constraint
                conn.execute(text("""
                    ALTER TABLE holidays DROP CONSTRAINT IF EXISTS holidays_date_key;
                    ALTER TABLE holidays ALTER COLUMN date TYPE TIMESTAMP WITH TIME ZONE;
                """))
                
                # ลบคอลัมน์ที่เพิ่มเข้าไป
                conn.execute(text("""
                    ALTER TABLE holidays
                    DROP COLUMN IF EXISTS source,
                    DROP COLUMN IF EXISTS is_active,
                    DROP COLUMN IF EXISTS is_recurring,
                    DROP COLUMN IF EXISTS updated_at;
                """))

            print(f"  -> Successfully reverted schema: {schema}")


from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

# โหลด environment variables
load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)

# สั่งรัน upgrade
upgrade(engine)

# หรือสั่งรัน downgrade
# downgrade(engine)