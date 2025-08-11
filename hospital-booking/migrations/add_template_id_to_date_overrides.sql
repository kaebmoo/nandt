-- เพิ่ม column template_id ใน date_overrides table
ALTER TABLE date_overrides 
ADD COLUMN IF NOT EXISTS template_id INTEGER;

-- เพิ่ม foreign key constraint (optional)
ALTER TABLE date_overrides 
ADD CONSTRAINT fk_date_override_template 
FOREIGN KEY (template_id) 
REFERENCES availabilities(id) 
ON DELETE CASCADE;

-- เพิ่ม index สำหรับ query performance
CREATE INDEX IF NOT EXISTS idx_date_overrides_template_id 
ON date_overrides(template_id);

-- เพิ่ม column สำหรับระบุ scope
ALTER TABLE date_overrides 
ADD COLUMN IF NOT EXISTS template_scope VARCHAR(50) DEFAULT 'template';
