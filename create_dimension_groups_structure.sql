-- ============================================================
-- Dimension Groups and Mapping Structure
-- ============================================================
-- This structure allows:
-- 1. Multiple dimension groups per product (e.g., "Main Dimensions", "Handle Dimensions")
-- 2. Each group can have multiple dimension parameters (width, height, depth, diameter, etc.)
-- 3. Better organization and flexibility
-- ============================================================

-- Step 1: Create dimension groups table
CREATE TABLE IF NOT EXISTS public.tbl_product_dimension_groups (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    product_id uuid NOT NULL,
    
    -- Group identification
    name text NOT NULL,  -- Name of the dimension group (e.g., "Product Measurements", "Handle Dimensions")
    description text NULL,  -- Optional description
    
    -- Ordering for multiple groups per product
    order_index integer NOT NULL DEFAULT 0,
    
    -- Audit fields
    created_by uuid NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    updated_by uuid NULL,
    updated_date timestamp with time zone NULL,
    
    CONSTRAINT tbl_product_dimension_groups_pkey PRIMARY KEY (id),
    CONSTRAINT tbl_product_dimension_groups_product_id_fkey FOREIGN KEY (product_id) 
        REFERENCES public.tbl_products(id) ON DELETE CASCADE
);

-- Step 2: Add dimension_group_id to existing tbl_product_dimensions table
ALTER TABLE IF EXISTS public.tbl_product_dimensions 
    ADD COLUMN IF NOT EXISTS dimension_group_id uuid NULL;

-- Step 3: Add foreign key constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'tbl_product_dimensions_group_fkey'
    ) THEN
        ALTER TABLE public.tbl_product_dimensions
            ADD CONSTRAINT tbl_product_dimensions_group_fkey 
            FOREIGN KEY (dimension_group_id) 
            REFERENCES public.tbl_product_dimension_groups(id) ON DELETE CASCADE;
    END IF;
END $$;

-- Step 4: Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_dimension_groups_product_id 
    ON public.tbl_product_dimension_groups(product_id);
CREATE INDEX IF NOT EXISTS idx_dimension_groups_product_order 
    ON public.tbl_product_dimension_groups(product_id, order_index);
CREATE INDEX IF NOT EXISTS idx_product_dimensions_group_id 
    ON public.tbl_product_dimensions(dimension_group_id);

-- Step 5: Add comments
COMMENT ON TABLE public.tbl_product_dimension_groups IS 'Stores dimension groups/collections for products. Each group can contain multiple dimension parameters (width, height, depth, etc.).';
COMMENT ON COLUMN public.tbl_product_dimension_groups.name IS 'Name of the dimension group (e.g., "Product Measurements", "Handle Dimensions")';
COMMENT ON COLUMN public.tbl_product_dimension_groups.description IS 'Optional description of the dimension group';
COMMENT ON COLUMN public.tbl_product_dimension_groups.order_index IS 'Order index for multiple dimension groups per product';
COMMENT ON COLUMN public.tbl_product_dimensions.dimension_group_id IS 'Reference to the dimension group this parameter belongs to. NULL means dimension is not part of any group.';



