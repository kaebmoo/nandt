-- Migration Script for tenant_humnoi
-- Run this in PostgreSQL

-- 1. Select the tenant schema
SET search_path TO tenant_humnoi;

-- 2. Show current search path (for verification)
SHOW search_path;

-- 3. Add template_id column to date_overrides
ALTER TABLE date_overrides 
ADD COLUMN IF NOT EXISTS template_id INTEGER;

-- 4. Add template_scope column  
ALTER TABLE date_overrides 
ADD COLUMN IF NOT EXISTS template_scope VARCHAR(50) DEFAULT 'template';

-- 5. Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_date_overrides_template_id 
ON date_overrides(template_id);

-- 6. Optional: Add foreign key constraint
-- Uncomment if you want referential integrity
-- ALTER TABLE date_overrides 
-- ADD CONSTRAINT fk_date_override_availability
-- FOREIGN KEY (template_id) 
-- REFERENCES availabilities(id) 
-- ON DELETE CASCADE;

-- 7. Verify the changes
\d date_overrides

-- 8. Check if columns were added successfully
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'tenant_humnoi'
  AND table_name = 'date_overrides'
  AND column_name IN ('template_id', 'template_scope');

-- 9. Update existing records to have template scope
UPDATE date_overrides 
SET template_scope = 'template'
WHERE template_scope IS NULL;

-- 10. Show final table structure
\d date_overrides
